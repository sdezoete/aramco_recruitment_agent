"""Repository against the local dev DB (T_IIR_ARIF_* with fake seed data). Read-only except the memory table.
Skipped when the DB is not reachable or not seeded."""
import uuid

import pytest

from app.config import load_settings
from app.db.connection import connect
from app.db.repository import Repository, full_name, gpa_value, to_number
from app.services import statuses


@pytest.fixture(scope="module")
def repo():
    try:
        conn = connect(load_settings())
    except Exception as e:  # pragma: no cover
        pytest.skip(f"dev DB not reachable: {e}")
    r = Repository(conn)
    try:
        if not r.ping()["candidates"]:
            pytest.skip("dev DB not seeded (scripts/seed_dev_db.py)")
    except Exception as e:  # pragma: no cover
        pytest.skip(f"T_IIR_ARIF tables missing: {e}")
    yield r
    conn.close()


def test_helpers():
    assert to_number(" 7 ") == 7.0 and to_number("n/a") is None and to_number(None) is None
    assert full_name("محمد", None, "القحطاني") == "محمد القحطاني"
    assert full_name(None, " ", None) == "(no name)"
    assert gpa_value("3.45") == 3.45 and gpa_value("3.2/4") == 3.2 and gpa_value("4.5") is None
    assert gpa_value(None) is None


def test_profiles_shape_and_no_protected_fields(repo):
    ids = repo.all_candidate_ids(20)
    profs = repo.profiles(ids)
    assert len(profs) == len(ids)
    p = next(iter(profs.values()))
    for k in ("candidate_id", "ats_id", "full_name", "skills", "experience", "education", "assessments",
              "hire_type", "location", "total_experience"):
        assert k in p
    keys = {k.lower() for k in p}
    assert not keys & {"gender", "national_id", "country"}   # never selected (protected / PII)


def test_arabic_names_round_trip(repo):
    profs = repo.profiles(repo.all_candidate_ids(400))
    assert any(any("؀" <= ch <= "ۿ" for ch in p["full_name"]) for p in profs.values())


def test_skill_vocab_and_search_filters(repo):
    vocab = [s["skill_name"] for s in repo.skills()]
    assert "Python" in vocab
    total, ids = repo.search_candidate_ids(skills=["Python"], hire_type="Saudi", min_years=3, limit=50)
    assert total >= len(ids) > 0
    for p in repo.profiles(ids).values():
        assert "Python" in p["skills"] and p["hire_type"] == "Saudi" and p["total_experience"] >= 3
    _, ids = repo.search_candidate_ids(locations=["AOC"], exclude_statuses=["Hired"], limit=50)
    for p in repo.profiles(ids).values():
        assert p["location"] == "AOC" and p["application_status"] != "Hired"


def test_raw_skill_spellings_are_grouped(repo):
    names = [s["skill_name"] for s in repo.skills()]
    assert sum(1 for n in names if n.strip().lower() in ("excel", "ms excel", "microsoft excel", "advanced excel")) == 1
    variants = repo.skill_variants(["Excel"])[0]
    assert {"MS Excel", "Excel"} <= set(variants)
    for p in repo.profiles(repo.all_candidate_ids(400)).values():
        assert len(p["skills"]) == len({s.lower() for s in p["skills"]})


def test_ats_lookup_and_status_codes(repo):
    ids = repo.all_candidate_ids(5)
    profs = repo.profiles(ids)
    ats = [p["ats_id"] for p in profs.values()]
    assert set(repo.arif_ids_for_ats(ats).values()) == set(ids)
    excluded = statuses.excluded_codes()
    assert excluded
    pool = repo.all_candidate_ids(400, exclude_codes=excluded)
    for p in repo.profiles(pool).values():
        assert p["status_code"] not in excluded and p["status_included"]


def test_experience_sorted_current_first(repo):
    for p in repo.profiles(repo.all_candidate_ids(100)).values():
        cur = [e["current"] for e in p["experience"]]
        assert cur == sorted(cur, reverse=True)


def test_arabic_text_search(repo):
    total, _ = repo.search_candidate_ids(text="الشهري", limit=5)
    assert total >= 0  # parameter round-trips as nvarchar without errors


def test_pool_stats(repo):
    for m in Repository.METRICS:
        rows = repo.pool_stats(m)
        assert rows and all({"label", "value"} <= set(r) for r in rows)
    with pytest.raises(ValueError):
        repo.pool_stats("certification_mix")


def test_memory_round_trip(repo):
    chat = "pytest_" + uuid.uuid4().hex[:10]
    try:
        repo.memory_set(chat, "k", {"title": "اختبار", "n": 1})
        repo.memory_set(chat, "k", {"title": "اختبار", "n": 2})
        assert repo.memory_get(chat, "k") == {"title": "اختبار", "n": 2}
    finally:
        assert repo.memory_delete_chat(chat) == 1


def test_large_id_sets_use_temp_table_with_same_result(repo, monkeypatch):
    import app.db.repository as rmod
    ids = repo.all_candidate_ids(120)
    small = repo.profiles(ids)
    monkeypatch.setattr(rmod, "_CHUNK", 50)   # force the temp-table path
    assert repo.profiles(ids) == small
