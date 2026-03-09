from __future__ import annotations

from pydantic import BaseModel, Field


class PlanFilter(BaseModel):
    field: str
    operator: str
    value: str | float | int | list[str]


class RankingFeature(BaseModel):
    name: str
    weight: float


class QueryPlan(BaseModel):
    filters: list[PlanFilter] = Field(default_factory=list)
    joins: list[str] = Field(default_factory=list)
    ranking_features: list[RankingFeature] = Field(default_factory=list)
    text_query_terms: list[str] = Field(default_factory=list)
    limit: int = 50
