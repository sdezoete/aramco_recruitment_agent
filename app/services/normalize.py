"""Name normalization and fuzzy matching for skills, certifications, degrees."""
from __future__ import annotations

import re

ALIASES = {
    "ml": "machine learning",
    "deep learning": "machine learning",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "power query": "excel",
    "python3": "python",
    "py": "python",
    "t sql": "sql",
    "tsql": "sql",
    "mssql": "sql",
    "postgres": "sql",
    "stats": "statistics",
    "statistical analysis": "statistics",
    "data pipelines": "etl",
    "data pipeline": "etl",
    "ba": "business analysis",
    "cad": "autocad",
    "adobe photoshop": "photoshop",
}

DEGREE_LEVELS = [
    (4, ("phd", "doctor", "doctorate", "dphil")),
    (3, ("master", "masters", "msc", "mba", "meng", "mphil", "ms", "ma")),
    (2, ("bachelor", "bachelors", "bsc", "beng", "bba", "ba", "bs", "degree")),
    (1, ("diploma", "associate")),
]
DEGREE_NAMES = {1: "Diploma", 2: "Bachelor", 3: "Master", 4: "PhD"}


def norm(text: str | None) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9+#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def canonical(text: str | None) -> str:
    n = norm(text)
    return ALIASES.get(n, n)


def tokens(text: str | None) -> set[str]:
    stop = {"and", "of", "the", "in", "for", "a", "an", "certified", "professional", "certification",
            "specialty", "associate"}
    return {t for t in norm(text).split() if t not in stop and len(t) > 1}


def degree_level(text: str | None) -> int:
    """0 unknown, 1 diploma, 2 bachelor, 3 master/MBA, 4 PhD. Short keys match whole tokens only."""
    toks = norm(text).split()
    if not toks:
        return 0
    compact = "".join(toks)  # "m sc" -> "msc"
    for level, keys in DEGREE_LEVELS:
        for k in keys:
            if k in toks:
                return level
            if len(k) >= 3 and (compact == k or any(t.startswith(k) for t in toks if len(k) >= 5)):
                return level
    return 0


def fuzzy_match(needle: str, haystack: list[str], threshold: float = 0.5) -> str | None:
    """Best match of needle in haystack by canonical equality, containment, then token overlap."""
    cn = canonical(needle)
    if not cn:
        return None
    by_canon = {canonical(h): h for h in haystack}
    if cn in by_canon:
        return by_canon[cn]
    for c, h in by_canon.items():
        if c and (cn in c.split() or (len(cn) > 3 and cn in c) or (len(c) > 3 and c in cn)):
            return h
    nt = tokens(needle)
    best, best_score = None, 0.0
    for h in haystack:
        ht = tokens(h)
        if not nt or not ht:
            continue
        score = len(nt & ht) / len(nt)
        if score > best_score:
            best, best_score = h, score
    return best if best_score >= threshold else None
