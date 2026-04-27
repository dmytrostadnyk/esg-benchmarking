"""
Calls the OpenAI API to score one company × topic × rubric-category combination.

Uses the Responses API (client.responses.parse) — OpenAI's newest API, which
replaces Chat Completions for all new development. Structured outputs guarantee
the response is a valid ScoringResult — no manual JSON parsing or error handling
for format mistakes needed. Pydantic validates field types and the score range.

store=False tells OpenAI not to retain the response on their servers for the
default 30 days — we never need to retrieve past responses, and ESG content
extracted from corporate reports is best kept out of any retention store.

Rate limiting is enforced here (not in the caller) so every code path
that touches the LLM is automatically protected.
"""

import threading
import time
from collections import deque
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, field_validator

from config import OPENAI_MODEL, RATE_LIMIT_PER_MINUTE


# ── Pydantic model for structured output ───────────────────────────────────────

class ScoringResult(BaseModel):
    """One scored cell: company × topic."""
    score: int
    confidence: Literal["High", "Medium", "Low"]
    rationale: str
    supporting_quote: str
    page_reference: str   # e.g. "p. 12"  or  "web"

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"score must be >= 0, got {v}")
        return v


# ── Rate limiter (sliding window) ─────────────────────────────────────────────

class _RateLimiter:
    """
    Allows at most `max_per_minute` calls in any rolling 60-second window.

    Thread-safe — when two analysis jobs run concurrently they share a single
    limiter instance, so the lock prevents them from both passing the length
    check at the same moment and exceeding the cap.
    """

    def __init__(self, max_per_minute: int):
        self._max = max_per_minute
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def wait_if_needed(self):
        """
        Block until the caller is cleared to make an API call.
        Loop + acquire/release pattern: we never hold the lock while sleeping,
        so other threads can check capacity concurrently.
        """
        while True:
            with self._lock:
                now = time.time()
                # Drop timestamps older than 60 s
                while self._timestamps and now - self._timestamps[0] > 60:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max:
                    # Capacity available — record this call and return
                    self._timestamps.append(now)
                    return
                # At capacity — compute how long until the oldest slot frees up
                wait = 60 - (now - self._timestamps[0]) + 0.05
            # Lock released before sleeping so other threads aren't blocked
            time.sleep(max(0.0, wait))


# One shared limiter for all LLM calls in the session
_limiter = _RateLimiter(RATE_LIMIT_PER_MINUTE)


# ── Scoring function ───────────────────────────────────────────────────────────

def _build_rubric_text(score_levels: list[dict]) -> str:
    """
    Format the list of score levels into a readable rubric block for the prompt.
    Each level has: score (int), label (str), definition (str), examples (str).
    """
    lines = []
    for level in score_levels:
        line = f"  Score {level['score']} — {level['label']}: {level['definition']}"
        if level.get("examples"):
            line += f"\n    Example: {level['examples']}"
        lines.append(line)
    return "\n".join(lines)


def score_company_topic(
    company_name: str,
    topic_name: str,
    topic_description: str,
    score_levels: list[dict],
    context_chunks: list[dict],
    api_key: str,
    model: str = OPENAI_MODEL,
) -> ScoringResult:
    """
    Ask the LLM to score one company on one topic using the rubric score levels.

    score_levels — list of dicts from the Rubric sheet for this topic,
                   each containing: score, label, definition, examples
    Blocks if the rate limit is about to be exceeded.
    Returns a ScoringResult (never None — raises on total failure instead).
    """
    _limiter.wait_if_needed()

    client = OpenAI(api_key=api_key)

    # Format retrieved passages for the prompt
    if context_chunks:
        context_text = "\n\n".join(
            f"[Source {i + 1} | Page {chunk['page']}]\n{chunk['text']}"
            for i, chunk in enumerate(context_chunks)
        )
    else:
        context_text = "No relevant text could be retrieved from the document."

    rubric_text = _build_rubric_text(score_levels)
    min_score   = score_levels[0]["score"]  if score_levels else 0
    max_score   = score_levels[-1]["score"] if score_levels else 4

    prompt = f"""You are an expert ESG analyst benchmarking corporate sustainability reports.

COMPANY: {company_name}
TOPIC: {topic_name}
TOPIC DESCRIPTION: {topic_description}

RUBRIC — score definitions ({min_score} = weakest, {max_score} = strongest):
{rubric_text}

SOURCE TEXT (extracted from the company's report and/or website):
{context_text}

INSTRUCTIONS:
1. Read every source passage carefully. Identify information directly relevant to "{topic_name}".
2. Choose the score ({min_score}–{max_score}) that best matches what the company has actually disclosed.
3. If no relevant information exists, assign Score {min_score} and explain why in rationale.
4. supporting_quote MUST be a verbatim copy of a sentence or phrase from the source text above.
   Do NOT paraphrase or summarise — copy the exact words.
5. page_reference should match the [Page X] label in the source (e.g. "p. 23").
   If the evidence comes from the website supplement, write "web".
6. confidence:
   - High   → the quote directly and explicitly satisfies the rubric criterion
   - Medium → the quote partially or implicitly supports the criterion
   - Low    → the evidence is weak, inferred, or tangential

Return a JSON object with fields: score, confidence, rationale, supporting_quote, page_reference."""

    response = client.responses.parse(
        model=model,
        input=prompt,
        text_format=ScoringResult,
        temperature=0.1,   # low temperature = more deterministic, consistent scores
        store=False,       # don't keep the response on OpenAI's servers
    )

    return response.output_parsed
