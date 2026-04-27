"""
Builds an in-memory FAISS vector index for one company's documents
(PDF pages + optional web content) so we can retrieve the most relevant
passages for each scoring query.
Why FAISS (not LangChain)?
  LangChain is listed as optional in the brief. We implement chunking and
  search ourselves — it's only ~60 lines and avoids the fragile LangChain
  version dependency chain.
Why cosine similarity (IndexFlatIP + L2 normalisation)?
  Cosine similarity ignores chunk length, so a short but highly relevant
  3-sentence passage scores as well as a long tangentially-related block.
"""

import numpy as np
import faiss
from openai import OpenAI
from config import CHUNK_SIZE, CHUNK_OVERLAP, EMBEDDING_MODEL, TOP_K_CHUNKS


# ── Chunking ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, page_num) -> list[dict]:
    """Split one page's text into overlapping windows."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        snippet = text[start:end].strip()
        if len(snippet) > 50:   # ignore near-empty windows
            chunks.append({"text": snippet, "page": page_num})
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def build_chunks(pages: list[dict], web_text: str) -> list[dict]:
    """Chunk all PDF pages and web content into retrieval-ready pieces."""
    chunks = []
    for p in pages:
        chunks.extend(_chunk_text(p["text"], p["page"]))
    if web_text.strip():
        chunks.extend(_chunk_text(web_text, "web"))
    return chunks


# ── Embeddings ─────────────────────────────────────────────────────────────────

def _get_embeddings(texts: list[str], api_key: str) -> np.ndarray:
    """
    Batch-embed a list of texts using the OpenAI embeddings API.
    Sends at most 100 texts per request to stay within API limits.
    Returns a float32 numpy array of shape (len(texts), embedding_dim).
    """
    client = OpenAI(api_key=api_key)
    all_vectors = []

    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        response = client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
        # response.data is sorted by index, so order is preserved
        all_vectors.extend(item.embedding for item in response.data)

    return np.array(all_vectors, dtype=np.float32)


# ── Index class ────────────────────────────────────────────────────────────────

class DocumentIndex:
    """FAISS cosine-similarity index for a single company."""

    def __init__(self):
        self.chunks: list[dict] = []
        self._index = None          # faiss.Index, set after build()

    def build(self, pages: list[dict], web_text: str, api_key: str):
        """
        Embed all document chunks and load them into FAISS.
        Call this once per company before running any queries.
        """
        self.chunks = build_chunks(pages, web_text)
        if not self.chunks:
            return  # nothing to index (e.g. scanned PDF with no web fallback)

        texts = [c["text"] for c in self.chunks]
        embeddings = _get_embeddings(texts, api_key)

        # Normalise to unit length so inner product equals cosine similarity
        faiss.normalize_L2(embeddings)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)

    def search(self, query: str, api_key: str, top_k: int = TOP_K_CHUNKS) -> list[dict]:
        """
        Return the top_k chunks most relevant to the query.
        Returns an empty list if the index was never built.
        """
        if self._index is None or not self.chunks:
            return []

        q_vec = _get_embeddings([query], api_key)
        faiss.normalize_L2(q_vec)

        k = min(top_k, len(self.chunks))
        _, indices = self._index.search(q_vec, k)

        return [self.chunks[i] for i in indices[0] if i != -1]
