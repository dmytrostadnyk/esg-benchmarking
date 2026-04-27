"""
Reads the three required sheets from the input Excel workbook
and returns them as plain Python lists-of-dicts.

Expected sheets
---------------
Companies  — company_name | report_url | website_url (optional)
Topics     — topic_id | topic_name | description
Rubric     — topic_id | score | label | definition | examples (optional)
             One row per score level. Scores are integers (e.g. 0–4).
"""

import pandas as pd

# Minimum columns that must exist in each sheet
_COMPANY_COLS = {"company_name", "report_url"}
_TOPIC_COLS   = {"topic_name"}
_RUBRIC_COLS  = {"topic_id", "score", "label", "definition"}


def parse_workbook(file) -> dict:
    """
    Parse the uploaded Excel file and return a dict with keys:
      companies, topics, rubric  (each is a list of dicts)

    Rubric rows are enriched with topic_name by joining with the topics sheet.
    Raises ValueError with a plain-English message when the file is malformed.
    """
    try:
        xl = pd.ExcelFile(file)
    except Exception as exc:
        raise ValueError(f"Could not open Excel file: {exc}") from exc

    # Sheet names — compare case-insensitively
    found = {s.lower(): s for s in xl.sheet_names}
    for required in ("companies", "topics", "rubric"):
        if required not in found:
            raise ValueError(
                f"Missing required sheet '{required}'. "
                f"Sheets found: {xl.sheet_names}"
            )

    topics = _read_topics(xl, found["topics"])
    rubric = _read_rubric(xl, found["rubric"])

    # Join: add topic_name to each rubric row so the scorer can reference it by name
    topic_id_to_name = {t["topic_id"]: t["topic_name"] for t in topics if t.get("topic_id")}
    for row in rubric:
        row["topic_name"] = topic_id_to_name.get(row["topic_id"], row["topic_id"])

    return {
        "companies": _read_companies(xl, found["companies"]),
        "topics":    topics,
        "rubric":    rubric,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case and snake_case all column names."""
    df.columns = (
        df.columns.str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
    )
    return df


def _require_columns(df: pd.DataFrame, required: set, sheet: str):
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Sheet '{sheet}' is missing columns: {missing}. "
            f"Columns found: {list(df.columns)}"
        )


def _read_companies(xl: pd.ExcelFile, sheet: str) -> list[dict]:
    df = _normalise_columns(xl.parse(sheet))
    _require_columns(df, _COMPANY_COLS, sheet)
    df = df.dropna(subset=["company_name", "report_url"])
    df["company_name"] = df["company_name"].astype(str).str.strip()
    df["report_url"]   = df["report_url"].astype(str).str.strip()
    # website_url is optional — fill blanks with empty string
    if "website_url" not in df.columns:
        df["website_url"] = ""
    df["website_url"] = df["website_url"].fillna("").astype(str).str.strip()
    return df[["company_name", "report_url", "website_url"]].to_dict("records")


def _read_topics(xl: pd.ExcelFile, sheet: str) -> list[dict]:
    df = _normalise_columns(xl.parse(sheet))
    _require_columns(df, _TOPIC_COLS, sheet)
    df = df.dropna(subset=["topic_name"])
    df["topic_name"] = df["topic_name"].astype(str).str.strip()

    # Accept either 'description' or 'topic_description' as the description column
    if "description" in df.columns and "topic_description" not in df.columns:
        df = df.rename(columns={"description": "topic_description"})
    if "topic_description" not in df.columns:
        df["topic_description"] = ""
    df["topic_description"] = df["topic_description"].fillna("").astype(str).str.strip()

    # topic_id is optional but needed for joining with rubric
    if "topic_id" not in df.columns:
        df["topic_id"] = ""
    df["topic_id"] = df["topic_id"].fillna("").astype(str).str.strip()

    return df[["topic_id", "topic_name", "topic_description"]].to_dict("records")


def _read_rubric(xl: pd.ExcelFile, sheet: str) -> list[dict]:
    df = _normalise_columns(xl.parse(sheet))
    _require_columns(df, _RUBRIC_COLS, sheet)
    df = df.dropna(subset=["topic_id", "score", "label", "definition"])

    df["topic_id"]   = df["topic_id"].astype(str).str.strip()
    # Parse score as numeric; invalid values become NaN and get dropped next
    df["score"]      = pd.to_numeric(df["score"], errors="coerce")
    df["label"]      = df["label"].astype(str).str.strip()
    df["definition"] = df["definition"].astype(str).str.strip()

    # examples is optional — treat NaN as empty string
    if "examples" not in df.columns:
        df["examples"] = ""
    df["examples"] = df["examples"].fillna("").astype(str).str.strip()

    # Drop any rows where score failed to parse, THEN convert to plain Python int.
    # Plain int is important because score is later used as a dict key to map to
    # labels — pandas nullable Int64 can behave subtly differently from built-in int.
    df = df.dropna(subset=["score"])
    df["score"] = df["score"].astype(int)
    df = df.sort_values(["topic_id", "score"])

    return df[["topic_id", "score", "label", "definition", "examples"]].to_dict("records")
