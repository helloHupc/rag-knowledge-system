from __future__ import annotations

import re


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _extract_query_terms(query: str) -> list[str]:
    normalized = _normalize_text(query)
    if not normalized:
        return []

    split_terms = [term for term in normalized.split(" ") if term]
    extracted: list[str] = []
    seen: set[str] = set()

    for term in split_terms:
        ascii_segments = re.findall(r"[a-z0-9]+", term)
        cjk_segments = re.findall(r"[\u4e00-\u9fff]{2,}", term)

        candidates = ascii_segments + cjk_segments
        if not candidates and term:
            candidates = [term]

        for candidate in candidates:
            if candidate not in seen:
                extracted.append(candidate)
                seen.add(candidate)

    return extracted


def _expand_terms(terms: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()

    for term in terms:
        candidates = [term]
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", term):
            candidates.extend(
                term[index:index + 2]
                for index in range(len(term) - 1)
            )

        for candidate in candidates:
            if candidate and candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)

    return expanded


def score_text_match(query: str, text: str) -> float:
    query_terms = _expand_terms(_extract_query_terms(query))
    if not query_terms:
        return 0.0

    normalized_text = _normalize_text(text)
    hits = sum(1 for term in query_terms if term in normalized_text)
    return round(hits / len(query_terms), 4)


def blend_scores(*, vector_score: float, text_score: float) -> float:
    return round((vector_score * 0.7) + (text_score * 0.3), 6)
