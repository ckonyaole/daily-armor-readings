"""Vector retrieval over Catena Aurea + CCC parquet corpora."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

class CorpusLoadError(Exception):
    pass

_MODEL: SentenceTransformer | None = None
def _model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _MODEL

class Retriever:
    def __init__(self, catena_path, ccc_path):
        try:
            self.catena = pd.read_parquet(catena_path)
            self.ccc = pd.read_parquet(ccc_path)
        except Exception as e:
            raise CorpusLoadError(f"failed to load corpus: {e}") from e

    def _embed(self, query: str) -> np.ndarray:
        return _model().encode([query], normalize_embeddings=True,
                                convert_to_numpy=True)[0]

    def retrieve_catena(self, query: str, *, k: int = 6,
                         gospel: str | None = None,
                         max_per_father: int = 2) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        df = self.catena
        if gospel:
            df = df[df["gospel"] == gospel.lower()]
        if df.empty:
            return []
        qv = self._embed(q)
        mat = np.vstack(df["embedding"].values)
        sims = mat @ qv
        ordered = df.assign(_score=sims).sort_values("_score", ascending=False)
        chosen: list[dict[str, Any]] = []
        father_counts: dict[str, int] = {}
        for _, row in ordered.iterrows():
            f = row["father"]
            if father_counts.get(f, 0) >= max_per_father:
                continue
            chosen.append({
                "father": f,
                "work": row.get("work", "") or f"Catena Aurea on {row['gospel'].title()}",
                "quote": row["text"],
                "_id": row["id"],
                "_score": float(row["_score"]),
                "_gospel": row["gospel"],
                "_chapter": int(row["chapter"]),
                "_verse_start": int(row["verseStart"]),
            })
            father_counts[f] = father_counts.get(f, 0) + 1
            if len(chosen) >= k:
                break
        return chosen

    def retrieve_ccc(self, query: str, *, k: int = 8) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        df = self.ccc
        if df.empty:
            return []
        qv = self._embed(q)
        mat = np.vstack(df["embedding"].values)
        sims = mat @ qv
        top = df.assign(_score=sims).sort_values("_score", ascending=False).head(k)
        return [{
            "paragraph": int(r["paragraph"]),
            "title": (r.get("section") or "").strip() or f"CCC {int(r['paragraph'])}",
            "text": r["text"],
            "_score": float(r["_score"]),
        } for _, r in top.iterrows()]
