"""
Quote verification layer — checks whether the LLM's supporting_quote
actually appears in the source document.

Why rapidfuzz instead of exact matching?
  OCR, Unicode ligatures, soft-hyphenation, and PDF encoding quirks mean
  a genuine quote may differ by a few characters from what's in the raw text.
  partial_ratio checks if the quote appears as an approximate *substring*,
  which handles these edge cases while still catching hallucinations.

A low fuzzy score does NOT mean the answer is wrong — it means the auditor
could not verify the quote automatically. A human reviewer should check
any row flagged as unverified.
"""

from rapidfuzz import fuzz
from config import FUZZY_MATCH_THRESHOLD


def verify_quote(quote: str, full_document_text: str) -> dict:
    """
    Check whether `quote` appears in `full_document_text`.

    Returns a dict:
      verified        — bool
      match_score     — int 0–100 (rapidfuzz partial_ratio)
      note            — plain-English explanation for the output Excel
    """
    if not quote or not quote.strip():
        return {
            "verified": False,
            "match_score": 0,
            "note": "No quote provided by the model.",
        }

    if not full_document_text:
        return {
            "verified": False,
            "match_score": 0,
            "note": "No source text available to verify against.",
        }

    # partial_ratio: best match of `quote` as a window inside `full_document_text`
    # Case-insensitive to handle capitalisation differences
    score = fuzz.partial_ratio(quote.lower(), full_document_text.lower())
    verified = score >= FUZZY_MATCH_THRESHOLD

    if verified:
        note = f"Verified — fuzzy match {score}/100."
    else:
        note = (
            f"NOT verified — fuzzy match only {score}/100 "
            f"(threshold: {FUZZY_MATCH_THRESHOLD}). "
            "This quote may be hallucinated or significantly paraphrased. "
            "Recommend manual review."
        )

    return {"verified": verified, "match_score": score, "note": note}
