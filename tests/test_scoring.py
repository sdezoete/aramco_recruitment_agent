from app.services.normalize import canonical, degree_level, fuzzy_match, norm
from app.services.scoring import (JobSpec, normalize_hire_type, normalize_weights, passes_filters, rank,
                                  score_candidate)


def cand(cid, skills, years, degree="Bachelor", major="Computer Science", title="Data Scientist",
         assessments=None, hire_type="Saudi", location="KSA"):
    return {"candidate_id": cid, "full_name": f"C{cid}", "skills": list(skills), "total_experience": years,
            "highest_degree": degree, "primary_major": major, "last_job_title": title,
            "experience": [{"job_title": title, "years_experience": years}], "education": [],
            "assessments": assessments if assessments is not None else {"inductive": 80, "numerical": 70,
                                                                         "verbal": 90},
            "hire_type": hire_type, "location": location}


def test_degree_levels():
    assert degree_level("PhD") == 4
    assert degree_level("Ph.D.") == 4
    assert degree_level("Master") == 3
    assert degree_level("MBA") == 3
    assert degree_level("M.Sc") == 3
    assert degree_level("Bachelor") == 2
    assert degree_level("Management") == 0      # must not match "ma"
    assert degree_level("Master's degree in Data Science") == 3
    assert degree_level("بكالوريوس") == 2
    assert degree_level("ماجستير") == 3
    assert degree_level("دكتوراه") == 4


def test_arabic_survives_normalization():
    assert norm("تعلم الآلة") == "تعلم الآلة"
    assert canonical("  Python ") == "python"
    assert canonical("الإحصاء") == canonical("Statistics")      # Arabic spelling groups with English
    assert fuzzy_match("تعلم الآلة", ["Machine Learning", "Python"]) == "Machine Learning"


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
    assert "certifications" not in w and "assessments" in w


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
    assert set(res[0]["breakdown"]) == {"skills", "experience", "relevance", "education", "assessments"}


def test_assessments_mean_and_neutral_when_missing():
    spec = JobSpec(required_skills=["Python"])
    r = score_candidate(spec, cand(1, ["Python"], 3, assessments={"inductive": 60, "numerical": None, "verbal": 80}))
    assert r["breakdown"]["assessments"] == 0.7
    r = score_candidate(spec, cand(2, ["Python"], 3, assessments={}))
    assert r["breakdown"]["assessments"] == 0.5 and "no_assessment" in r["flags"]


def test_hire_type_is_a_filter_not_a_score():
    spec = JobSpec(required_skills=["Python"], hire_type="Saudi", locations=["AOC"])
    saudi = cand(1, ["Python"], 3, hire_type="Saudi", location="AOC")
    expat = cand(2, ["Python"], 3, hire_type="Expat", location="AOC")
    assert passes_filters(spec, saudi) and not passes_filters(spec, expat)
    assert not passes_filters(spec, cand(3, ["Python"], 3, location="ASC"))
    # same job-related profile -> same score, whatever the hire type
    assert score_candidate(spec, saudi)["score"] == score_candidate(spec, expat)["score"]
    assert "hire_type_mismatch" in score_candidate(spec, expat)["flags"]
    assert normalize_hire_type("expatriate") == "Expat" and normalize_hire_type("any") is None


def test_old_saved_spec_still_loads():
    spec = JobSpec.from_dict({"title": "X", "certifications": ["PMP"], "weights": {"certifications": 0.5}})
    assert spec.title == "X" and "certifications" not in spec.weights


def test_deterministic():
    spec = JobSpec(required_skills=["Python"], min_years=3)
    c = cand(1, ["Python"], 3)
    assert score_candidate(spec, c) == score_candidate(spec, c)


def test_free_text_dates():
    from app.services.normalize import is_present, parse_date
    assert parse_date("Mar 2019") == parse_date("2019-03") == parse_date("03/2019") == (2019, 3)
    assert parse_date("2015") == (2015, 1) and parse_date("Present") is None
    assert is_present("Present") and is_present("حتى الآن") and not is_present("2019")


def test_status_and_gpa_flags():
    spec = JobSpec(required_skills=["Python"], min_gpa=3.0)
    c = cand(1, ["Python"], 3)
    c.update(gpa=2.8, status_included=False)
    flags = score_candidate(spec, c)["flags"]
    assert "below_min_gpa" in flags and "status_not_open" in flags
