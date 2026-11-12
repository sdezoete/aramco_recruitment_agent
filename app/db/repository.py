"""All SQL for the app lives here. Parameterized queries only.

Tables: the server's T_IIR_ARIF_* tables (docs/DATA_DICTIONARY.md), read-only, plus the app's own
T_IIR_ARIF_AGENT_MEMORY (sql/02_agent_memory.sql), the only table the app writes to.

- Ids: the app's `candidate_id` everywhere (tools, UI, memory) is ARIF_ID, the PK the child tables join on.
  CANDIDATE_ID (unique ATS id) is exposed as `ats_id`, and can be looked up.
- Original columns only: the NORM_* columns are not used (user decision 2026-11-11). Raw skill spellings are
  grouped in Python by their canonical form (services/normalize.py), so "MS Excel" and "Excel" are one skill.
- Never selected: NATIONAL_ID, GENDER, COUNTRY (nationality; protected). TEXT_TOKENS only inside WHERE.
- Volume: the server holds 350k-500k candidates. Pools are pre-filtered and capped in SQL; never load the
  whole table into Python.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from typing import Iterable

import pyodbc

from app.services import statuses
from app.services.normalize import DEGREE_NAMES, canonical, degree_level, is_present, norm, parse_date

log = logging.getLogger("ra.repo")

_CHUNK = 500  # SQL Server allows ~2100 parameters per statement
_VOCAB_TTL = 600.0
_vocab_cache: tuple[float, dict[str, dict]] | None = None
_memory_missing_logged = False

C = "dbo.T_IIR_ARIF_CANDIDATE"
EDU = "dbo.T_IIR_ARIF_EDUCATION"
EXP = "dbo.T_IIR_ARIF_EXPERIENCE"
SKL = "dbo.T_IIR_ARIF_SKILLS"
MEM = "dbo.T_IIR_ARIF_AGENT_MEMORY"

YEARS_SQL = "TRY_CAST(c.YEARS_OF_EXPERIENCE AS decimal(6,1))"
GPA_SQL = "TRY_CAST(c.GPA AS decimal(4,2))"
SKILL_SQL = "s.ORG_SKILL"   # compared raw (sargable: an index on ORG_SKILL can be used); variants keep exact spellings
# Degree level from the original DEGREE text (English or Arabic), 0 = unknown. Mirrors normalize.degree_level.
DEGREE_LEVEL_SQL = (
    "CASE WHEN {c} LIKE '%phd%' OR {c} LIKE '%ph.d%' OR {c} LIKE '%doctor%' OR {c} LIKE N'%دكتوراه%' THEN 4 "
    "WHEN {c} LIKE '%master%' OR {c} LIKE '%mba%' OR {c} LIKE '%m.sc%' OR {c} LIKE '%msc%' OR {c} LIKE '%m.eng%' "
    "OR {c} LIKE '%meng%' OR {c} LIKE N'%ماجستير%' THEN 3 "
    "WHEN {c} LIKE '%bachelor%' OR {c} LIKE '%b.sc%' OR {c} LIKE '%bsc%' OR {c} LIKE '%beng%' OR {c} LIKE '%b.eng%' "
    "OR {c} LIKE '%bba%' OR {c} LIKE N'%بكالوريوس%' THEN 2 "
    "WHEN {c} LIKE '%diploma%' OR {c} LIKE '%associate%' OR {c} LIKE N'%دبلوم%' THEN 1 ELSE 0 END")

CANDIDATE_SELECT = (
    "SELECT c.ARIF_ID, c.CANDIDATE_ID, c.GIVENNAME, c.MIDDLENAME, c.SURNAME, c.CURRENT_EMPLOYER, "
    "c.CURRENT_JOB_TITLE, c.YEARS_OF_EXPERIENCE, c.SAUDI_EXPAT, c.GPA, c.SOURCE_OF_APPLICATION, "
    "c.HIGHEST_JOB_REQ_ID, c.HIGHEST_APPLICATION_STATUS, c.APPLICATION_STATUS_CODE, c.RESUME_PROCESSED, "
    "c.CANDIDATE_FLAG, c.INDREASON, c.NUMREASON, c.VERBREASON, c.SUMMARY, c.LAST_MODIFIED "
    f"FROM {C} c")


def _chunks(ids: list[int]) -> Iterable[list[int]]:
    for i in range(0, len(ids), _CHUNK):
        yield ids[i:i + _CHUNK]


def _rows(cur: pyodbc.Cursor) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def to_number(v) -> float | None:
    """'5' / '5.0' / ' 7 ' -> number; anything else -> None (several numeric columns are text)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def gpa_value(v) -> float | None:
    """GPA on the 1-4 scale (4 = highest). Accepts '3.45' or '3.45/4'; out-of-range values -> None."""
    if v is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(v))
    n = float(m.group(0).replace(",", ".")) if m else None
    return round(n, 2) if n is not None and 0 < n <= 4 else None


