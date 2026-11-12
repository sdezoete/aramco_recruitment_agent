"""Name normalization and fuzzy matching for skills, titles, majors and degrees.

Unicode-aware: Arabic text (names, skills, institutions on the server) survives normalization."""
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
    # raw resume spellings (ORG_SKILL is used as-is since 2026-11-11, so variants are grouped here)
    "python 3": "python",
    "python programming": "python",
    "ms sql server": "sql",
    "sql server": "sql",
    "sql queries": "sql",
    "advanced excel": "excel",
    "auto cad": "autocad",
    "autocad 2d 3d": "autocad",
    "تعلم الآلة": "machine learning",
    "تعلم الاله": "machine learning",
    "الإحصاء": "statistics",
    "الاحصاء": "statistics",
    "تحليل الأعمال": "business analysis",
    "تحليل الاعمال": "business analysis",
    "إدارة المشاريع": "project management",
    "ادارة المشاريع": "project management",
    "pm": "project management",
}

DEGREE_LEVELS = [
    (4, ("phd", "doctor", "doctorate", "dphil", "دكتوراه", "الدكتوراه")),
    (3, ("master", "masters", "msc", "mba", "meng", "mphil", "ms", "ma", "ماجستير", "الماجستير")),
    (2, ("bachelor", "bachelors", "bsc", "beng", "bba", "ba", "bs", "degree", "بكالوريوس", "البكالوريوس")),
    (1, ("diploma", "associate", "دبلوم", "الدبلوم")),
]
DEGREE_NAMES = {1: "Diploma", 2: "Bachelor", 3: "Master", 4: "PhD"}


def norm(text: str | None) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^\w+#]+|_", " ", t)
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


# ------------------------------------------------------------------------------------------- free-text dates
# STARTDATE / ENDDATE are free text on the server ("Mar 2019", "2019-03", "03/2019", "2019", "Present").
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_PRESENT = re.compile(r"present|current|now|ongoing|to\s*date|till\s*date|today|حتى\s*الآن|الآن|حاليا|حالياً", re.I)


def is_present(text: str | None) -> bool:
    return bool(text and _PRESENT.search(text))


def parse_date(text: str | None) -> tuple[int, int] | None:
    """(year, month) from a free-text date, month 1 when unknown; None when there is no year."""
    if not text:
        return None
    s = text.strip().lower()
    m = re.search(r"(19|20)\d{2}", s)
    if not m:
        return None
    year = int(m.group(0))
    month = 1
    for name, num in _MONTHS.items():
        if re.search(r"\b" + name, s):
            return year, num
    m2 = re.search(r"\b(\d{4})[-/.](\d{1,2})\b", s) or re.search(r"\b(\d{1,2})[-/.](\d{4})\b", s)
    if m2:
        a, b = m2.groups()
        mm = int(b) if len(a) == 4 else int(a)
        if 1 <= mm <= 12:
            month = mm
    return year, month
