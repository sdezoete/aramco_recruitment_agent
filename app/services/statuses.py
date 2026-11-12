"""Application status reference list: data/reference/application_statuses.csv.

One row per APPLICATION_STATUS_CODE: code, status, stage, stage_order, include_in_matching (Y/N).
`include_in_matching=N` means candidates whose furthest application has that code are left out of
match_candidates by default (e.g. Hired, Offer Accepted). The recruiter can override per request.

The current file is a PLACEHOLDER; the user will replace it with the real list (60+ codes). Unknown codes
(in the DB but not in the file) are treated as included and sort last.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import ROOT

log = logging.getLogger("ra.statuses")
STATUS_FILE = ROOT / "data" / "reference" / "application_statuses.csv"


@dataclass(frozen=True)
class Status:
    code: int
    status: str
    stage: str
    stage_order: int
    include: bool


@lru_cache(maxsize=4)
def load(path: Path = STATUS_FILE) -> dict[int, Status]:
    out: dict[int, Status] = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for n, row in enumerate(csv.DictReader(f), 2):
                try:
                    code = int(row["code"])
                    out[code] = Status(code, row["status"].strip(), (row.get("stage") or "").strip() or "Other",
                                       int(row.get("stage_order") or 99),
                                       (row.get("include_in_matching") or "Y").strip().upper() != "N")
                except (KeyError, ValueError) as e:
                    log.warning("%s line %d skipped: %s", path.name, n, e)
    except FileNotFoundError:
        log.warning("%s not found: no statuses are excluded by default", path)
    return out


def excluded_codes() -> list[int]:
    return sorted(c for c, s in load().items() if not s.include)


def info(code) -> Status | None:
    try:
        return load().get(int(code))
    except (TypeError, ValueError):
        return None


def sort_key(code) -> tuple[int, int]:
    s = info(code)
    return (s.stage_order if s else 999, int(code) if isinstance(code, int) else 99999)
