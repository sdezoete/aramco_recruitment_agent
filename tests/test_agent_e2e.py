"""End-to-end agent turns: mock LLM (in-process, via ASGITransport) + the local SQL Server dev DB.
Skipped when the DB is not reachable."""
import asyncio
import uuid

import httpx
import pytest

from app.agent.loop import run_turn
from app.config import load_settings
from app.db.connection import connect
from app.db.repository import Repository
from app.llm.client import LLMClient
from app.tools.context import ChatState
from tests import mock_llm


def _settings():
    s = load_settings()
    s.LLM_BASE_URL = "http://mock/v1"
    s.LLM_MODEL = mock_llm.MODEL
    s.LLM_API_KEY = ""
    s.PRODUCTION = False
    return s


@pytest.fixture(scope="module")
def db_ok():
    s = _settings()
    try:
        conn = connect(s)
        conn.close()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"dev DB not reachable: {e}")
    return s


def run(s, text, chat):
    client = LLMClient(s, transport=httpx.ASGITransport(app=mock_llm.app))

    async def go():
        evs = []
        try:
            async for ev in run_turn(settings=s, client=client, repo_factory=lambda: Repository(connect(s)),
                                     chat=chat, user_text=text):
                evs.append(ev)
        finally:
            await client.aclose()
        return evs, client
    return asyncio.run(go())


@pytest.fixture
def chat(db_ok):
    st = ChatState("pytest_" + uuid.uuid4().hex[:12])
    yield st
    conn = connect(db_ok)
    try:
        Repository(conn).memory_delete_chat(st.chat_id)
    finally:
        conn.close()


def _check_best_candidate_flow(evs, templates):
    kinds = [e[0] for e in evs]
    assert "error" not in kinds, evs
    assert kinds[-1] == "done"
    blocks = [d for k, d in evs if k == "ui_block"]
    assert [b["template"] for b in blocks] == templates
    rows = blocks[0]["data"]["rows"]
    assert rows and rows[0]["score"] >= rows[-1]["score"]
    tools = [d["name"] for k, d in evs if k == "tool_start"]
    assert tools[:2] == ["set_job_spec", "match_candidates"]
    final = "".join(d["text"] for k, d in evs if k == "text_delta")
    assert rows[0]["full_name"] in final


@pytest.mark.parametrize("mode", ["native", "raw_harmony", "no_tools"])
def test_best_candidate_flow(db_ok, chat, mode, monkeypatch):
    monkeypatch.setattr(mock_llm, "RAW", mode == "raw_harmony")
    monkeypatch.setattr(mock_llm, "NO_TOOLS", mode == "no_tools")
    evs, client = run(db_ok, "Find the best candidates for the senior data scientist JD", chat)
    # prompted-JSON mode makes one tool call per reply, so the mock only gets to the ranked table
    _check_best_candidate_flow(evs, ["ranked_table"] if mode == "no_tools" else ["ranked_table", "score_radar"])
    if mode == "native":
        assert ("thinking", {"state": "start"}) in evs
        assert ("segment_end", {"kind": "preamble"}) in evs
    if mode == "no_tools":
        assert client.caps.native_tools is False
    # harmony history policy: no reasoning stored, final answer stored
    assert chat.history[-1]["role"] == "assistant"
    assert all("reasoning" not in str(m.keys()) for m in chat.history)


def test_shortlist_persisted_in_agent_memory(db_ok, chat):
    run(db_ok, "Find the best candidates for the business analyst JD", chat)
    conn = connect(db_ok)
    try:
        repo = Repository(conn)
        assert repo.memory_get(chat.chat_id, "active_job_spec")["title"] == "Business Analyst"
        assert len(repo.memory_get(chat.chat_id, "last_shortlist")) >= 1
    finally:
        conn.close()
