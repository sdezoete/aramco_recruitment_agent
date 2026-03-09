from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class SQLQuery:
    sql: str
    params: list[Any]


def build_in_clause_params(values: Sequence[Any]) -> tuple[str, list[Any]]:
    """Build placeholders for safe SQL IN clauses."""
    items = list(values)
    if not items:
        return "(NULL)", []
    placeholders = ", ".join(["?"] * len(items))
    return f"({placeholders})", items
