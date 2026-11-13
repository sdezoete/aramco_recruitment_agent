"""FastAPI app: static frontend + JSON/SSE API (docs/ARCHITECTURE.md, Endpoints)."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.agent.loop import run_turn
from app.config import ROOT, get_settings
from app.db.connection import connect
from app.db.repository import Repository
from app.services.scoring import CRITERIA
from app.llm.client import LLMClient
from app.tools import render
from app.tools.context import ChatState, ToolContext, ToolError

log = logging.getLogger("ra")
STATIC = ROOT / "static"
LOGS = ROOT / "logs"
_CHAT_ID = re.compile(r"^[A-Za-z0-9_\-]{8,50}$")
MAX_CHATS = 200


class AppState:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm: LLMClient | None = None
        self.chats: OrderedDict[str, ChatState] = OrderedDict()
        self.db_status: dict = {"reachable": None}

    def repo(self) -> Repository:
        return Repository(connect(self.settings))

    def chat(self, chat_id: str) -> ChatState:
        if chat_id in self.chats:
            self.chats.move_to_end(chat_id)
            return self.chats[chat_id]
        st = ChatState(chat_id)
        self.chats[chat_id] = st
        while len(self.chats) > MAX_CHATS:
            self.chats.popitem(last=False)
        return st


state = AppState()


def _audit(record: dict) -> None:
    """Metadata only: never message content or candidate data."""
    try:
        LOGS.mkdir(exist_ok=True)
        with open(LOGS / "audit.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


async def _check_db() -> dict:
    def ping():
        conn = connect(state.settings)
        try:
            return Repository(conn).ping()
        finally:
            conn.close()
    try:
        info = await asyncio.to_thread(ping)
        state.db_status = {"reachable": True, "database": info["db"], "candidates": info["candidates"],
                           "memory_table": bool(info["memory_table"])}
    except Exception as e:
        state.db_status = {"reachable": False, "detail": f"{type(e).__name__}: {str(e)[:200]}"}
    return state.db_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = state.settings
    problems = s.problems()
    log.info("Recruitment Agent %s | PRODUCTION=%s", __version__, s.PRODUCTION)
    if not s.PRODUCTION:
        log.warning("*** DEVELOPMENT MODE (PRODUCTION=False) ***")
    for p in problems:
        log.error("config: %s", p)
    if s.PRODUCTION and problems:
        raise SystemExit("Refusing to start in PRODUCTION with configuration problems (see above).")
    state.llm = LLMClient(s)
    db, caps = await asyncio.gather(_check_db(), state.llm.probe())
    log.info("DB %s/%s: %s", s.DB_SERVER, s.DB_NAME, "reachable" if db.get("reachable") else db.get("detail"))
    log.info("LLM %s at %s: %s", s.LLM_MODEL, s.LLM_BASE_URL, "reachable" if caps.reachable else caps.detail)
    yield
    await state.llm.aclose()


app = FastAPI(title="Recruitment Agent", version=__version__, lifespan=lifespan,
              docs_url=None if get_settings().PRODUCTION else "/api/docs", redoc_url=None, openapi_url=None
              if get_settings().PRODUCTION else "/api/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    if not request.url.path.startswith("/api/docs"):
        h["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                                        "script-src 'self'; connect-src 'self'; font-src 'self'; "
                                        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    h["X-Content-Type-Options"] = "nosniff"
    h["Referrer-Policy"] = "no-referrer"
    h["X-Frame-Options"] = "DENY"
    if state.settings.PRODUCTION:
        h["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    detail = "Internal error" if state.settings.PRODUCTION else f"{type(exc).__name__}: {exc}"
    return JSONResponse({"error": detail}, status_code=500)


# ------------------------------------------------------------------------------------------- pages
@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ------------------------------------------------------------------------------------------- api
@app.get("/api/meta")
async def meta():
    s = state.settings
    return {"version": __version__, "production": s.PRODUCTION, "llm_label": s.llm_label,
            "display_name": s.LLM_DISPLAY_NAME or "ARIF"}


@app.get("/api/health")
async def health():
    s = state.settings
    db = await _check_db()
    caps = state.llm.caps if state.llm else None
    if state.llm and (caps.reachable is not True or not caps.checked_at or time.time() - caps.checked_at > 60):
        caps = await state.llm.probe()
    return {"version": __version__, "production": s.PRODUCTION, "db": db,
            "llm": {"model": s.LLM_MODEL, "label": s.llm_label, **(caps.public() if caps else {})},
            "config_problems": s.problems()}


class ChatIn(BaseModel):
    chat_id: str = Field(min_length=8, max_length=50)
    message: str = Field(min_length=1, max_length=20000)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    if not _CHAT_ID.match(body.chat_id):
        raise HTTPException(400, "invalid chat_id")
    chat_state = state.chat(body.chat_id)

    async def stream():
        t0, tools, outcome = time.time(), [], "ok"
        try:
            async for event, data in run_turn(settings=state.settings, client=state.llm, repo_factory=state.repo,
                                              chat=chat_state, user_text=body.message.strip()):
                if event == "tool_start":
                    tools.append(data["name"])
                elif event == "error":
                    outcome = "error"
                yield _sse(event, data)
                if await request.is_disconnected():
                    outcome = "client_disconnected"
                    break
        except Exception as e:
            log.exception("chat turn failed")
            outcome = "error"
            yield _sse("error", {"message": "Internal error" if state.settings.PRODUCTION else str(e)})
        finally:
            _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": "chat_turn", "tools": tools,
                    "seconds": round(time.time() - t0, 2), "outcome": outcome})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/candidates/{candidate_id}/profile")
async def candidate_profile(candidate_id: int = PathParam(gt=0, le=2_147_483_647),
                            chat_id: str = Query(min_length=8, max_length=50)):
    """Profile panel (ADR-015): the candidate_profile block, hydrated and scored by the server against the
    chat's active job spec, without an LLM round trip. Read-only: no history, no memory writes."""
    if not _CHAT_ID.match(chat_id):
        raise HTTPException(400, "invalid chat_id")
    st = state.chat(chat_id)

    def build() -> dict:
        conn = connect(state.settings)
        try:
            repo = Repository(conn)
            st.load(repo)
            ctx = ToolContext(repo=repo, settings=state.settings, chat=st)
            return render.build(ctx, {"template": "candidate_profile", "title": "Profile",
                                      "candidate_ids": [candidate_id]})
        finally:
            conn.close()

    t0, outcome = time.time(), "ok"
    try:
        return await asyncio.to_thread(build)
    except ToolError:
        outcome = "not_found"
        raise HTTPException(404, "candidate not found") from None
    except Exception:
        outcome = "error"
        raise
    finally:   # metadata only: no candidate id or name
        _audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": "profile_view",
                "seconds": round(time.time() - t0, 2), "outcome": outcome})


