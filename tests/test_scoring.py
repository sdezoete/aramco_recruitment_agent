from app.services.normalize import degree_level, fuzzy_match
from app.services.scoring import JobSpec, normalize_weights, rank, score_candidate


def cand(cid, skills, years, degree="Bachelor", major="Computer Science", title="Data Scientist", certs=()):
    return {"candidate_id": cid, "full_name": f"C{cid}", "skills": list(skills), "total_experience": years,
            "highest_degree": degree, "primary_major": major, "last_job_title": title,
            "experience": [{"job_title": title, "years_experience": years}], "education": [],
            "certifications": list(certs)}


def test_degree_levels():
    assert degree_level("PhD") == 4
    assert degree_level("Master") == 3
    assert degree_level("MBA") == 3
    assert degree_level("M.Sc") == 3
    assert degree_level("Bachelor") == 2
    assert degree_level("Management") == 0      # must not match "ma"
    assert degree_level("Master's degree in Data Science") == 3


def test_fuzzy_match():
    vocab = ["Python", "SQL", "Machine Learning", "Excel"]
    assert fuzzy_match("python3", vocab) == "Python"
    assert fuzzy_match("ML", vocab) == "Machine Learning"
    assert fuzzy_match("MS Excel", vocab) == "Excel"
    assert fuzzy_match("Kubernetes", vocab) is None


def test_weights_normalize():
    w = normalize_weights({"skills": 2, "experience": 0})
    assert abs(sum(w.values()) - 1) < 1e-3
    assert w["experience"] == 0


def test_rank_orders_and_explains():
    spec = JobSpec(title="Data Scientist", required_skills=["Python", "SQL", "Machine Learning"],
                   preferred_skills=["Tableau"], min_years=4, degree_level=3, majors=["Data Science"],
                   title_keywords=["Data Scientist"])
    a = cand(1, ["Python", "SQL", "Machine Learning", "Tableau"], 5, "Master", "Data Science")
    b = cand(2, ["Python"], 2, "Bachelor", "Graphic Design", "Graphic Designer")
    res = rank(spec, [b, a], must_have=["SQL"])
    assert [r["candidate_id"] for r in res] == [1, 2]
    assert res[0]["score"] > 85
    assert res[1]["missing_skills"] == ["SQL", "Machine Learning"]
    assert "missing_must_have:SQL" in res[1]["flags"] and "below_min_years" in res[1]["flags"]
    assert set(res[0]["breakdown"]) == {"skills", "experience", "relevance", "education", "certifications"}


def test_deterministic():
    spec = JobSpec(required_skills=["Python"], min_years=3)
    c = cand(1, ["Python"], 3)
    assert score_candidate(spec, c) == score_candidate(spec, c)
