"""RAG 用チャンクの読み込みと TF-IDF ベクトル索引（ローカル・外部 API 不要）。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: dict[str, Any]


class ChunkStore:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None

    @classmethod
    def load_jsonl(cls, path: Path) -> ChunkStore:
        if not path.is_file():
            logger.warning("rag jsonl not found: %s", path)
            return cls([])

        chunks: list[Chunk] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                text = (obj.get("text") or "").strip()
                if not text:
                    continue
                chunks.append(
                    Chunk(
                        chunk_id=str(obj.get("chunk_id", "")),
                        text=text,
                        meta=dict(obj.get("metadata") or {}),
                    )
                )
        logger.info("loaded %d chunks from %s", len(chunks), path)
        store = cls(chunks)
        store._build_index()
        return store

    def _build_index(self) -> None:
        if not self._chunks:
            return
        texts = [c.text for c in self._chunks]
        self._vectorizer = TfidfVectorizer(
            max_features=50_000,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(texts)

    def is_ready(self) -> bool:
        return bool(self._chunks) and self._matrix is not None

    def search(self, query: str, top_k: int) -> list[tuple[Chunk, float]]:
        if not self.is_ready() or not query.strip():
            return []
        assert self._vectorizer is not None and self._matrix is not None
        qv = self._vectorizer.transform([query])
        sims = cosine_similarity(qv, self._matrix)[0]
        idx = np.argsort(-sims)[:top_k]
        out: list[tuple[Chunk, float]] = []
        for i in idx:
            out.append((self._chunks[int(i)], float(sims[int(i)])))
        return out