@app.get("/dev/gallery", include_in_schema=False)
async def dev_gallery():
    """Dev only: every UI template rendered from real DB data (design + visual checks)."""
    if state.settings.PRODUCTION:
        raise HTTPException(404)
    return FileResponse(STATIC / "dev" / "gallery.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/dev/sample-blocks", include_in_schema=False)
async def dev_sample_blocks(doc_id: str = "jd_senior_data_scientist"):
    if state.settings.PRODUCTION:
        raise HTTPException(404)
    from app.agent import registry
    from app.tools.context import ToolContext

    def build():
        conn = connect(state.settings)
        try:
            repo = Repository(conn)
            chat_state = ChatState("dev_gallery")
            ctx = ToolContext(repo=repo, settings=state.settings, chat=chat_state)
            calls = [("set_job_spec", {"doc_id": doc_id}), ("match_candidates", {"limit": 10})]
            for name, args in calls:
                ok, res = registry.execute(ctx, name, args)
                if not ok:
                    raise HTTPException(500, res)
            top = [r["candidate_id"] for r in chat_state.shortlist[:3]]
            views = [
                {"template": "kpi_strip", "title": "At a glance"},
                {"template": "jd_card", "title": "Active job spec"},
                {"template": "ranked_table", "title": "Best matches"},
                {"template": "score_radar", "title": "Top 3 head to head", "candidate_ids": top},
                {"template": "comparison_matrix", "title": "Comparison", "candidate_ids": top},
                {"template": "candidate_cards", "title": "Top candidates", "candidate_ids": top},
                {"template": "candidate_profile", "title": "Profile", "candidate_ids": top[:1]},
                {"template": "chart", "title": "Skill supply (pool)", "metric": "skill_supply"},
                {"template": "chart", "title": "Shortlist scores", "metric": "shortlist_scores"},
                {"template": "chart", "title": "Degree mix", "metric": "degree_mix"},
                {"template": "chart", "title": "Application status (furthest reached)", "metric": "status_mix"},
                {"template": "document_hits", "title": "Documents"},
            ]
            for v in views:
                ok, res = registry.execute(ctx, "render_view", v)
                if not ok:
                    raise HTTPException(500, res)
            return ctx.blocks
        finally:
            conn.close()

    return await asyncio.to_thread(build)


class ResetIn(BaseModel):
    chat_id: str


@app.post("/api/chat/reset")
async def reset(body: ResetIn):
    state.chats.pop(body.chat_id, None)
    return {"ok": True}


@app.get("/api/export/shortlist.csv")
async def export_shortlist(chat_id: str):
    if not _CHAT_ID.match(chat_id):
        raise HTTPException(400, "invalid chat_id")
    st = state.chat(chat_id)
    if not st.shortlist:
        def load():
            conn = connect(state.settings)
            try:
                st.load(Repository(conn))
            finally:
                conn.close()
        await asyncio.to_thread(load)
    if not st.shortlist:
        raise HTTPException(404, "no shortlist for this chat yet")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "arif_id", "ats_candidate_id", "full_name", "location", "hire_type", "score",
                *CRITERIA, "matched_skills", "missing_skills", "flags"])
    for n, r in enumerate(st.shortlist, 1):
        b = r["breakdown"]
        w.writerow([n, r["candidate_id"], r.get("ats_id"), r["full_name"], r.get("location"), r.get("hire_type"),
                    r["score"], *(b.get(c) for c in CRITERIA), "; ".join(r["matched_skills"]),
                    "; ".join(r["missing_skills"]), "; ".join(r.get("flags", []))])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="shortlist.csv"'})
