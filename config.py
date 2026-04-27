import os
from dotenv import load_dotenv

load_dotenv()  

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

OPENAI_MODEL = "gpt-4o-mini"

EMBEDDING_MODEL = "text-embedding-3-small"

# ── AI kill switch ────────────────────────────────────────────────────────────
# Set AI_ENABLED=false in your .env to instantly cut off all AI features
# without changing any code or restarting the app.
AI_ENABLED = os.environ.get("AI_ENABLED", "true").lower() == "true"

# ── Rate limiting ─────────────────────
# Caps LLM calls to avoid accidental runaway costs from loops or automation bugs.
RATE_LIMIT_PER_MINUTE = 5

# ── Chunking ──────────────────────────────────────────────────────────────────
# Each PDF page is split into overlapping windows so context at page boundaries
# is not lost. 1200 chars ≈ 300 words — enough for a meaningful passage.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

# How many chunks to retrieve from the vector store per scoring query
TOP_K_CHUNKS = 6

# ── Quote auditing ────────────────────────────────────────────────────────────
# Minimum rapidfuzz partial_ratio score (0–100) to mark a quote as verified.
# 70 allows for minor OCR noise or ligature differences.
FUZZY_MATCH_THRESHOLD = 70

# ── HTTP ──────────────────────────────────────────────────────────────────────
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB hard limit per PDF
REQUEST_TIMEOUT_SECONDS = 30

# Max characters of web page text to keep (avoids bloating the index)
MAX_WEB_CONTENT_CHARS = 5_000

# ── API output ────────────────────────────────────────────────────────────────
# Where the API saves completed result files so n8n can download them
RESULTS_DIR = "results"

# Reject uploaded Excel files larger than this (safety against OOM attacks).
# Legitimate input workbooks are tiny — 10 MB is very generous.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Max number of analysis jobs running at the same time.
# Each job holds one thread and hammers the OpenAI API — keep this small.
MAX_CONCURRENT_JOBS = 2

# Old jobs and their result files are cleaned up after this many hours.
# Prevents unbounded memory growth and disk usage over long server uptimes.
JOB_RETENTION_HOURS = 24
