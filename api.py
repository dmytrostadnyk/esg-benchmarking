"""
ESG Benchmarking Tool — FastAPI backend.
n8n calls these four endpoints to orchestrate the full analysis:
  GET  /health              → tells n8n the server is up and AI is enabled
  POST /analyse             → accepts the Excel file, starts the pipeline, returns a job_id
  GET  /status/{job_id}     → n8n polls this until status == "done" or "error"
  GET  /results/{job_id}    → n8n downloads the finished Excel file from here

Why a background thread (not async)?
  The pipeline is mostly blocking I/O (PDF download, OpenAI calls) plus CPU work
  (FAISS). FastAPI's built-in BackgroundTasks shares the event loop with the server,
  which would freeze all /status polls while the pipeline runs. A plain
  threading.Thread keeps the server responsive during long jobs.
  (Production upgrade: replace with Celery + Redis for multi-worker support.)
"""

import io
import logging
import sys
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from config import (
    AI_ENABLED,
    JOB_RETENTION_HOURS,
    MAX_CONCURRENT_JOBS,
    MAX_UPLOAD_BYTES,
    OPENAI_API_KEY,
    RESULTS_DIR,
)
from modules.auditor import verify_quote
from modules.excel_parser import parse_workbook
from modules.exporter import create_output_excel
from modules.pdf_extractor import download_pdf, extract_pages, get_full_text
from modules.scorer import score_company_topic
from modules.vector_store import DocumentIndex
from modules.web_retriever import fetch_web_text

# ── Logging ───────────────────────────────────────────────────────────────────
# Writes to stdout to see errors live in the uvicorn terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("esg-api")


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ESG Benchmarking API",
    description="Python backend for the ESG benchmarking tool.",
    version="1.0.0",
)

# Create the results folder if it doesn't exist yet
Path(RESULTS_DIR).mkdir(exist_ok=True)

# In-memory job store: {job_id: {status, progress, message, result_path, ...}}
# Protected by _jobs_lock for compound updates across multiple keys.
jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# Caps concurrent pipeline threads. Extra jobs queue on this semaphore so the
# OpenAI API isn't flooded when many analysis requests arrive at once.
_job_semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Timezone-aware UTC timestamp (utcnow() is deprecated in Python 3.12+)."""
    return datetime.now(timezone.utc).isoformat()


def _update_job(job_id: str, **fields):
    """Thread-safe partial update of a job record."""
    with _jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(fields)


def _cleanup_old_jobs():
    """
    Delete jobs (and their result files) older than JOB_RETENTION_HOURS.
    Called at the start of every /analyse call — cheap and requires no scheduler.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=JOB_RETENTION_HOURS)
    stale_ids: list[str] = []

    with _jobs_lock:
        for job_id, job in jobs.items():
            try:
                created = datetime.fromisoformat(job.get("created_at", ""))
            except ValueError:
                continue
            if created < cutoff:
                stale_ids.append(job_id)

        for job_id in stale_ids:
            # Remove the result file if it still exists on disk
            result_path = jobs[job_id].get("result_path")
            if result_path:
                try:
                    Path(result_path).unlink(missing_ok=True)
                except Exception as exc:
                    log.warning(f"Could not delete {result_path}: {exc}")
            del jobs[job_id]

    if stale_ids:
        log.info(f"Cleaned up {len(stale_ids)} expired job(s).")


def _validate_upload(file: UploadFile) -> bytes:
    """
    Read the uploaded file, enforce size and format constraints.
    Raises HTTPException on any validation failure.
    """
    # Extension check — openpyxl only handles .xlsx reliably
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=f"Only .xlsx files are accepted. Got: {file.filename!r}",
        )

    data = file.file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds the {limit_mb} MB limit.",
        )
    return data


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", summary="Check server and AI status")
def health():
    """
    Quick health check for n8n to call before starting a job.
    Returns whether the AI kill switch is on and whether the API key is set.
    """
    return {
        "status": "ok",
        "ai_enabled": AI_ENABLED,
        "api_key_set": bool(OPENAI_API_KEY),
        "timestamp": _now_iso(),
    }


