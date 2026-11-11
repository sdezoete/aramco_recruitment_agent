"""Deterministic JD text -> JobSpec draft, mapped onto the real Skill vocabulary.

The LLM reviews the draft and may override fields through set_job_spec arguments.
"""
from __future__ import annotations

import re

from app.services.normalize import ALIASES, DEGREE_NAMES, canonical, degree_level, fuzzy_match, norm
from app.services.scoring import JobSpec

_PREFERRED_HEADINGS = re.compile(r"(preferred|nice[\s-]to[\s-]have|desirable|bonus|plus)", re.I)
_REQUIRED_HEADINGS = re.compile(r"(required|requirements|must[\s-]have|essential|qualifications|skills)", re.I)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)", re.I)
_TITLE_STOP = {"senior", "junior", "lead", "principal", "staff", "sr", "jr", "i", "ii", "iii"}


def _mentions(text_norm: str, skill: str) -> bool:
    c = canonical(skill)
    variants = {c} | {a for a, target in ALIASES.items() if target == c}
    return any(re.search(r"(?<![a-z0-9])" + re.escape(v) + r"(?![a-z0-9])", text_norm) for v in variants if v)


def map_skills(names: list[str], vocabulary: list[str]) -> tuple[list[str], list[str]]:
    """Map free-text skill names onto vocabulary names. Returns (mapped, unmapped)."""
    mapped, unmapped = [], []
    for n in names:
        m = fuzzy_match(n, vocabulary, threshold=0.75)
        if m and m not in mapped:
            mapped.append(m)
        elif not m:
            unmapped.append(n)
    return mapped, unmapped


def extract(text: str, vocabulary: list[str], title: str | None = None) -> JobSpec:
    lines = [l.strip() for l in text.splitlines()]
    spec = JobSpec()
    spec.title = title or next((l.lstrip("#").strip() for l in lines if l), "")[:120]

    # Split text into required / preferred / other zones by headings. Skills in "other" sections
    # (about, responsibilities) don't count. Without any requirements heading, all non-preferred text counts.
    zone = "other"
    zones: dict[str, list[str]] = {"required": [], "preferred": [], "other": []}
    for l in lines:
        is_heading = l.startswith("#") or (l.endswith(":") and len(l) < 60)
        if is_heading:
            if _PREFERRED_HEADINGS.search(l):
                zone = "preferred"
            elif _REQUIRED_HEADINGS.search(l):
                zone = "required"
            else:
                zone = "other"
        zones[zone].append(l)
    req_text = zones["required"] or zones["other"]
    pref_text = zones["preferred"]
    req_norm, pref_norm = norm(" ".join(req_text)), norm(" ".join(pref_text))

    for skill in vocabulary:
        if _mentions(req_norm, skill):
            spec.required_skills.append(skill)
        elif _mentions(pref_norm, skill):
            spec.preferred_skills.append(skill)

    years = [int(m.group(1)) for m in _YEARS.finditer(" ".join(req_text))]
    spec.min_years = float(min(years)) if years else 0.0

    degree_lines = [l for l in req_text if re.search(r"degree|bachelor|master|phd|doctor|diploma|b\.?sc|m\.?sc|mba", l, re.I)]
    spec.degree_level = min((lvl for lvl in (degree_level(l) for l in degree_lines) if lvl), default=0)
    for l in degree_lines:
        m = re.search(r"\bin\s+([A-Za-z ,/&]+)", l)
        if m:
            for part in re.split(r",|/| or | and ", m.group(1)):
                part = part.strip(" .")
                if 2 < len(part) < 40 and part.lower() not in ("a related field", "related field"):
                    spec.majors.append(part)

    spec.certifications = [l.lstrip("-*• ").strip() for l in req_text
                           if re.search(r"certif", l, re.I) and not l.startswith("#") and len(l) < 120][:5]

    words = [w for w in re.findall(r"[A-Za-z]+", spec.title) if w.lower() not in _TITLE_STOP]
    spec.title_keywords = [" ".join(words)] if words else []
    return spec


def describe(spec: JobSpec) -> dict:
    d = spec.to_dict()
    d["degree"] = DEGREE_NAMES.get(spec.degree_level, "any")
    return d
