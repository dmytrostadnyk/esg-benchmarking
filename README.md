# ESG Benchmarking Tool

Automates ESG (Environmental, Social, Governance) scoring of companies against a custom rubric — a process that typically takes analysts days of manual work.

Upload an Excel file with company names, sustainability report links, and a scoring rubric. The tool downloads each PDF report, finds the most relevant passages using vector search, scores every topic with GPT-4o, verifies AI-generated quotes against the source to catch hallucinations, and delivers a colour-coded Excel results file — triggered and delivered entirely via n8n automation.

---

## Architecture

```
n8n Cloud Workflow
│
├── Webhook  ──→  POST /analyse  (upload Excel, receive job_id)
│
├── Loop: Wait 60s ──→  GET /status/{job_id}  ──→  Switch
│                                                   ├── done         ──→ GET /results/{job_id}
│                                                   ├── error        ──→ Gmail error email
│                                                   └── processing   ──→ (loop back)
│
└── done path: Google Drive upload ──→ Gmail success email

Python FastAPI Backend  (runs locally, exposed via ngrok)
│
├── parse_workbook()       reads companies + topics + rubric from Excel
├── download_pdf()         fetches sustainability report PDF
├── extract_pages()        PyMuPDF layout-aware text extraction
├── fetch_web_text()       scrapes company website for supplementary info
├── DocumentIndex.build()  chunks text, creates OpenAI embeddings, builds FAISS index
├── DocumentIndex.search() retrieves top-K relevant passages per topic
├── score_company_topic()  GPT-4o scores one company × topic cell via Responses API
├── verify_quote()         rapidfuzz fuzzy match — flags AI hallucinations
└── create_output_excel()  colour-coded .xlsx with audit column
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + uvicorn |
| AI scoring | OpenAI Responses API (GPT-4o) with Pydantic structured outputs |
| Embeddings | OpenAI text-embedding-3-small |
| Vector search | FAISS (Facebook AI Similarity Search) |
| PDF extraction | PyMuPDF |
| Hallucination detection | rapidfuzz fuzzy quote matching |
| Automation | n8n Cloud (webhook, polling loop, Drive, Gmail) |
| Tunnel | ngrok (exposes local API to n8n Cloud) |

---

## Production-Grade Features

- **AI kill switch** — set `AI_ENABLED=false` in `.env` to disable all AI calls instantly, no redeploy needed
- **Rate limiter** — sliding 60-second window, 5 LLM calls/minute, thread-safe across concurrent jobs
- **Concurrent job cap** — semaphore limits parallel analysis threads (default: 2) to prevent OpenAI bill spikes
- **Atomic file writes** — output written to `.tmp` then renamed, so a mid-write crash never serves a corrupt file
- **Structured outputs** — Pydantic validates every LLM response; no JSON parsing errors
- **Quote audit column** — every output row shows whether the AI's supporting quote was actually found in the source document

---

## Project Structure

```
├── api.py                  FastAPI app — 4 endpoints, background pipeline
├── config.py               All settings loaded from environment variables
├── requirements.txt        Python dependencies
├── .env.example            Template for your .env file
├── test.xlsx               Sample input workbook (companies + rubric)
├── modules/
│   ├── auditor.py          Fuzzy quote verification
│   ├── excel_parser.py     Reads the input workbook
│   ├── exporter.py         Writes the colour-coded output workbook
│   ├── pdf_extractor.py    Downloads and extracts PDF text
│   ├── scorer.py           OpenAI Responses API scoring call
│   ├── vector_store.py     FAISS index build + search
│   └── web_retriever.py    Web scraping for supplementary content
└── results/                Output files written here (gitignored)
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/esg-benchmarking-tool.git
cd esg-benchmarking-tool
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
copy .env.example .env
```

Open `.env` and paste your OpenAI API key.

### 3. Start the API

```bash
uvicorn api:app --reload --port 8000
```

Open `http://localhost:8000/docs` to test the API interactively.

### 4. Expose the API to n8n Cloud (skip if using n8n self-hosted)

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL — you'll use it in n8n.

### 5. Set up n8n

Import the n8n workflow (see `n8n_workflow_setup.md` or re-create the 9 nodes manually).
Replace all `localhost:8000` references in the HTTP Request nodes with your ngrok URL.
Add your Google Drive folder and Gmail credentials in n8n.
Publish the workflow.

### 6. Run an analysis

Send your Excel file to the n8n webhook URL:

```bash
curl -X POST https://YOUR_N8N_WEBHOOK_URL \
  -F "file=@test.xlsx"
```

Wait ~3 minutes. The results file lands in your Google Drive and you receive an email.

---

## Input Excel Format

The workbook needs three sheets:

| Sheet | Required columns |
|---|---|
| Companies | `company_name`, `report_url`, `website_url` |
| Topics | `topic_id`, `topic_name`, `topic_description` |
| Rubric | `topic_id`, `score`, `label`, `definition`, `examples` |

See `test.xlsx` for a working example.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns server status and whether AI is enabled |
| POST | `/analyse` | Upload Excel file, returns `job_id` immediately |
| GET | `/status/{job_id}` | Returns `processing / done / error` + progress % |
| GET | `/results/{job_id}` | Downloads the completed Excel file |