def _score_0_100(v) -> int | None:
    n = to_number(v)
    return int(round(n)) if n is not None and 0 <= n <= 100 else None


def full_name(given, middle, surname) -> str:
    return " ".join(p.strip() for p in (given, middle, surname) if p and p.strip()) or "(no name)"


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, (date, datetime)) else None


def _recency(start: str | None, end: str | None) -> tuple:
    """Sort key: current entries first, then by end date, then start date (newest first)."""
    e, s = parse_date(end), parse_date(start)
    return (0 if is_present(end) else 1, -(e[0] * 12 + e[1]) if e else 0, -(s[0] * 12 + s[1]) if s else 0)


class Repository:
    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ basics
    def ping(self) -> dict:
        cur = self.conn.cursor()
        cur.execute(f"SELECT DB_NAME() AS db, (SELECT COUNT(*) FROM {C}) AS candidates, "
                    "CASE WHEN OBJECT_ID(?) IS NULL THEN 0 ELSE 1 END AS memory_table", [MEM])
        return _rows(cur)[0]

    # ------------------------------------------------------------------ skill vocabulary (raw ORG_SKILL, grouped)
    def _vocab(self) -> dict[str, dict]:
        """canonical key -> {skill_name (most common spelling), candidates, variants[]}. Cached."""
        global _vocab_cache
        now = time.monotonic()
        if _vocab_cache and now - _vocab_cache[0] < _VOCAB_TTL:
            return _vocab_cache[1]
        cur = self.conn.cursor()
        cur.execute(f"SELECT MIN({SKILL_SQL} COLLATE Latin1_General_BIN) AS raw, COUNT(*) AS n FROM {SKL} s "  # BIN: capitals sort first
                    "WHERE s.ORG_SKILL IS NOT NULL AND LTRIM(RTRIM(s.ORG_SKILL)) <> '' GROUP BY s.ORG_SKILL")
        groups: dict[str, dict] = {}
        for raw, n in cur.fetchall():
            key = canonical(raw)
            if not key:
                continue
            # display name: prefer the plain spelling ("Excel" over "Advanced Excel"), then capitalised,
            # then the most common one
            rank = (norm(raw) == key, raw.strip()[:1].isupper(), n)
            g = groups.setdefault(key, {"skill_name": raw.strip(), "rank": rank, "candidates": 0, "variants": []})
            g["variants"].append(raw)
            g["candidates"] += n
            if rank > g["rank"]:
                g["skill_name"], g["rank"] = raw.strip(), rank
        _vocab_cache = (now, groups)
        return groups

    def skills(self) -> list[dict]:
        """Skill vocabulary with (approximate) candidate counts, most common first."""
        rows = [{"skill_name": g["skill_name"], "candidates": g["candidates"], "variants": len(g["variants"])}
                for g in self._vocab().values()]
        rows.sort(key=lambda r: (-r["candidates"], r["skill_name"]))
        return rows

    def skill_variants(self, names: list[str]) -> list[list[str]]:
        """For each skill name, every raw ORG_SKILL spelling of it (falls back to the name itself)."""
        vocab = self._vocab()
        return [vocab.get(canonical(n), {}).get("variants") or [n] for n in names]

    def display_skill(self, raw: str) -> str:
        g = self._vocab().get(canonical(raw))
        return g["skill_name"] if g else raw.strip()

    # ------------------------------------------------------------------ lookups
    def arif_ids_for_ats(self, ats_ids: list[int]) -> dict[int, int]:
        """ATS CANDIDATE_ID (unique) -> ARIF_ID."""
        ids = [int(i) for i in ats_ids][:_CHUNK]
        if not ids:
            return {}
        cur = self.conn.cursor()
        cur.execute(f"SELECT CANDIDATE_ID, ARIF_ID FROM {C} WHERE CANDIDATE_ID IN ({','.join('?' * len(ids))})", ids)
        return {a: b for a, b in cur.fetchall()}

    # ------------------------------------------------------------------ filters shared by search and pools
    @staticmethod
    def _filters(where: list[str], params: list, *, hire_type: str | None = None,
                 locations: list[str] | None = None, statuses_in: list[str] | None = None,
                 exclude_statuses: list[str] | None = None, exclude_codes: list[int] | None = None,
                 min_gpa: float | None = None) -> None:
        if hire_type:
            where.append("c.SAUDI_EXPAT = ?")
            params.append(hire_type)
        if locations:
            where.append(f"c.CANDIDATE_FLAG IN ({','.join('?' * len(locations))})")
            params += list(locations)
        if statuses_in:
            where.append(f"c.HIGHEST_APPLICATION_STATUS IN ({','.join('?' * len(statuses_in))})")
            params += list(statuses_in)
        if exclude_statuses:
            where.append("(c.HIGHEST_APPLICATION_STATUS IS NULL OR c.HIGHEST_APPLICATION_STATUS NOT IN "
                         f"({','.join('?' * len(exclude_statuses))}))")
            params += list(exclude_statuses)
        if exclude_codes:
            where.append("(c.APPLICATION_STATUS_CODE IS NULL OR c.APPLICATION_STATUS_CODE NOT IN "
                         f"({','.join('?' * len(exclude_codes))}))")
            params += [int(x) for x in exclude_codes]
        if min_gpa is not None:
            where.append(f"{GPA_SQL} >= ?")
            params.append(min_gpa)

    def _skill_clauses(self, where: list[str], params: list, skills: list[str], mode_all: bool) -> None:
        groups = self.skill_variants(list(dict.fromkeys(skills)))
        if mode_all:
            for variants in groups:
                where.append(f"c.ARIF_ID IN (SELECT s.ARIF_ID FROM {SKL} s WHERE {SKILL_SQL} IN "
                             f"({','.join('?' * len(variants))}))")
                params += variants
        else:
            flat = list(dict.fromkeys(v for g in groups for v in g))
            where.append(f"c.ARIF_ID IN (SELECT s.ARIF_ID FROM {SKL} s WHERE {SKILL_SQL} IN "
                         f"({','.join('?' * len(flat))}))")
            params += flat

    # ------------------------------------------------------------------ search
    def search_candidate_ids(self, *, text: str | None = None, skills: list[str] | None = None,
                             skills_all: bool = False, min_years: float | None = None,
                             max_years: float | None = None, degree: str | None = None,
                             major: str | None = None, limit: int = 10, **filters) -> tuple[int, list[int]]:
        where, params = ["1=1"], []
        if text:
            # one set-based subquery: an OR across tables would force a nested-loop scan (128 s at 100k rows)
            like = f"%{text}%"
            where.append(f"c.ARIF_ID IN (SELECT t.ARIF_ID FROM {C} t WHERE t.CURRENT_JOB_TITLE LIKE ? "
                         f"OR t.SUMMARY LIKE ? OR t.TEXT_TOKENS LIKE ? UNION SELECT e.ARIF_ID FROM {EXP} e "
                         "WHERE e.TITLE LIKE ?)")
            params += [like] * 4
        if skills:
            self._skill_clauses(where, params, skills, skills_all)
        if min_years is not None:
            where.append(f"{YEARS_SQL} >= ?")
            params.append(min_years)
        if max_years is not None:
            where.append(f"{YEARS_SQL} <= ?")
            params.append(max_years)
        if degree:
            lvl = degree_level(degree)
            if lvl:  # "at least this level"
                where.append(f"c.ARIF_ID IN (SELECT ed.ARIF_ID FROM {EDU} ed WHERE "
                             f"{DEGREE_LEVEL_SQL.format(c='ed.DEGREE')} >= ?)")
                params.append(lvl)
            else:
                where.append(f"c.ARIF_ID IN (SELECT ed.ARIF_ID FROM {EDU} ed WHERE ed.DEGREE LIKE ?)")
                params.append(f"%{degree}%")
        if major:
            where.append(f"c.ARIF_ID IN (SELECT ed.ARIF_ID FROM {EDU} ed WHERE ed.MAJOR LIKE ?)")
            params.append(f"%{major}%")
        self._filters(where, params, **filters)
        sql_where = " AND ".join(where)
        cur = self.conn.cursor()
        cur.execute(f"SELECT TOP (?) c.ARIF_ID, COUNT(*) OVER () AS total FROM {C} c WHERE {sql_where} "
                    f"ORDER BY {YEARS_SQL} DESC, c.ARIF_ID", [int(limit)] + params)
        rows = cur.fetchall()
        return (rows[0][1] if rows else 0), [r[0] for r in rows]

    def candidate_ids_with_any_skill(self, skills: list[str], limit: int, **filters) -> list[int]:
        """Pool for matching: candidates with any of the skills, most matching spellings first, capped."""
        if not skills:
            return []
        flat = list(dict.fromkeys(v for g in self.skill_variants(list(dict.fromkeys(skills))) for v in g))
        where, params = [f"{SKILL_SQL} IN ({','.join('?' * len(flat))})"], list(flat)
        self._filters(where, params, **filters)
        cur = self.conn.cursor()
        cur.execute(f"SELECT TOP (?) s.ARIF_ID FROM {SKL} s JOIN {C} c ON c.ARIF_ID = s.ARIF_ID "
                    f"WHERE {' AND '.join(where)} GROUP BY s.ARIF_ID "
                    f"ORDER BY COUNT(DISTINCT {SKILL_SQL}) DESC, MAX({YEARS_SQL}) DESC, s.ARIF_ID",
                    [int(limit)] + params)
        return [r[0] for r in cur.fetchall()]

    def all_candidate_ids(self, limit: int, **filters) -> list[int]:
        where, params = ["1=1"], []
        self._filters(where, params, **filters)
        cur = self.conn.cursor()
        cur.execute(f"SELECT TOP (?) c.ARIF_ID FROM {C} c WHERE {' AND '.join(where)} "
                    f"ORDER BY {YEARS_SQL} DESC, c.ARIF_ID", [int(limit)] + params)
        return [r[0] for r in cur.fetchall()]

    # ------------------------------------------------------------------ profiles
    @staticmethod
    def _id_batches(cur: pyodbc.Cursor, ids: list[int]) -> list[tuple[str, list]]:
        """IN-list for small id sets; for large ones a session temp table, so each child table is scanned
        once instead of once per 500-id chunk (2000 profiles at 100k rows: 1.9 s -> 0.8 s, ADR-014)."""
        if len(ids) <= _CHUNK:
            return [(",".join("?" * len(ids)), ids)]
        cur.execute("IF OBJECT_ID('tempdb..#ra_ids') IS NOT NULL DROP TABLE #ra_ids; "
                    "CREATE TABLE #ra_ids (ID int PRIMARY KEY)")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #ra_ids (ID) VALUES (?)", [[i] for i in ids])
        cur.fast_executemany = False
        return [("SELECT ID FROM #ra_ids", [])]

    def profiles(self, ids: list[int]) -> dict[int, dict]:
        """Full profiles keyed by ARIF_ID (the app's candidate_id), one round-trip per table."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        out: dict[int, dict] = {}
        if not ids:
            return out
        cur = self.conn.cursor()
        batches = self._id_batches(cur, ids)
        for ph, chunk in batches:
            cur.execute(f"{CANDIDATE_SELECT} WHERE c.ARIF_ID IN ({ph})", chunk)
            for r in _rows(cur):
                r = {k: _clean(v) for k, v in r.items()}
                st = statuses.info(r["APPLICATION_STATUS_CODE"])
                out[r["ARIF_ID"]] = {
                    "candidate_id": r["ARIF_ID"], "ats_id": r["CANDIDATE_ID"],
                    "full_name": full_name(r["GIVENNAME"], r["MIDDLENAME"], r["SURNAME"]),
                    "last_job_title": r["CURRENT_JOB_TITLE"], "last_company": r["CURRENT_EMPLOYER"],
                    "total_experience": to_number(r["YEARS_OF_EXPERIENCE"]),
                    "location": r["CANDIDATE_FLAG"], "hire_type": r["SAUDI_EXPAT"],
                    "gpa": gpa_value(r["GPA"]), "source": r["SOURCE_OF_APPLICATION"],
                    "application_status": r["HIGHEST_APPLICATION_STATUS"] or (st.status if st else None),
                    "status_code": r["APPLICATION_STATUS_CODE"], "job_req_id": r["HIGHEST_JOB_REQ_ID"],
                    "pipeline_stage": st.stage if st else None,
                    "status_included": st.include if st else True,
                    "resume_processed": r["RESUME_PROCESSED"] == 1,
                    "assessments": {"inductive": _score_0_100(r["INDREASON"]),
                                    "numerical": _score_0_100(r["NUMREASON"]),
                                    "verbal": _score_0_100(r["VERBREASON"])},
                    "summary": r["SUMMARY"], "last_modified": _iso(r["LAST_MODIFIED"]),
                    "skills": [], "experience": [], "education": [],
                    "highest_degree": None, "primary_major": None,
                }
            cur.execute(f"SELECT ARIF_ID, ORG_SKILL FROM {SKL} WHERE ARIF_ID IN ({ph})", chunk)
            seen: dict[int, set] = {}
            for aid, raw in cur.fetchall():
                raw = _clean(raw)
                key = canonical(raw)
                if aid in out and key and key not in seen.setdefault(aid, set()):
                    seen[aid].add(key)
                    out[aid]["skills"].append(self.display_skill(raw))
            cur.execute("SELECT ARIF_ID, TITLE, EMPLOYER, COUNTRY, YEARS_OF_EXPERIENCE, STARTDATE, ENDDATE "
                        f"FROM {EXP} WHERE ARIF_ID IN ({ph})", chunk)
            for r in _rows(cur):
                if r["ARIF_ID"] in out:
                    r = {k: _clean(v) for k, v in r.items()}
                    out[r["ARIF_ID"]]["experience"].append({
                        "job_title": r["TITLE"], "company": r["EMPLOYER"], "location": r["COUNTRY"],
                        "years_experience": r["YEARS_OF_EXPERIENCE"], "start": r["STARTDATE"], "end": r["ENDDATE"],
                        "current": is_present(r["ENDDATE"])})
            cur.execute(f"SELECT ARIF_ID, DEGREE, MAJOR, INSTITUTION, STARTDATE, ENDDATE FROM {EDU} "
                        f"WHERE ARIF_ID IN ({ph})", chunk)
            for r in _rows(cur):
                if r["ARIF_ID"] in out:
                    r = {k: _clean(v) for k, v in r.items()}
                    out[r["ARIF_ID"]]["education"].append({
                        "degree": r["DEGREE"], "level": degree_level(r["DEGREE"]), "major": r["MAJOR"],
                        "institute": r["INSTITUTION"], "start": r["STARTDATE"], "end": r["ENDDATE"]})
        if len(ids) > _CHUNK:
            cur.execute("DROP TABLE IF EXISTS #ra_ids")
        for p in out.values():
            p["skills"].sort(key=str.lower)
            p["experience"].sort(key=lambda e: _recency(e["start"], e["end"]))
            p["education"].sort(key=lambda e: _recency(e["start"], e["end"]))
            if p["education"]:
                top = max(p["education"], key=lambda e: e["level"])
                p["highest_degree"] = DEGREE_NAMES.get(top["level"]) or top["degree"]
                p["primary_major"] = top["major"]
            if p["total_experience"] is None and p["experience"]:
                p["total_experience"] = float(sum(e["years_experience"] or 0 for e in p["experience"]))
        return out

    # ------------------------------------------------------------------ analytics
    METRICS = ("skill_supply", "experience_distribution", "degree_mix", "major_mix", "location_mix",
               "status_mix", "stage_mix", "source_mix", "hire_type_mix")

    def pool_stats(self, metric: str, candidate_ids: list[int] | None = None) -> list[dict]:
        if metric not in self.METRICS:
            raise ValueError(f"unknown metric {metric}; use one of {', '.join(self.METRICS)}")
        scope, params = "", []
        if candidate_ids:
            ids = [int(i) for i in candidate_ids][:_CHUNK]
            scope = f" AND c.ARIF_ID IN ({','.join('?' * len(ids))})"
            params = ids
        level = DEGREE_LEVEL_SQL.format(c="ed.DEGREE")
        queries = {
            "skill_supply": f"SELECT {SKILL_SQL} AS label, COUNT(DISTINCT s.ARIF_ID) AS value FROM {SKL} s "
                            f"JOIN {C} c ON c.ARIF_ID = s.ARIF_ID WHERE s.ORG_SKILL IS NOT NULL{scope} "
                            "GROUP BY s.ORG_SKILL",
            "experience_distribution":
                f"SELECT label, COUNT(*) AS value FROM (SELECT CASE WHEN {YEARS_SQL} IS NULL THEN 'unknown' "
                f"WHEN {YEARS_SQL} < 2 THEN '0-2' WHEN {YEARS_SQL} < 5 THEN '2-5' "
                f"WHEN {YEARS_SQL} < 10 THEN '5-10' ELSE '10+' END AS label FROM {C} c "
                f"WHERE 1=1{scope}) x GROUP BY label",
            "degree_mix": f"SELECT lvl AS label, COUNT(*) AS value FROM (SELECT c.ARIF_ID, "
                          f"MAX({level}) AS lvl FROM {C} c LEFT JOIN {EDU} ed ON ed.ARIF_ID = c.ARIF_ID "
                          f"WHERE 1=1{scope} GROUP BY c.ARIF_ID) x GROUP BY lvl ORDER BY lvl DESC",
            "major_mix": f"SELECT TOP 30 LTRIM(RTRIM(ed.MAJOR)) AS label, COUNT(DISTINCT ed.ARIF_ID) AS value "
                         f"FROM {EDU} ed JOIN {C} c ON c.ARIF_ID = ed.ARIF_ID WHERE ed.MAJOR IS NOT NULL{scope} "
                         "GROUP BY LTRIM(RTRIM(ed.MAJOR)) ORDER BY value DESC",
            "location_mix": f"SELECT COALESCE(c.CANDIDATE_FLAG, 'unknown') AS label, COUNT(*) AS value "
                            f"FROM {C} c WHERE 1=1{scope} GROUP BY c.CANDIDATE_FLAG ORDER BY value DESC",
            "status_mix": f"SELECT c.APPLICATION_STATUS_CODE AS code, MAX(c.HIGHEST_APPLICATION_STATUS) AS label, "
                          f"COUNT(*) AS value FROM {C} c WHERE 1=1{scope} GROUP BY c.APPLICATION_STATUS_CODE",
            "source_mix": f"SELECT COALESCE(c.SOURCE_OF_APPLICATION, 'unknown') AS label, COUNT(*) AS value "
                          f"FROM {C} c WHERE 1=1{scope} GROUP BY c.SOURCE_OF_APPLICATION ORDER BY value DESC",
            "hire_type_mix": f"SELECT COALESCE(c.SAUDI_EXPAT, 'unknown') AS label, COUNT(*) AS value "
                             f"FROM {C} c WHERE 1=1{scope} GROUP BY c.SAUDI_EXPAT ORDER BY value DESC",
        }
        queries["stage_mix"] = queries["status_mix"]
        cur = self.conn.cursor()
        cur.execute(queries[metric], params)
        rows = _rows(cur)
        if metric == "skill_supply":  # group raw spellings into one skill
            agg: dict[str, dict] = {}
            for r in rows:
                key = canonical(r["label"])
                if key:
                    a = agg.setdefault(key, {"label": self.display_skill(r["label"]), "value": 0})
                    a["value"] += r["value"]
            return sorted(agg.values(), key=lambda r: -r["value"])
        if metric in ("status_mix", "stage_mix"):
            rows.sort(key=lambda r: statuses.sort_key(r["code"]))
            if metric == "status_mix":
                out = []
                for r in rows:
                    st = statuses.info(r["code"])
                    out.append({"label": r["label"] or (st.status if st else None) or f"code {r['code']}",
                                "value": r["value"], "code": r["code"]})
                return out
            stages: dict[str, int] = {}
            for r in rows:
                st = statuses.info(r["code"])
                name = st.stage if st else "Unknown"
                stages[name] = stages.get(name, 0) + r["value"]
            return [{"label": k, "value": v} for k, v in stages.items()]
        rows = [{"label": r["label"], "value": r["value"]} for r in rows]
        if metric == "experience_distribution":
            order = {"0-2": 0, "2-5": 1, "5-10": 2, "10+": 3, "unknown": 4}
            rows.sort(key=lambda r: order.get(r["label"], 9))
        if metric == "degree_mix":
            rows = [{"label": DEGREE_NAMES.get(r["label"], "unknown"), "value": r["value"]} for r in rows]
        return rows

    # ------------------------------------------------------------------ T_IIR_ARIF_AGENT_MEMORY (only writable table)
    def _memory(self, sql: str, params: list):
        """Run a memory statement. If the table is missing (not yet created on the server), log once and
        carry on: chat state then lives in process memory only."""
        global _memory_missing_logged
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
            return cur
        except pyodbc.ProgrammingError as e:
            if "42S02" not in str(e):
                raise
            if not _memory_missing_logged:
                log.warning("%s does not exist; chat state is kept in memory only. Run sql/02_agent_memory.sql.",
                            MEM)
                _memory_missing_logged = True
            return None

    def memory_get(self, chat_id: str, key: str):
        cur = self._memory(f"SELECT MEMORY_VALUE FROM {MEM} WHERE CHAT_ID = ? AND MEMORY_KEY = ?", [chat_id, key])
        row = cur.fetchone() if cur else None
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return row[0]

    def memory_delete_chat(self, chat_id: str) -> int:
        cur = self._memory(f"DELETE FROM {MEM} WHERE CHAT_ID = ?", [chat_id])
        return cur.rowcount if cur else 0

    def memory_set(self, chat_id: str, key: str, value) -> None:
        text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
        cur = self._memory(f"UPDATE {MEM} SET MEMORY_VALUE = ?, UPDATED_AT = SYSDATETIME() "
                           "WHERE CHAT_ID = ? AND MEMORY_KEY = ?", [text, chat_id, key])
        if cur is not None and cur.rowcount == 0:
            self._memory(f"INSERT INTO {MEM} (CHAT_ID, MEMORY_KEY, MEMORY_VALUE) VALUES (?, ?, ?)",
                         [chat_id, key, text])
