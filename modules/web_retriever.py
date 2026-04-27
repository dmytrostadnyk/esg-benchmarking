"""
Fetches plain text from a company's website URL.
BeautifulSoup because it cleanly strips HTML tags, scripts, and navbars
so only the readable body content goes into the vector index.
"""

import requests
from bs4 import BeautifulSoup
from config import REQUEST_TIMEOUT_SECONDS, MAX_WEB_CONTENT_CHARS


def fetch_web_text(url: str) -> str:
    """
    Fetch a web page and return its readable text content.
    Returns an empty string on any error so the caller can safely ignore failures.
    """
    if not url or not url.startswith("http"):
        return ""

    headers = {"User-Agent": "ESG-Benchmarker/1.0 (internal tool)"}

    try:
        response = requests.get(
            url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except Exception:
        # Web fetch is a best-effort supplement — never block the main pipeline
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove tags that never contain useful body content
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # Collapse blank lines and strip each line
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)

    # Truncate so this doesn't dwarf the PDF content in the vector index
    return cleaned[:MAX_WEB_CONTENT_CHARS]
