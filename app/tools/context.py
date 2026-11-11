"""Per-call tool context and per-chat state."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import Settings
from app.db.repository import Repository
from app.services.scoring import JobSpec


class ToolError(Exception):
    """A user/model-facing tool error; returned to the model as {"error": ...}."""


@dataclass
class ChatState:
    chat_id: str
    history: list[dict] = field(default_factory=list)   # wire messages (no system/developer)
    job_spec: dict | None = None
    shortlist: list[dict] | None = None                  # last match_candidates results
    block_seq: int = 0
    loaded: bool = False

    def load(self, repo: Repository) -> None:
        if self.loaded:
            return
        self.job_spec = self.job_spec or repo.memory_get(self.chat_id, "active_job_spec")
        self.shortlist = self.shortlist or repo.memory_get(self.chat_id, "last_shortlist")
        self.loaded = True

    def spec(self) -> JobSpec | None:
        return JobSpec.from_dict(self.job_spec) if self.job_spec else None


@dataclass
class ToolContext:
    repo: Repository
    settings: Settings
    chat: ChatState
    blocks: list[dict] = field(default_factory=list)

    def save_spec(self, spec: JobSpec) -> None:
        self.chat.job_spec = spec.to_dict()
        self.repo.memory_set(self.chat.chat_id, "active_job_spec", self.chat.job_spec)

    def save_shortlist(self, results: list[dict]) -> None:
        self.chat.shortlist = results
        self.repo.memory_set(self.chat.chat_id, "last_shortlist", results)

    def require_spec(self, override: dict | None = None) -> JobSpec:
        if override:
            base = dict(self.chat.job_spec or {})
            base.update({k: v for k, v in override.items() if v not in (None, [], "")})
            return JobSpec.from_dict(base)
        spec = self.chat.spec()
        if not spec:
            raise ToolError("No active job spec. Call set_job_spec first (from a JD document, pasted JD text, "
                            "or explicit requirements).")
        return spec