@app.post("/analyse", summary="Upload Excel and start analysis")
def analyse(file: UploadFile = File(..., description="The input Excel workbook (.xlsx)")):
    """
    Accept the Excel workbook, start the analysis pipeline in a background thread,
    and immediately return a job_id.

    n8n should then poll GET /status/{job_id} every 60 seconds until done.
    """
    # ── Security checks ───────────────────────────────────────────────────────
    if not AI_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="AI features are disabled. Set AI_ENABLED=true in your .env file.",
        )
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY is not set. Add it to your .env file.",
        )

    # Validate and read the upload (size, format, non-empty)
    excel_bytes = _validate_upload(file)

    # Garbage-collect expired jobs before accepting a new one
    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        jobs[job_id] = {
            "status": "processing",
            "progress": 0.0,
            "message": "Job queued — pipeline starting...",
            "result_path": None,
            "error": None,
            "created_at": _now_iso(),
        }

    # Launch pipeline in a background thread so this endpoint returns immediately
    thread = threading.Thread(
        target=_run_pipeline,
        args=(job_id, excel_bytes),
        daemon=True,  # thread dies automatically if the server shuts down
    )
    thread.start()

    log.info(f"Started job {job_id} (upload: {len(excel_bytes)} bytes)")
    return {
        "job_id": job_id,
        "status_url": f"/status/{job_id}",
        "results_url": f"/results/{job_id}",
    }


@app.get("/status/{job_id}", summary="Poll job progress")
def status(job_id: str):
    """
    Returns the current state of a job.

    n8n polls this endpoint in a loop (every 60 s) and routes on the status field:
      "processing" → wait and check again
      "done"       → call GET /results/{job_id}
      "error"      → send error notification
    """
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        # Return a shallow copy so the client can't mutate our state
        return dict(jobs[job_id])


