"""Deterministic, explainable candidate-to-JobSpec scoring (docs/DATA_MODEL.md, Scoring model).

The LLM never produces scores. It may only change weights / must-haves through tool arguments.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.services.normalize import canonical, degree_level, fuzzy_match, norm, tokens

CRITERIA = ("skills", "experience", "relevance", "education", "assessments")
DEFAULT_WEIGHTS = {"skills": 0.40, "experience": 0.25, "relevance": 0.15, "education": 0.10, "assessments": 0.10}
ASSESSMENT_NEUTRAL = 0.5          # no reasoning-test scores on file: neutral, flagged, never a penalty to 0
HIRE_TYPES = ("Saudi", "Expat")   # T_IIR_ARIF_CANDIDATE.SAUDI_EXPAT values (DECISIONS ADR-010)


@dataclass
class JobSpec:
    title: str = ""
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    min_years: float = 0.0
    min_gpa: float | None = None           # GPA scale 1-4; below it adds a flag (not a hard filter)
    degree_level: int = 0                  # 0 none, 1 diploma, 2 bachelor, 3 master, 4 phd
    majors: list[str] = field(default_factory=list)
    hire_type: str | None = None           # requisition is for Saudi or Expat hire: hard filter, never scored
    locations: list[str] = field(default_factory=list)   # CANDIDATE_FLAG values (AOC, ASC, ...): hard filter
    title_keywords: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    doc_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "JobSpec":
        d = dict(d or {})
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        spec = cls(**known)
        spec.weights = normalize_weights(spec.weights)
        spec.hire_type = normalize_hire_type(spec.hire_type)
        return spec


def normalize_hire_type(v: str | None) -> str | None:
    if not v:
        return None
    s = str(v).strip().lower()
    if s.startswith("saudi") or s in ("local", "national"):
        return "Saudi"
    if s.startswith("expat") or s in ("international", "foreign"):
        return "Expat"
    return None  # "any" / unknown


def normalize_weights(w: dict | None) -> dict[str, float]:
    merged = dict(DEFAULT_WEIGHTS)
    for k, v in (w or {}).items():
        if k in merged and v is not None:
            merged[k] = max(0.0, float(v))
    total = sum(merged.values()) or 1.0
    return {k: round(v / total, 4) for k, v in merged.items()}


def _skill_score(spec: JobSpec, cand_skills: list[str]) -> tuple[float, list[str], list[str]]:
    have = {canonical(s) for s in cand_skills}
    matched, missing = [], []
    for s in spec.required_skills:
        (matched if canonical(s) in have else missing).append(s)
    pref_hit = [s for s in spec.preferred_skills if canonical(s) in have]
    if spec.required_skills:
        base = len(matched) / len(spec.required_skills)
    elif spec.preferred_skills:
        base = len(pref_hit) / len(spec.preferred_skills)
    else:
        base = 1.0
    bonus = 0.1 * (len(pref_hit) / len(spec.preferred_skills)) if spec.preferred_skills and spec.required_skills else 0
    return min(1.0, base + bonus), matched + [p for p in pref_hit if p not in matched], missing


def _experience_score(spec: JobSpec, years: float | None) -> float:
    y = float(years or 0)
    if spec.min_years <= 0:
        return 1.0 if y > 0 else 0.5
    return min(y / spec.min_years, 1.0)


def _relevance_score(spec: JobSpec, cand: dict) -> float:
    kws = [k for k in (spec.title_keywords or ([spec.title] if spec.title else [])) if k]
    if not kws:
        return 1.0
    kw_tokens = set().union(*(tokens(k) for k in kws))
    if not kw_tokens:
        return 1.0
    titles = [(cand.get("last_job_title"), 1.0)] + [
        (" ".join(filter(None, {e.get("job_title"), e.get("norm_title")})), float(e.get("years_experience") or 0))
        for e in cand.get("experience", [])]
    best, weighted, total_years = 0.0, 0.0, 0.0
    for title, yrs in titles:
        overlap = len(tokens(title) & kw_tokens) / len(kw_tokens) if title else 0.0
        best = max(best, overlap)
        if yrs:
            weighted += overlap * yrs
            total_years += yrs
    years_component = weighted / total_years if total_years else 0.0
    return round(0.7 * best + 0.3 * years_component, 4)


def _education_score(spec: JobSpec, cand: dict) -> float:
    level = max([degree_level(cand.get("highest_degree"))]
                + [e.get("level") or degree_level(e.get("degree")) for e in cand.get("education", [])])
    if spec.degree_level <= 0:
        deg = 1.0
    elif level >= spec.degree_level:
        deg = 1.0
    elif level == spec.degree_level - 1:
        deg = 0.5
    else:
        deg = 0.0
    if not spec.majors:
        return deg
    majors = [cand.get("primary_major")] + [e.get("major") for e in cand.get("education", [])]
    majors = [m for m in majors if m]
    major_ok = any(fuzzy_match(m, majors, threshold=0.5) for m in spec.majors)
    return round(0.6 * deg + 0.4 * (1.0 if major_ok else 0.0), 4)


def _assessment_score(cand: dict) -> tuple[float, bool]:
    """Mean of the inductive / numerical / verbal reasoning scores (0-100) on file. (score, has_any)."""
    vals = [v for v in (cand.get("assessments") or {}).values() if isinstance(v, (int, float))]
    if not vals:
        return ASSESSMENT_NEUTRAL, False
    return sum(vals) / len(vals) / 100.0, True


def passes_filters(spec: JobSpec, cand: dict) -> bool:
    """Requisition hard filters (hire type, location). Applied before ranking, never part of the score."""
    if spec.hire_type and cand.get("hire_type") and cand["hire_type"] != spec.hire_type:
        return False
    if spec.locations and cand.get("location") not in spec.locations:
        return False
    return True


def score_candidate(spec: JobSpec, cand: dict, must_have: list[str] | None = None) -> dict:
    skills, matched, missing = _skill_score(spec, cand.get("skills", []))
    assess, has_assess = _assessment_score(cand)
    breakdown = {
        "skills": round(skills, 4),
        "experience": round(_experience_score(spec, cand.get("total_experience")), 4),
        "relevance": _relevance_score(spec, cand),
        "education": _education_score(spec, cand),
        "assessments": round(assess, 4),
    }
    w = normalize_weights(spec.weights)
    score = round(100 * sum(w[k] * breakdown[k] for k in CRITERIA), 1)
    flags = []
    have = {canonical(s) for s in cand.get("skills", [])}
    for m in (must_have or []):
        if canonical(m) not in have:
            flags.append(f"missing_must_have:{m}")
    if spec.min_years and float(cand.get("total_experience") or 0) < spec.min_years:
        flags.append("below_min_years")
    if not has_assess and w["assessments"] > 0:
        flags.append("no_assessment")
    if spec.hire_type and cand.get("hire_type") != spec.hire_type:
        flags.append("hire_type_mismatch")
    if spec.locations and cand.get("location") not in spec.locations:
        flags.append("location_mismatch")
    if cand.get("status_included") is False:
        flags.append("status_not_open")
    if spec.min_gpa and cand.get("gpa") is not None and cand["gpa"] < spec.min_gpa:
        flags.append("below_min_gpa")
    return {
        "candidate_id": cand["candidate_id"],
        "ats_id": cand.get("ats_id"),
        "full_name": cand.get("full_name"),
        "location": cand.get("location"),
        "hire_type": cand.get("hire_type"),
        "last_job_title": cand.get("last_job_title"),
        "total_experience": cand.get("total_experience"),
        "score": score,
        "breakdown": breakdown,
        "matched_skills": matched,
        "missing_skills": missing,
        "flags": flags,
    }


def rank(spec: JobSpec, candidates: list[dict], must_have: list[str] | None = None) -> list[dict]:
    results = [score_candidate(spec, c, must_have) for c in candidates]
    results.sort(key=lambda r: (-r["score"], -float(r.get("total_experience") or 0), r["candidate_id"]))
    return results


def band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "strong"
    if score >= 50:
        return "partial"
    return "weak"


__all__ = ["JobSpec", "CRITERIA", "DEFAULT_WEIGHTS", "HIRE_TYPES", "normalize_weights", "normalize_hire_type",
           "passes_filters", "score_candidate", "rank", "band", "norm"]
