"""Long-term Memory — vector-based semantic retrieval.

Uses numpy for cosine similarity search. No external vector database
needed for small-to-medium use cases.

For embedding generation, supports:
- OpenAI Embeddings API
- Simple TF-IDF fallback (no external dependencies)
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from agent2.memory.base import BaseMemory, MemoryItem


class LongTermMemory(BaseMemory):
    """Long-term memory with vector-based semantic search.

    Features:
    - Semantic similarity search using cosine similarity
    - TF-IDF fallback when no embedding model is available
    - Optional persistence to disk
    - Optional OpenAI embeddings for higher quality

    Parameters
    ----------
    embedding_provider : str
        ``"tfidf"`` (default, no deps) or ``"openai"`` (requires openai package).
    persist_path : str | Path | None
        Path to save/load memory to/from disk.
    """

    def __init__(
        self,
        *,
        embedding_provider: str = "tfidf",
        persist_path: str | Path | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._persist_path = Path(persist_path) if persist_path else None
        self._documents: list[dict[str, Any]] = []  # {"content", "metadata", "embedding"}
        self._vocab: dict[str, int] = {}  # For TF-IDF
        self._idf: dict[str, float] = {}

        # Load from disk if available
        if self._persist_path and self._persist_path.exists():
            self._load()

    # ── BaseMemory interface ────────────────────────────────────────

    async def add(self, content: str, **metadata: Any) -> None:
        """Add a document to long-term memory."""
        embedding = await self._embed(content)
        self._documents.append({
            "content": content,
            "metadata": metadata,
            "embedding": embedding,
        })
        # Rebuild IDF for TF-IDF
        if self._embedding_provider == "tfidf":
            self._rebuild_idf()
        # Persist if configured
        if self._persist_path:
            self._save()

    async def search(self, query: str, *, top_k: int = 5) -> list[MemoryItem]:
        """Search memory by semantic similarity."""
        if not self._documents:
            return []

        query_embedding = await self._embed(query)
        scored: list[tuple[float, dict[str, Any]]] = []

        for doc in self._documents:
            score = self._cosine_similarity(query_embedding, doc["embedding"])
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[MemoryItem] = []
        for score, doc in scored[:top_k]:
            if score > 0.0:  # Only include non-zero similarity
                results.append(
                    MemoryItem(
                        content=doc["content"],
                        metadata=doc["metadata"],
                        score=score,
                    )
                )
        return results

    async def clear(self) -> None:
        """Clear all long-term memory."""
        self._documents.clear()
        self._vocab.clear()
        self._idf.clear()
        if self._persist_path and self._persist_path.exists():
            self._persist_path.unlink()

    # ── Embedding ───────────────────────────────────────────────────

    async def _embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        if self._embedding_provider == "openai":
            return await self._embed_openai(text)
        else:
            return self._embed_tfidf(text)

    def _embed_tfidf(self, text: str) -> list[float]:
        """Generate a TF-IDF embedding (no external deps).

        This is a simple bag-of-words approach. Not as good as neural
        embeddings, but works for basic semantic search.
        """
        words = self._tokenize(text)
        tf = Counter(words)
        total = len(words) if words else 1

        # Build vocab if needed
        for w in words:
            if w not in self._vocab:
                self._vocab[w] = len(self._vocab)

        # Create TF-IDF vector
        vector = [0.0] * len(self._vocab)
        for word, count in tf.items():
            idx = self._vocab[word]
            tf_score = count / total
            idf_score = self._idf.get(word, 1.0)
            vector[idx] = tf_score * idf_score

        return vector

    def _rebuild_idf(self) -> None:
        """Rebuild IDF scores from all documents."""
        n_docs = len(self._documents) + 1  # +1 smoothing
        doc_freq: Counter[str] = Counter()

        for doc in self._documents:
            words = set(self._tokenize(doc["content"]))
            for w in words:
                doc_freq[w] += 1

        self._idf = {
            word: math.log(n_docs / (1 + freq))
            for word, freq in doc_freq.items()
        }

    async def _embed_openai(self, text: str) -> list[float]:
        """Generate embedding via OpenAI API."""
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError(
                "openai package required for OpenAI embeddings. "
                "Install with: uv pip install 'agent2[openai]'"
            ) from e

        from agent2.utils.config import settings
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(
            input=text,
            model="text-embedding-3-small",
        )
        return response.data[0].embedding

    # ── Similarity ──────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        # Pad shorter vector with zeros
        max_len = max(len(a), len(b))
        a = a + [0.0] * (max_len - len(a))
        b = b + [0.0] * (max_len - len(b))

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Utilities ───────────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace tokenizer with lowercasing."""
        import re
        return re.findall(r'\w+', text.lower())

    def _save(self) -> None:
        """Persist memory to disk."""
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "documents": [
                {"content": d["content"], "metadata": d["metadata"], "embedding": d["embedding"]}
                for d in self._documents
            ],
            "vocab": self._vocab,
            "idf": self._idf,
        }
        self._persist_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        """Load memory from disk."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._documents = data.get("documents", [])
            self._vocab = data.get("vocab", {})
            self._idf = data.get("idf", {})
        except (json.JSONDecodeError, KeyError):
            pass

    @property
    def size(self) -> int:
        """Number of documents in memory."""
        return len(self._documents)
