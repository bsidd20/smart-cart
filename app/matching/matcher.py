"""Matches a query to the best in-stock product at a store.

Tries semantic similarity first, falls back to fuzzy, and rejects anything below
min_accept_score. Catalog embeddings are computed once at startup, so each query is
just a matrix multiply against the cached vectors.
"""

from __future__ import annotations

import numpy as np

from app import config
from app.data.store import Candidate, Repository
from app.matching import fuzzy
from app.matching.semantic import cosine_similarity, get_embedder
from app.models import MatchResult


def _candidate_text(c: Candidate) -> str:
    return c.product.name + " " + " ".join(c.product.search_terms)


class ProductMatcher:
    def __init__(self, repo: Repository, cfg: config.MatchConfig | None = None):
        self.repo = repo
        self.cfg = cfg or config.SETTINGS.match
        self.embedder = get_embedder()
        self._cand_cache: dict[str, list[Candidate]] = {}
        self._emb_cache: dict[str, np.ndarray] = {}
        for store_id in repo.all_store_ids():
            cands = repo.candidates(store_id)
            self._cand_cache[store_id] = cands
            self._emb_cache[store_id] = self.embedder.encode([_candidate_text(c) for c in cands])

    @property
    def backend(self) -> str:
        return self.embedder.backend

    def match(self, query: str, store_id: str) -> MatchResult:
        cands = self._cand_cache.get(store_id, [])
        if not cands:
            return MatchResult(query=query, store_id=store_id, available=False)

        qvec = self.embedder.encode([query])[0]
        sem_scores = cosine_similarity(qvec, self._emb_cache[store_id])
        sem_idx = int(np.argmax(sem_scores))
        sem_score = float(sem_scores[sem_idx])

        fz_scores = [fuzzy.best_score(query, c.product.name, c.product.search_terms) for c in cands]
        fz_idx = int(np.argmax(fz_scores))
        fz_score = float(fz_scores[fz_idx])

        # Only a real semantic model is trusted to accept on its own. The hashing
        # fallback over-scores substring overlap ("milk" looks close to "almond
        # milk"), so when it's active the fuzzy score is the gate.
        real_semantic = self.backend == "sentence-transformers"
        if real_semantic and sem_score >= self.cfg.semantic_threshold and sem_score >= fz_score:
            idx, score, method = sem_idx, sem_score, "semantic"
        else:
            idx, score, method = fz_idx, fz_score, "fuzzy"

        if score < self.cfg.min_accept_score:
            return MatchResult(
                query=query,
                store_id=store_id,
                available=False,
                score=round(score, 3),
                method="none",
            )

        chosen = cands[idx]
        return MatchResult(
            query=query,
            store_id=store_id,
            product_id=chosen.product.product_id,
            product_name=chosen.product.name,
            price=chosen.price,
            score=round(score, 3),
            method=method,
            available=True,
        )

    def match_across_stores(self, query: str) -> dict[str, MatchResult]:
        return {sid: self.match(query, sid) for sid in self.repo.all_store_ids()}
