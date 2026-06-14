"""Fuzzy product-name matching with RapidFuzz.

Lexical similarity: fast and deterministic, good for typos/plurals/word order, but
blind to true synonyms (it doesn't know aubergine == eggplant). The semantic matcher
covers that case.
"""

from __future__ import annotations

from rapidfuzz import fuzz


def best_score(query: str, name: str, search_terms: list[str]) -> float:
    """Best 0..1 similarity of `query` against a product's name and synonyms.

    An exact match to any synonym wins outright. This is what lets "rice" pick
    "White Basmati Rice" (which lists "rice" as a synonym) over "Brown Rice" (which
    doesn't) - token_set_ratio would score both 1.0 since "rice" is a subset of each.
    Otherwise token_sort_ratio is used, so an extra word like "brown" lowers the score.
    """
    q = query.lower().strip()
    candidates = [name.lower()] + [t.lower() for t in search_terms]
    best = 0.0
    for cand in candidates:
        if cand == q:
            return 1.0
        score = fuzz.token_sort_ratio(q, cand) / 100.0
        if score > best:
            best = score
    return best