@app.get("/results/{job_id}", summary="Download the finished Excel report")
def results(job_id: str):
    """
    Streams the colour-coded output Excel file back to n8n as binary.
    Only available once status == "done".
    """
    with _jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        job = dict(jobs[job_id])   # snapshot under lock

    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=f"Job failed: {job['error']}")

    if job["status"] != "done":
        raise HTTPException(
            status_code=202,
            detail=f"Job is still running. Progress: {job['progress']:.0%} — {job['message']}",
        )

    result_path = Path(job["result_path"])
    if not result_path.exists():
        raise HTTPException(
            status_code=410,
            detail="Result file has expired or been cleaned up.",
        )

    return FileResponse(
        path=str(result_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"esg_results_{job_id[:8]}.xlsx",
    )


# ── Background pipeline ───────────────────────────────────────────────────────

def _update_progress(job_id: str, progress: float, message: str):
    """Helper to report progress from inside the pipeline thread."""
    _update_job(job_id, progress=round(progress, 2), message=message)


def _run_pipeline(job_id: str, excel_bytes: bytes):
    """
    The full analysis pipeline. Runs in a background thread so the API stays
    responsive. Updates jobs[job_id] as it progresses.

    Concurrency is capped by _job_semaphore so we don't spawn unlimited
    OpenAI-hammering workers when many requests arrive together.
    """
    # If MAX_CONCURRENT_JOBS workers are already busy, this blocks until one frees up
    _update_progress(job_id, 0.0, "Waiting for an available worker slot...")

    with _job_semaphore:
        try:
            _update_progress(job_id, 0.02, "Parsing Excel workbook...")
            workbook_data = parse_workbook(io.BytesIO(excel_bytes))

            companies = workbook_data["companies"]
            topics    = workbook_data["topics"]

            if not companies or not topics:
                raise ValueError(
                    "Workbook has no companies or no topics — nothing to score."
                )

            # Group rubric score levels by topic_id for fast lookup during scoring
            rubric_by_topic_id: dict[str, list] = {}
            for row in workbook_data["rubric"]:
                rubric_by_topic_id.setdefault(row["topic_id"], []).append(row)

            total_tasks = len(companies) * len(topics)
            completed   = 0
            all_results: list[dict] = []

            # ── Per-company pipeline ──────────────────────────────────────────
            for company in companies:
                company_name = company["company_name"]
                report_url   = company["report_url"]
                website_url  = company.get("website_url", "")

                # Download and extract PDF — failures don't stop the whole job,
                # the company's topics will be scored against empty context and
                # the LLM will return "No Disclosure".
                _update_progress(
                    job_id,
                    completed / max(total_tasks, 1),
                    f"Downloading PDF — {company_name}",
                )
                try:
                    pdf_bytes_dl = download_pdf(report_url)
                    pages        = extract_pages(pdf_bytes_dl)
                    full_text    = get_full_text(pages)
                except Exception as exc:
                    pages, full_text = [], ""
                    log.warning(f"[{job_id}] PDF failed for {company_name}: {exc}")

                # Fetch supplementary web content (best-effort, never raises)
                web_text = fetch_web_text(website_url)

                # Build FAISS vector index for this company's documents
                _update_progress(
                    job_id,
                    completed / max(total_tasks, 1),
                    f"Building search index — {company_name}",
                )
                doc_index = DocumentIndex()
                try:
                    doc_index.build(pages, web_text, OPENAI_API_KEY)
                except Exception as exc:
                    log.warning(f"[{job_id}] Index build failed for {company_name}: {exc}")

                # ── Score each topic ──────────────────────────────────────────
                for topic in topics:
                    topic_id    = topic.get("topic_id", "")
                    topic_name  = topic["topic_name"]
                    topic_desc  = topic.get("topic_description", "")
                    score_levels = rubric_by_topic_id.get(topic_id, [])

                    _update_progress(
                        job_id,
                        completed / max(total_tasks, 1),
                        f"Scoring — {company_name} | {topic_name}",
                    )

                    # Skip topics with no rubric — nothing to score against
                    if not score_levels:
                        all_results.append(_error_row(
                            company_name, topic_name,
                            f"No rubric rows found for topic_id '{topic_id}'.",
                        ))
                        completed += 1
                        continue

                    # Retrieve the most relevant passages for this topic
                    context_chunks = doc_index.search(
                        f"{topic_name}: {topic_desc}", OPENAI_API_KEY
                    )

                    try:
                        result = score_company_topic(
                            company_name      = company_name,
                            topic_name        = topic_name,
                            topic_description = topic_desc,
                            score_levels      = score_levels,
                            context_chunks    = context_chunks,
                            api_key           = OPENAI_API_KEY,
                        )

                        # Look up the human-readable label (e.g. "Leading") for the score
                        label_map   = {sl["score"]: sl["label"] for sl in score_levels}
                        score_label = label_map.get(result.score, str(result.score))

                        # Verify the quote against both PDF and web text
                        audit = verify_quote(
                            result.supporting_quote,
                            full_text + "\n" + web_text,
                        )

                        all_results.append({
                            "company":           company_name,
                            "topic":             topic_name,
                            "score":             result.score,
                            "score_label":       score_label,
                            "confidence":        result.confidence,
                            "rationale":         result.rationale,
                            "supporting_quote":  result.supporting_quote,
                            "page_reference":    result.page_reference,
                            "quote_verified":    audit["verified"],
                            "fuzzy_match_score": audit["match_score"],
                            "audit_note":        audit["note"],
                            "error":             None,
                        })

                    except Exception as exc:
                        log.warning(
                            f"[{job_id}] Scoring failed for "
                            f"{company_name} | {topic_name}: {exc}"
                        )
                        all_results.append(_error_row(company_name, topic_name, str(exc)))

                    completed += 1

            # ── Export to Excel and save to disk (atomic) ─────────────────────
            _update_progress(job_id, 0.97, "Generating Excel output file...")
            excel_output = create_output_excel(all_results)

            # Atomic write: write to .tmp then rename, so a crashed mid-write
            # never leaves a corrupt file that /results would serve.
            result_path = Path(RESULTS_DIR) / f"{job_id}.xlsx"
            tmp_path    = result_path.with_suffix(".xlsx.tmp")
            tmp_path.write_bytes(excel_output)
            tmp_path.replace(result_path)

            _update_job(
                job_id,
                status="done",
                progress=1.0,
                message=f"Analysis complete. {len(all_results)} rows scored.",
                result_path=str(result_path),
            )
            log.info(f"Job {job_id} finished: {len(all_results)} rows.")

        except Exception as exc:
            # Catch-all: any unexpected error marks the job as failed.
            # Full traceback goes to the server log so you can debug.
            log.error(f"Job {job_id} crashed:\n{traceback.format_exc()}")
            _update_job(
                job_id,
                status="error",
                progress=0.0,
                message=str(exc),
                error=str(exc),
            )


def _error_row(company: str, topic: str, error: str) -> dict:
    """Build a blank result row for a failed topic (keeps the output complete)."""
    return {
        "company": company, "topic": topic,
        "score": None, "score_label": None, "confidence": None,
        "rationale": None, "supporting_quote": None, "page_reference": None,
        "quote_verified": False, "fuzzy_match_score": 0,
        "audit_note": None, "error": error,
    }
