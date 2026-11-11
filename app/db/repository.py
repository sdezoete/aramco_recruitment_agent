"""All SQL for the app lives here. Parameterized queries only; schema is fixed (docs/DATA_MODEL.md).

Only AgentMemory is written to. Every other table is read-only.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

import pyodbc

_CHUNK = 500  # SQL Server allows ~2100 parameters per statement

CANDIDATE_COLS = ("candidate_id", "full_name", "location", "total_experience", "highest_degree",
                  "primary_major", "last_job_title", "last_company", "summary")


def _chunks(ids: list[int]) -> Iterable[list[int]]:
    for i in range(0, len(ids), _CHUNK):
        yield ids[i:i + _CHUNK]


def _rows(cur: pyodbc.Cursor) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class Repository:
    def __init__(self, conn: pyodbc.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ basics
    def ping(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT DB_NAME() AS db, (SELECT COUNT(*) FROM dbo.Candidate) AS candidates")
        return _rows(cur)[0]

    def skills(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT s.skill_id, s.skill_name, COUNT(cs.candidate_id) AS candidates "
            "FROM dbo.Skill s LEFT JOIN dbo.CandidateSkill cs ON cs.skill_id = s.skill_id "
            "GROUP BY s.skill_id, s.skill_name ORDER BY candidates DESC, s.skill_name")
        return _rows(cur)

    # ------------------------------------------------------------------ search
    def search_candidate_ids(self, *, text: str | None = None, skill_ids: list[int] | None = None,
                             skills_all: bool = False, min_years: float | None = None,
                             max_years: float | None = None, degree: str | None = None,
                             major: str | None = None, location: str | None = None,
                             certification: str | None = None, limit: int = 10) -> tuple[int, list[int]]:
        where, params = ["1=1"], []
        if text:
            like = f"%{text}%"
            where.append("(c.summary LIKE ? OR c.last_job_title LIKE ? OR c.primary_major LIKE ? "
                         "OR EXISTS (SELECT 1 FROM dbo.Experience e WHERE e.candidate_id = c.candidate_id "
                         "AND e.job_title LIKE ?))")
            params += [like] * 4
        if skill_ids:
            ph = ",".join("?" * len(skill_ids))
            need = len(set(skill_ids)) if skills_all else 1
            where.append(f"c.candidate_id IN (SELECT candidate_id FROM dbo.CandidateSkill WHERE skill_id IN ({ph}) "
                         "GROUP BY candidate_id HAVING COUNT(DISTINCT skill_id) >= ?)")
            params += list(skill_ids) + [need]
        if min_years is not None:
            where.append("c.total_experience >= ?")
            params.append(min_years)
        if max_years is not None:
            where.append("c.total_experience <= ?")
            params.append(max_years)
        if degree:
            where.append("(c.highest_degree LIKE ? OR EXISTS (SELECT 1 FROM dbo.Education ed "
                         "WHERE ed.candidate_id = c.candidate_id AND ed.degree LIKE ?))")
            params += [f"%{degree}%"] * 2
        if major:
            where.append("(c.primary_major LIKE ? OR EXISTS (SELECT 1 FROM dbo.Education ed "
                         "WHERE ed.candidate_id = c.candidate_id AND ed.major LIKE ?))")
            params += [f"%{major}%"] * 2
        if location:
            where.append("c.location LIKE ?")
            params.append(f"%{location}%")
        if certification:
            where.append("EXISTS (SELECT 1 FROM dbo.Certification ce WHERE ce.candidate_id = c.candidate_id "
                         "AND ce.name LIKE ?)")
            params.append(f"%{certification}%")
        sql_where = " AND ".join(where)
        cur = self.conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM dbo.Candidate c WHERE {sql_where}", params)
        total = cur.fetchone()[0]
        cur.execute(f"SELECT TOP (?) c.candidate_id FROM dbo.Candidate c WHERE {sql_where} "
                    "ORDER BY c.total_experience DESC, c.candidate_id", [int(limit)] + params)
        return total, [r[0] for r in cur.fetchall()]

    def candidate_ids_with_any_skill(self, skill_ids: list[int], limit: int) -> list[int]:
        if not skill_ids:
            return []
        ph = ",".join("?" * len(skill_ids))
        cur = self.conn.cursor()
        cur.execute(f"SELECT TOP (?) candidate_id FROM dbo.CandidateSkill WHERE skill_id IN ({ph}) "
                    "GROUP BY candidate_id ORDER BY COUNT(*) DESC", [int(limit)] + list(skill_ids))
        return [r[0] for r in cur.fetchall()]

    def all_candidate_ids(self, limit: int) -> list[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT TOP (?) candidate_id FROM dbo.Candidate ORDER BY candidate_id", [int(limit)])
        return [r[0] for r in cur.fetchall()]

    # ------------------------------------------------------------------ profiles
    def profiles(self, ids: list[int]) -> dict[int, dict]:
        """Full profiles keyed by candidate_id, in one round-trip per table per chunk."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        out: dict[int, dict] = {}
        cur = self.conn.cursor()
        for chunk in _chunks(ids):
            ph = ",".join("?" * len(chunk))
            cur.execute(f"SELECT {', '.join(CANDIDATE_COLS)} FROM dbo.Candidate WHERE candidate_id IN ({ph})", chunk)
            for r in _rows(cur):
                r.update(skills=[], experience=[], education=[], certifications=[])
                out[r["candidate_id"]] = r
            cur.execute("SELECT cs.candidate_id, s.skill_name FROM dbo.CandidateSkill cs "
                        f"JOIN dbo.Skill s ON s.skill_id = cs.skill_id WHERE cs.candidate_id IN ({ph}) "
                        "ORDER BY s.skill_name", chunk)
            for cid, name in cur.fetchall():
                if cid in out and name:
                    out[cid]["skills"].append(name)
            cur.execute("SELECT candidate_id, job_title, company, location, years_experience FROM dbo.Experience "
                        f"WHERE candidate_id IN ({ph}) ORDER BY years_experience DESC", chunk)
            for r in _rows(cur):
                if r["candidate_id"] in out:
                    out[r.pop("candidate_id")]["experience"].append(r)
            cur.execute("SELECT candidate_id, institute, major, degree, gpa FROM dbo.Education "
                        f"WHERE candidate_id IN ({ph})", chunk)
            for r in _rows(cur):
                if r["candidate_id"] in out:
                    out[r.pop("candidate_id")]["education"].append(r)
            cur.execute(f"SELECT candidate_id, name FROM dbo.Certification WHERE candidate_id IN ({ph})", chunk)
            for cid, name in cur.fetchall():
                if cid in out and name:
                    out[cid]["certifications"].append(name)
        return out

    # ------------------------------------------------------------------ analytics
    def pool_stats(self, metric: str, candidate_ids: list[int] | None = None) -> list[dict]:
        scope, params = "", []
        if candidate_ids:
            ids = [int(i) for i in candidate_ids][:_CHUNK]
            scope = f" AND c.candidate_id IN ({','.join('?' * len(ids))})"
            params = ids
        queries = {
            "skill_supply": "SELECT s.skill_name AS label, COUNT(*) AS value FROM dbo.CandidateSkill cs "
                            "JOIN dbo.Skill s ON s.skill_id = cs.skill_id JOIN dbo.Candidate c "
                            f"ON c.candidate_id = cs.candidate_id WHERE 1=1{scope} "
                            "GROUP BY s.skill_name ORDER BY value DESC",
            "experience_distribution":
                "SELECT label, COUNT(*) AS value FROM (SELECT CASE WHEN c.total_experience IS NULL THEN 'unknown' "
                "WHEN c.total_experience < 2 THEN '0-2' WHEN c.total_experience < 5 THEN '2-5' "
                "WHEN c.total_experience < 10 THEN '5-10' ELSE '10+' END AS label FROM dbo.Candidate c "
                f"WHERE 1=1{scope}) x GROUP BY label",
            "degree_mix": "SELECT COALESCE(c.highest_degree, 'unknown') AS label, COUNT(*) AS value "
                          f"FROM dbo.Candidate c WHERE 1=1{scope} GROUP BY c.highest_degree ORDER BY value DESC",
            "major_mix": "SELECT COALESCE(c.primary_major, 'unknown') AS label, COUNT(*) AS value "
                         f"FROM dbo.Candidate c WHERE 1=1{scope} GROUP BY c.primary_major ORDER BY value DESC",
            "location_mix": "SELECT COALESCE(c.location, 'unknown') AS label, COUNT(*) AS value "
                            f"FROM dbo.Candidate c WHERE 1=1{scope} GROUP BY c.location ORDER BY value DESC",
            "certification_mix": "SELECT ce.name AS label, COUNT(*) AS value FROM dbo.Certification ce "
                                 f"JOIN dbo.Candidate c ON c.candidate_id = ce.candidate_id WHERE 1=1{scope} "
                                 "GROUP BY ce.name ORDER BY value DESC",
        }
        if metric not in queries:
            raise ValueError(f"unknown metric {metric}")
        cur = self.conn.cursor()
        cur.execute(queries[metric], params)
        rows = _rows(cur)
        if metric == "experience_distribution":
            order = {"0-2": 0, "2-5": 1, "5-10": 2, "10+": 3, "unknown": 4}
            rows.sort(key=lambda r: order.get(r["label"], 9))
        return rows

    # ------------------------------------------------------------------ AgentMemory (the only writable table)
    def memory_get(self, chat_id: str, key: str):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM dbo.AgentMemory WHERE chat_id = ? AND [key] = ?", [chat_id, key])
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return row[0]

    def memory_delete_chat(self, chat_id: str) -> int:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM dbo.AgentMemory WHERE chat_id = ?", [chat_id])
        return cur.rowcount

    def memory_set(self, chat_id: str, key: str, value) -> None:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
        cur = self.conn.cursor()
        cur.execute("UPDATE dbo.AgentMemory SET value = ?, updated_at = ? WHERE chat_id = ? AND [key] = ?",
                    [text, datetime.now(), chat_id, key])
        if cur.rowcount == 0:
            cur.execute("INSERT INTO dbo.AgentMemory (chat_id, [key], value, updated_at) VALUES (?, ?, ?, ?)",
                        [chat_id, key, text, datetime.now()])
