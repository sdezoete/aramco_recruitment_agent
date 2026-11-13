"""Profile side panel endpoint (ADR-015): GET /api/candidates/{id}/profile?chat_id=...
Runs against the local dev DB without an LLM. Skipped when the DB is not reachable or not seeded."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import registry
from app.db.connection import connect
from app.db.repository import Repository
from app.tools.context import ToolContext

PROTECTED = {"national_id", "gender", "country", "nationality", "religion", "marital_status", "age", "birth_date"}


@pytest.fixture(scope="module")
def ids():
    try:
        conn = connect(main.state.settings)
    except Exception as e:  # pragma: no cover
        pytest.skip(f"dev DB not reachable: {e}")
    try:
        found = Repository(conn).all_candidate_ids(5)
    finally:
        conn.close()
    if not found:
        pytest.skip("dev DB not seeded (scripts/seed_dev_db.py)")
    return found


@pytest.fixture
def client(monkeypatch):
    audit = []
    monkeypatch.setattr(main, "_audit", audit.append)
    # no `with`: the lifespan (LLM probe) is not needed for this endpoint
    c = TestClient(main.app)
    c.audit = audit
    return c


@pytest.fixture
def chat_id():
    cid = "pytest_" + uuid.uuid4().hex[:12]
    yield cid
    main.state.chats.pop(cid, None)
    conn = connect(main.state.settings)
    try:
        Repository(conn).memory_delete_chat(cid)
    finally:
        conn.close()


def _url(cand, chat):
    return f"/api/candidates/{cand}/profile?chat_id={chat}"


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k).lower()
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_profile_block_without_job_spec(client, ids, chat_id):
    r = client.get(_url(ids[0], chat_id))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["template"] == "candidate_profile"
    d = b["data"]
    assert d["candidate_id"] == ids[0]
    assert d["full_name"]
    for k in ("skills", "experience", "education", "assessments", "criteria"):
        assert k in d
    # no active job: nothing to score against
    assert d["score"] is None and d["breakdown"] is None


def test_profile_never_contains_protected_fields(client, ids, chat_id):
    for cand in ids:
        b = client.get(_url(cand, chat_id)).json()
        assert not PROTECTED & set(_keys(b)), cand


def test_profile_scored_against_active_job_matches_shortlist(client, chat_id):
    """With an active job the panel shows the same deterministic score as the ranking."""
    st = main.state.chat(chat_id)
    conn = connect(main.state.settings)
    try:
        ctx = ToolContext(repo=Repository(conn), settings=main.state.settings, chat=st)
        for name, args in (("set_job_spec", {"doc_id": "jd_business_analyst"}), ("match_candidates", {"limit": 5})):
            ok, res = registry.execute(ctx, name, args)
            assert ok, res
    finally:
        conn.close()
    assert st.shortlist, "business analyst JD should produce a shortlist on the seeded dev DB"
    history_before, seq_before = list(st.history), st.block_seq
    for row in st.shortlist[:3]:
        d = client.get(_url(row["candidate_id"], chat_id)).json()["data"]
        assert d["score"] == row["score"]
        assert d["breakdown"] == row["breakdown"]
        assert d["matched_skills"] == row["matched_skills"]
    # read-only for the chat: no history, no block numbering, no LLM
    assert st.history == history_before and st.block_seq == seq_before


def test_profile_scored_after_server_restart(client, chat_id):
    """The active job is reloaded from agent memory when the chat is not in server memory."""
    st = main.state.chat(chat_id)
    conn = connect(main.state.settings)
    try:
        ctx = ToolContext(repo=Repository(conn), settings=main.state.settings, chat=st)
        ok, res = registry.execute(ctx, "set_job_spec", {"doc_id": "jd_business_analyst"})
        assert ok, res
        ok, res = registry.execute(ctx, "match_candidates", {"limit": 3})
        assert ok, res
        top = st.shortlist[0]
    finally:
        conn.close()
    main.state.chats.pop(chat_id)   # simulate a restart: only T_IIR_ARIF_AGENT_MEMORY remains
    d = client.get(_url(top["candidate_id"], chat_id)).json()["data"]
    assert d["score"] == top["score"]


def test_unknown_candidate_is_404(client, chat_id):
    r = client.get(_url(2_000_000_000, chat_id))
    assert r.status_code == 404
    assert client.audit[-1]["outcome"] == "not_found"


@pytest.mark.parametrize("cand,chat,status", [
    ("abc", "validchat123", 422),
    ("0", "validchat123", 422),
    ("-5", "validchat123", 422),
    ("99999999999", "validchat123", 422),
    ("1", "short", 422),
    ("1", "bad chat id!!", 400),
    ("1", "x" * 51, 422),
])
def test_bad_input_is_rejected(client, cand, chat, status):
    assert client.get(f"/api/candidates/{cand}/profile", params={"chat_id": chat}).status_code == status


def test_missing_chat_id_is_rejected(client):
    assert client.get("/api/candidates/1/profile").status_code == 422


def test_audit_holds_metadata_only(client, ids, chat_id):
    client.get(_url(ids[0], chat_id))
    rec = client.audit[-1]
    assert rec["action"] == "profile_view" and rec["outcome"] == "ok"
    assert set(rec) == {"ts", "action", "seconds", "outcome"}   # no candidate id, name or chat id


def test_security_headers_present(client, ids, chat_id):
    r = client.get(_url(ids[0], chat_id))
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
