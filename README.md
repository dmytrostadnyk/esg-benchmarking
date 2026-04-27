# ESG Benchmarking Tool

Automates ESG (Environmental, Social, Governance) scoring of companies against a custom rubric — a process that typically takes analysts days of manual work.

Upload an Excel file with company names, sustainability report links, and a scoring rubric. The tool downloads each PDF report, finds the most relevant passages using vector search, scores every topic with GPT-4o, verifies AI-generated quotes against the source to catch hallucinations, and delivers a colour-coded Excel results file — triggered and delivered entirely via n8n automation.

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

- **AI kill switch** - set `AI_ENABLED=false` in `.env` to disable all AI calls instantly, no redeploy needed
- **Rate limiter** - sliding 60-second window, 5 LLM calls/minute, thread-safe across concurrent jobs
- **Concurrent job cap** - semaphore limits parallel analysis threads (default: 2) to prevent OpenAI bill spikes
- **Atomic file writes** - output written to `.tmp` then renamed, so a mid-write crash never serves a corrupt file
- **Structured outputs** - Pydantic validates every LLM response; no JSON parsing errors
- **Quote audit column** - every output row shows whether the AI's supporting quote was actually found in the source document

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
