"""DEV ONLY: fill the local T_IIR_ARIF_* tables with deterministic FAKE candidates.

Every person, id and score here is invented. Some names, institutions and skills are in Arabic, like on the
server. Run after sql/01_dev_server_tables.sql (which empties the tables):

    sqlcmd -S localhost -E -d recruitment -i sql\\01_dev_server_tables.sql
    sqlcmd -S localhost -E -d recruitment -i sql\\02_agent_memory.sql
    .venv\\Scripts\\python scripts\\seed_dev_db.py [--count 400]

Refuses to run when PRODUCTION=True.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_settings  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.services import statuses  # noqa: E402

# ---------------------------------------------------------------------------------------------- vocab
# family -> (titles, core skills, extra skills, majors, min degree)
FAMILIES = {
    "data": (["Data Scientist", "Senior Data Scientist", "Machine Learning Engineer", "Data Analyst"],
             ["Python", "SQL", "Machine Learning", "Statistics"],
             ["ETL", "Tableau", "Power BI", "Spark", "AWS", "Deep Learning", "NLP", "Azure"],
             ["Computer Science", "Data Science", "Statistics", "Mathematics"], "Bachelor"),
    "ba": (["Business Analyst", "Senior Business Analyst", "Process Analyst", "Business Systems Analyst"],
           ["Business Analysis", "Excel", "Requirements Gathering"],
           ["SQL", "Tableau", "Power BI", "Process Improvement", "Stakeholder Management", "SAP", "Agile"],
           ["Business Administration", "Management", "Information Systems", "Finance"], "Bachelor"),
    "structural": (["Structural Engineer", "Senior Structural Engineer", "Civil Engineer", "Design Engineer"],
                   ["AutoCAD", "Structural Analysis", "Excel"],
                   ["STAAD.Pro", "ETABS", "Revit", "Concrete Design", "Steel Design", "Primavera P6"],
                   ["Civil Engineering", "Structural Engineering"], "Bachelor"),
    "reservoir": (["Reservoir Engineer", "Senior Reservoir Engineer", "Petroleum Engineer", "Production Engineer"],
                  ["Reservoir Simulation", "Petrel", "Well Testing"],
                  ["Eclipse", "PVT Analysis", "Production Optimization", "Python", "Decline Curve Analysis",
                   "Nodal Analysis"],
                  ["Petroleum Engineering", "Chemical Engineering", "Geoscience"], "Bachelor"),
    "process": (["Process Engineer", "Senior Process Engineer", "Process Safety Engineer"],
                ["Aspen HYSYS", "Process Simulation", "HAZOP"],
                ["P&ID", "Process Safety", "Excel", "Heat Exchanger Design", "Python"],
                ["Chemical Engineering", "Process Engineering"], "Bachelor"),
    "design": (["Graphic Designer", "UX Designer", "Visual Designer"],
               ["Photoshop", "Illustrator", "Figma"],
               ["InDesign", "Excel", "UX Research"],
               ["Graphic Design", "Fine Arts"], "Diploma"),
}
FAMILY_WEIGHTS = {"data": 22, "ba": 20, "structural": 16, "reservoir": 18, "process": 14, "design": 10}

# How a skill may be written in a resume (ORG_SKILL). The app uses ORG_SKILL only; NORM_* columns stay NULL
# in dev data to prove nothing depends on them (user decision 2026-11-11).
ORG_VARIANTS = {
    "Python": ["Python", "Python 3", "python", "Python programming"],
    "SQL": ["SQL", "T-SQL", "MS SQL Server", "SQL queries"],
    "Machine Learning": ["Machine Learning", "ML", "machine-learning", "تعلم الآلة"],
    "Excel": ["Excel", "MS Excel", "Microsoft Excel", "Advanced Excel"],
    "Statistics": ["Statistics", "Statistical analysis", "الإحصاء"],
    "Business Analysis": ["Business Analysis", "BA", "تحليل الأعمال"],
    "AutoCAD": ["AutoCAD", "Auto CAD", "AutoCAD 2D/3D"],
    "Project Management": ["Project Management", "إدارة المشاريع", "project management"],
}

SAUDI_GIVEN_M = [("محمد", "Mohammed"), ("أحمد", "Ahmed"), ("عبدالله", "Abdullah"), ("فهد", "Fahad"),
                 ("خالد", "Khalid"), ("سلطان", "Sultan"), ("عمر", "Omar"), ("فيصل", "Faisal"),
                 ("ناصر", "Nasser"), ("تركي", "Turki")]
SAUDI_GIVEN_F = [("سارة", "Sarah"), ("نورة", "Noura"), ("ريم", "Reem"), ("فاطمة", "Fatimah"),
                 ("هيا", "Haya"), ("لمى", "Lama"), ("دانة", "Dana"), ("منيرة", "Munirah")]
SAUDI_FAMILY = [("القحطاني", "Al-Qahtani"), ("الشهري", "Al-Shehri"), ("العتيبي", "Al-Otaibi"),
                ("الدوسري", "Al-Dossary"), ("الغامدي", "Al-Ghamdi"), ("الزهراني", "Al-Zahrani"),
                ("الحربي", "Al-Harbi"), ("المطيري", "Al-Mutairi"), ("السبيعي", "Al-Subaie"),
                ("العنزي", "Al-Anazi")]
EXPATS = [  # (given_m, given_f, family, country)
    (["Pieter", "Daan", "Jeroen"], ["Sanne", "Lotte", "Femke"], ["de Vries", "Jansen", "Bakker", "Visser"],
     "Netherlands"),
    (["James", "Michael", "Robert"], ["Emily", "Jessica", "Laura"], ["Smith", "Johnson", "Miller", "Davis"],
     "United States"),
    (["Oliver", "Harry"], ["Charlotte", "Amelia"], ["Taylor", "Brown", "Wilson"], "United Kingdom"),
    (["Rahul", "Arjun", "Vikram"], ["Priya", "Ananya", "Divya"], ["Sharma", "Patel", "Iyer", "Nair"], "India"),
    (["Ahmed", "Mostafa", "Karim"], ["Mona", "Yasmin"], ["Hassan", "Ibrahim", "Mahmoud"], "Egypt"),
    (["Omar", "Zaid"], ["Lina", "Rania"], ["Haddad", "Khoury", "Nasser"], "Jordan"),
    (["Jose", "Mark"], ["Maria", "Angela"], ["Santos", "Reyes", "Cruz"], "Philippines"),
]
SAUDI_EMPLOYERS = [("شركة الخليج للهندسة", "Gulf Engineering Co"), ("Desert Analytics", "Desert Analytics"),
                   ("Red Sea Petroleum Services", "Red Sea Petroleum Services"),
                   ("مجموعة النخبة للاستشارات", "Elite Consulting Group"), ("Najd Data Solutions", "Najd Data Solutions"),
                   ("Eastern Province Utilities", "Eastern Province Utilities")]
INTL_EMPLOYERS = ["Nordic Data Labs", "Atlas Consulting", "Northsea Energy", "Meridian Structures",
                  "Bluewater Process Engineering", "Harbor Analytics", "Summit Design Studio", "Delta Reservoir Partners"]
SAUDI_INSTITUTIONS = [("جامعة الملك سعود", "King Saud University"),
                      ("King Fahd University of Petroleum and Minerals", "King Fahd University of Petroleum and Minerals"),
                      ("جامعة الملك عبدالعزيز", "King Abdulaziz University"),
                      ("Imam Abdulrahman Bin Faisal University", "Imam Abdulrahman Bin Faisal University")]
INTL_INSTITUTIONS = ["Delft University of Technology", "University of Texas at Austin", "Imperial College London",
                     "Indian Institute of Technology Bombay", "Cairo University", "University of Jordan",
                     "University of the Philippines", "Heriot-Watt University", "Texas A&M University"]
DEGREE_TEXT = {"Diploma": ["Diploma", "دبلوم"], "Bachelor": ["B.Sc.", "Bachelor of Science", "BEng", "بكالوريوس"],
               "Master": ["M.Sc.", "Master of Science", "MBA", "ماجستير"], "PhD": ["PhD", "Ph.D.", "دكتوراه"]}
DEG_ORDER = ["Diploma", "Bachelor", "Master", "PhD"]
SOURCES = ["Career Site", "Referral", "Job Fair", "LinkedIn", "University Recruitment", "Agency"]
_STATUS_LIST = sorted(statuses.load().values(), key=lambda s: s.code)   # data/reference/application_statuses.csv
STATUSES = [(s.status, s.code) for s in _STATUS_LIST]
_STAGE_W = {"Applied": 6, "Screening": 5, "Assessment": 3, "Interview": 2, "Offer": 1, "Hiring": 0.5, "Hired": 1,
            "Closed": 3}
STATUS_W = [_STAGE_W.get(s.stage, 1) for s in _STATUS_LIST]
FLAGS = ["KSA", "AOC", "ASC"]          # location flag (dev sample values; server uses AOC, ASC, ...)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TODAY = date(2026, 11, 1)


def fmt_date(r: random.Random, d: date) -> str:
    return r.choice([f"{MONTHS[d.month - 1]} {d.year}", f"{d.year}-{d.month:02d}", f"{d.month:02d}/{d.year}"])


def add_years(d: date, years: int, months: int = 0) -> date:
    m = d.month - 1 + months
    return date(d.year + years + m // 12, m % 12 + 1, 1)


def tokens(*parts: str) -> str:
    words: list[str] = []
    for p in parts:
        for w in re.findall(r"[\w+#&.]+", (p or "").lower()):
            if len(w) > 1 and w not in words:
                words.append(w)
    return " ".join(words)


def make_candidate(r: random.Random, n: int) -> dict:
    fam_key = r.choices(list(FAMILY_WEIGHTS), weights=list(FAMILY_WEIGHTS.values()))[0]
    titles, core, extra, majors, min_deg = FAMILIES[fam_key]
    saudi = r.random() < 0.6
    female = r.random() < 0.35
    arabic_script = saudi and r.random() < 0.5
    if saudi:
        g = r.choice(SAUDI_GIVEN_F if female else SAUDI_GIVEN_M)
        m = r.choice(SAUDI_GIVEN_M)
        f = r.choice(SAUDI_FAMILY)
        idx = 0 if arabic_script else 1
        given, middle, surname = g[idx], m[idx], f[idx]
        country = "Saudi Arabia" if r.random() < 0.9 else r.choice(["United States", "United Kingdom"])
        flag = "KSA" if country == "Saudi Arabia" else r.choice(["AOC", "ASC"])
    else:
        gm, gf, fams, country = r.choice(EXPATS)
        given, middle, surname = r.choice(gf if female else gm), None, r.choice(fams)
        flag = {"Netherlands": "AOC", "United Kingdom": "AOC", "United States": "ASC"}.get(
            country, r.choice(FLAGS))

    seniority = r.random()
    total_years = int(round(seniority * 18)) + r.choice([0, 1])
    junior_titles = [t for t in titles if not t.startswith("Senior")]
    title = titles[1] if total_years >= 8 and r.random() < 0.6 else r.choice(
        titles if total_years >= 6 else junior_titles)
    skills = list(core) if r.random() < 0.55 else r.sample(core, k=max(1, len(core) - 1))
    skills += r.sample(extra, k=r.randint(1, min(5, len(extra))))
    if r.random() < 0.25:
        skills.append("Project Management")
    if r.random() < 0.15:  # cross-family noise
        other = FAMILIES[r.choice([k for k in FAMILIES if k != fam_key])]
        skills.append(r.choice(other[1]))
    skills = list(dict.fromkeys(skills))

    # education: 1-2 degrees, highest last
    top = r.choices(DEG_ORDER, weights=[1, 6, 3, 1] if min_deg == "Bachelor" else [5, 4, 1, 0])[0]
    top = max(top, min_deg, key=DEG_ORDER.index) if r.random() < 0.9 else top
    degs = [d for d in DEG_ORDER[1:DEG_ORDER.index(top) + 1]] if top != "Diploma" else ["Diploma"]
    degs = degs[-2:]
    major = r.choice(majors)
    end_year = TODAY.year - total_years - r.randint(0, 1)
    edu = []
    for i, d in enumerate(reversed(degs)):
        dur = {"Diploma": 2, "Bachelor": 4, "Master": 2, "PhD": 4}[d]
        end = date(end_year, r.choice([5, 6, 7]), 1)
        start = date(end.year - dur, 9, 1)
        end_year = start.year
        if saudi and r.random() < 0.7:
            inst, norm_inst = r.choice(SAUDI_INSTITUTIONS)
        else:
            inst = norm_inst = r.choice(INTL_INSTITUTIONS)
        ongoing = i == 0 and d in ("Master", "PhD") and r.random() < 0.08
        edu.append({"DEGREE": r.choice(DEGREE_TEXT[d]), "MAJOR": major if i == 0 or r.random() < 0.6 else r.choice(majors),
                    "INSTITUTION": inst, "STARTDATE": str(start.year), "ENDDATE": "Present" if ongoing else str(end.year),
                    "NORM_DEGREE": None, "NORM_INSTITUTION": None, "NORM_STARTDATE": None,
                    "NORM_ENDDATE": None})

    # experience: walk back from today
    exp, cursor, left = [], TODAY, total_years
    employers = SAUDI_EMPLOYERS if country == "Saudi Arabia" else [(e, e) for e in INTL_EMPLOYERS]
    while left > 0 and len(exp) < 4:
        yrs = left if len(exp) == 3 else min(left, r.randint(1, 6))
        start = add_years(cursor, -yrs, -r.randint(0, 5))
        emp, norm_emp = r.choice(employers)
        t = title if not exp else r.choice(titles)
        current = not exp
        exp.append({"TITLE": t, "EMPLOYER": emp, "STARTDATE": fmt_date(r, start),
                    "ENDDATE": "Present" if current else fmt_date(r, cursor),
                    "COUNTRY": country if r.random() < 0.85 else r.choice(["Saudi Arabia", "United Arab Emirates", "Qatar"]),
                    "YEARS_OF_EXPERIENCE": yrs, "NORM_TITLE": None,
                    "NORM_EMPLOYER": None, "NORM_STARTDATE": None, "NORM_ENDDATE": None})
        cursor, left = start, left - yrs

    status, code = r.choices(STATUSES, weights=STATUS_W)[0]
    processed = r.random() > 0.05
    has_assess = r.random() < 0.7
    score = lambda: str(max(20, min(99, int(r.gauss(68, 14)))))  # noqa: E731
    emp_name = exp[0]["EMPLOYER"] if exp else None
    if r.random() < 0.08 and arabic_script:
        summary = f"{title} بخبرة {total_years} سنوات. مهارات: {', '.join(skills[:4])}."
    else:
        summary = (f"{title} with {total_years} years of experience"
                   + (f" at {emp_name}" if emp_name else "") + f". {top} in {major}. "
                   + f"Strong in {', '.join(skills[:3])}" + (f"; also {', '.join(skills[3:6])}." if len(skills) > 3 else "."))
    created = add_years(TODAY, -r.randint(0, 3), -r.randint(0, 11))
    return {
        "cand": {
            "CANDIDATE_ID": 3000000 + n * 7 + r.randint(0, 6),
            "GIVENNAME": given, "MIDDLENAME": middle, "SURNAME": surname, "CREATED_ON": created,
            "CURRENT_EMPLOYER": emp_name, "CURRENT_JOB_TITLE": title,
            "YEARS_OF_EXPERIENCE": str(total_years), "COUNTRY": country,
            "NATIONAL_ID": None,  # never stored in dev data; the app never reads this column
            "SAUDI_EXPAT": "Saudi" if saudi else "Expat",
            "GPA": (f"{r.uniform(2.3, 4.0):.2f}" if r.random() < 0.9 else f"{r.uniform(2.3, 4.0):.1f}/4")
            if r.random() < 0.8 else None,
            "LAST_MODIFIED": add_years(created, 0, r.randint(0, 10)) if created < TODAY else created,
            "SOURCE_OF_APPLICATION": r.choice(SOURCES), "GENDER": "F" if female else "M",
            "HIGHEST_JOB_REQ_ID": f"REQ-{r.randint(10000, 10999)}",
            "HIGHEST_APPLICATION_ID": f"APP-{r.randint(500000, 599999)}",
            "HIGHEST_APPLICATION_STATUS": status, "APPLICATION_STATUS_CODE": code,
            "RESUME_UPLOADED": 1, "RESUME_DATE": created, "RESUME_FILE_TYPE": r.choice(["pdf", "pdf", "docx"]),
            "RESUME_PROCESSED": 1 if processed else 0,
            "EDUCATION_EXTRACTED": 1 if processed else 0, "EXPERIENCE_EXTRACTED": 1 if processed else 0,
            "SKILLS_EXTRACTED": 1 if processed else 0, "SUMMARY_EXTRACTED": 1 if processed else 0,
            "WILD_SEARCH_EXTRACTED": 1 if processed else 0,
            "CANDIDATE_FLAG": flag,
            "INDREASON": score() if has_assess else None, "NUMREASON": score() if has_assess else None,
            "VERBREASON": score() if has_assess else None,
            "SUMMARY": summary if processed else None,
            "TEXT_TOKENS": tokens(title, summary, " ".join(skills), major) if processed else None,
        },
        "skills": [{"ORG_SKILL": (lambda v: f" {v} " if r.random() < 0.05 else v)(r.choice(ORG_VARIANTS.get(s, [s]))),
                    "NORM_SKILL": None} for s in skills] if processed else [],
        "education": edu if processed else [],
        "experience": exp if processed else [],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=400)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    s = load_settings()
    if s.PRODUCTION:
        print("Refusing to seed: PRODUCTION=True")
        return 2
    r = random.Random(args.seed)
    conn = connect(s)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dbo.T_IIR_ARIF_CANDIDATE")
    if cur.fetchone()[0]:
        print("T_IIR_ARIF_CANDIDATE is not empty. Run sql\\01_dev_server_tables.sql first.")
        return 1
    cols = None
    counts = {"skills": 0, "education": 0, "experience": 0}
    for n in range(args.count):
        c = make_candidate(r, n)
        cols = list(c["cand"])
        cur.execute(f"INSERT INTO dbo.T_IIR_ARIF_CANDIDATE ({', '.join(cols)}) OUTPUT INSERTED.ARIF_ID "
                    f"VALUES ({', '.join('?' * len(cols))})", [c["cand"][k] for k in cols])
        arif_id = cur.fetchone()[0]
        cid = c["cand"]["CANDIDATE_ID"]
        for table, key in (("T_IIR_ARIF_SKILLS", "skills"), ("T_IIR_ARIF_EDUCATION", "education"),
                           ("T_IIR_ARIF_EXPERIENCE", "experience")):
            rows = c[key]
            if not rows:
                continue
            rc = list(rows[0])
            cur.executemany(f"INSERT INTO dbo.{table} (ARIF_ID, CANDIDATE_ID, {', '.join(rc)}) "
                            f"VALUES (?, ?, {', '.join('?' * len(rc))})",
                            [[arif_id, cid] + [row[k] for k in rc] for row in rows])
            counts[key] += len(rows)
    conn.commit()
    conn.close()
    print(f"Seeded {args.count} fake candidates, {counts['skills']} skills, {counts['education']} education, "
          f"{counts['experience']} experience rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
