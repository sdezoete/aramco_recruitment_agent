"""Settings: built-in defaults -> .env (next to the app) -> RA_<KEY> environment variables.

The app reads .env itself; .env values override machine environment variables of the same name,
and RA_<KEY> variables override both (used by tests and the mock LLM).
PRODUCTION=True enforces the rules in docs/AIRGAP_DEPLOYMENT_STANDARD.md section 4.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

_TRUE = {"1", "true", "yes", "on"}


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    return values


@dataclass
class Settings:
    PRODUCTION: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    TLS_CERT_FILE: str = ""
    TLS_KEY_FILE: str = ""
    TLS_ALLOW_SELF_SIGNED: bool = False

    DB_DRIVER: str = "ODBC Driver 17 for SQL Server"
    DB_SERVER: str = "localhost"
    DB_NAME: str = "recruitment"
    DB_TRUSTED_CONNECTION: bool = True
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_ENCRYPT: bool = False
    DB_TRUST_SERVER_CERTIFICATE: bool = True

    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_DISPLAY_NAME: str = "ARIF"
    LLM_VERIFY_SSL: bool = True
    LLM_CA_FILE: str = ""
    LLM_TIMEOUT_SECONDS: float = 120.0
    LLM_MAX_TOKENS: int = 4096
    LLM_MAX_RETRIES: int = 2
    LLM_REASONING_EFFORT: str = "medium"   # harmony "Reasoning: <effort>"; also sent as reasoning_effort if accepted
    LLM_IGNORE_PROXY: bool = True

    AGENT_MAX_STEPS: int = 8
    MATCH_MAX_POOL: int = 2000

    DOCS_DIR: str = "data/docs"

    # Not settings: bookkeeping for the startup banner.
    sources: dict = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ helpers
    @property
    def llm_label(self) -> str:
        """What the UI shows for the model."""
        if self.PRODUCTION:
            return self.LLM_DISPLAY_NAME or "ARIF"
        return f"{self.LLM_MODEL or 'no model'} (local dev)"

    @property
    def docs_path(self) -> Path:
        p = Path(self.DOCS_DIR)
        return p if p.is_absolute() else ROOT / p

    def masked(self) -> dict:
        out = {}
        for f in fields(self):
            if f.name == "sources":
                continue
            v = getattr(self, f.name)
            if f.name in ("LLM_API_KEY", "DB_PASSWORD") and v:
                v = v[:3] + "…" + f"({len(v)} chars)"
            out[f.name] = v
        return out

    def problems(self) -> list[str]:
        """Configuration errors. In PRODUCTION these stop the app from starting."""
        errs = []
        if not self.LLM_BASE_URL:
            errs.append("LLM_BASE_URL is empty")
        if not self.LLM_MODEL:
            errs.append("LLM_MODEL is empty")
        if not self.DB_TRUSTED_CONNECTION and not self.DB_USER:
            errs.append("DB_TRUSTED_CONNECTION=no but DB_USER is empty")
        if self.PRODUCTION:
            if not self.LLM_VERIFY_SSL:
                errs.append("LLM_VERIFY_SSL must be True when PRODUCTION=True")
            if not (self.TLS_CERT_FILE and self.TLS_KEY_FILE):
                errs.append("TLS_CERT_FILE and TLS_KEY_FILE are required when PRODUCTION=True")
            if "api.openai.com" in self.LLM_BASE_URL:
                errs.append("LLM_BASE_URL points at a public API; the server must use the internal gateway")
        return errs


def _coerce(name: str, typ, raw: str):
    if typ is bool or typ == "bool":
        return raw.strip().lower() in _TRUE
    if typ is int or typ == "int":
        return int(raw)
    if typ is float or typ == "float":
        return float(raw)
    return raw


def load_settings(env_file: Path | None = None) -> Settings:
    s = Settings()
    file_vals = _parse_env_file(env_file or ENV_FILE)
    for f in fields(Settings):
        if f.name == "sources":
            continue
        src, raw = "default", None
        if f.name in file_vals:
            src, raw = ".env", file_vals[f.name]
        elif f.name in os.environ:
            src, raw = "env", os.environ[f.name]
        if f"RA_{f.name}" in os.environ:
            src, raw = f"RA_{f.name}", os.environ[f"RA_{f.name}"]
        if raw is not None and (raw != "" or f.type in (str, "str")):
            try:
                setattr(s, f.name, _coerce(f.name, f.type, raw))
            except ValueError:
                raise ValueError(f"Invalid value for {f.name}: {raw!r}") from None
        s.sources[f.name] = src

    # Dev convenience: fall back to the machine's OPENAI_API_KEY for the local OpenAI stand-in.
    if not s.PRODUCTION and not s.LLM_API_KEY and os.environ.get("OPENAI_API_KEY"):
        s.LLM_API_KEY = os.environ["OPENAI_API_KEY"]
        s.sources["LLM_API_KEY"] = "env OPENAI_API_KEY"
    return s


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(s: Settings) -> None:
    """For tests."""
    global _settings
    _settings = s
