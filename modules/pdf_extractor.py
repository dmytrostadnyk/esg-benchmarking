"""
Downloads a PDF from a URL and extracts text page-by-page using PyMuPDF. PyMuPDF (fitz) 
is used because it understands multi-column layouts and reading order, 
which plain pdfminer doesn't. ESG reports often use two-column designs and sidebars.
"""

import fitz  # PyMuPDF
import requests
from config import MAX_PDF_BYTES, REQUEST_TIMEOUT_SECONDS


def download_pdf(url: str) -> bytes:
    """
    Fetch a PDF from a URL and return its raw bytes.
    Raises ValueError if the file exceeds MAX_PDF_BYTES.
    Raises requests.HTTPError if the server returns an error status.
    """
    headers = {"User-Agent": "ESG-Benchmarker/1.0 (internal tool)"}
    response = requests.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
        stream=True,           # stream so we can check size before loading all into RAM
    )
    response.raise_for_status()

    chunks = []
    total_bytes = 0
    for chunk in response.iter_content(chunk_size=8_192):
        total_bytes += len(chunk)
        if total_bytes > MAX_PDF_BYTES:
            limit_mb = MAX_PDF_BYTES // (1024 * 1024)
            raise ValueError(f"PDF exceeds the {limit_mb} MB size limit — skipping.")
        chunks.append(chunk)

    return b"".join(chunks)


def extract_pages(pdf_bytes: bytes) -> list[dict]:
    """
    Extract text from every page of a PDF.

    Returns a list of dicts:
      {"page": int (1-indexed), "text": str}

    Pages with no extractable text are excluded (e.g. pure-image scans).
    If the whole PDF is scanned, an empty list is returned — the caller
    should warn the user and fall back to web content.
    """
    pages = []
    # Open from bytes — no temp file needed
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for i in range(len(doc)):
        page = doc[i]
        # "text" mode preserves reading order better than "rawdict" for our use case
        raw = page.get_text("text")

        # Normalise whitespace: collapse blank lines, strip leading/trailing spaces
        lines = [line.strip() for line in raw.splitlines()]
        cleaned = "\n".join(line for line in lines if line)

        if len(cleaned) > 50:   # skip near-empty pages (headers/footers only)
            pages.append({"page": i + 1, "text": cleaned})

    doc.close()
    return pages


def get_full_text(pages: list[dict]) -> str:
    """
    Concatenate all pages into one string with page markers.
    Used by the quote auditor to search across the whole document.
    """
    return "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in pages)
