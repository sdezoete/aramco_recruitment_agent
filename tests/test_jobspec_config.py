from pathlib import Path

from app.config import ROOT, load_settings
from app.services import jobspec

VOCAB = ["AutoCAD", "Business Analysis", "ETL", "Excel", "Machine Learning", "Photoshop", "Python", "SQL",
         "Statistics", "Tableau"]


def test_extract_sample_jd():
    text = (ROOT / "data" / "docs" / "jd_senior_data_scientist.md").read_text(encoding="utf-8")
    spec = jobspec.extract(text, VOCAB)
    assert spec.title == "Senior Data Scientist"
    assert set(spec.required_skills) == {"Python", "SQL", "Machine Learning", "Statistics"}
    assert set(spec.preferred_skills) == {"ETL", "Tableau"}   # 'data pipelines' in Responsibilities ignored
    assert spec.min_years == 4
    assert spec.degree_level == 3
    assert "Data Science" in spec.majors


def test_map_skills_reports_unmapped():
    mapped, unmapped = jobspec.map_skills(["python3", "Kubernetes", "ml"], VOCAB)
    assert mapped == ["Python", "Machine Learning"]
    assert unmapped == ["Kubernetes"]


def test_env_file_and_production_rules(tmp_path: Path, monkeypatch):
    for k in ("PRODUCTION", "LLM_BASE_URL", "LLM_MODEL", "RA_PRODUCTION", "RA_LLM_BASE_URL", "RA_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    env = tmp_path / ".env"
    env.write_text("PRODUCTION=True\nLLM_BASE_URL=https://api.openai.com/v1\nLLM_MODEL=x\nPORT=9000\n"
                   "LLM_VERIFY_SSL=False\n", encoding="utf-8")
    s = load_settings(env)
    assert s.PRODUCTION is True and s.PORT == 9000
    probs = " ".join(s.problems())
    assert "LLM_VERIFY_SSL" in probs and "TLS_CERT_FILE" in probs and "public API" in probs


def test_ra_override_wins(tmp_path: Path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("PRODUCTION=False\nLLM_MODEL=from-env-file\n", encoding="utf-8")
    monkeypatch.setenv("RA_LLM_MODEL", "from-ra")
    assert load_settings(env).LLM_MODEL == "from-ra"
