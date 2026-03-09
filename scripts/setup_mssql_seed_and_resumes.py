from __future__ import annotations

import random
import os
from datetime import date, timedelta
from pathlib import Path

import pyodbc
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parents[1]
RESUME_DIR = BASE_DIR / "candidate_pdf_files"
DB_NAME = "arif_recruitment"
SERVER_CANDIDATES = [r"localhost\\SQLEXPRESS", r".\\SQLEXPRESS", "localhost", "."]
DRIVER_CANDIDATES = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]


FIRST_NAMES = [
    "Sarah",
    "Faisal",
    "Lina",
    "Yousef",
    "Maha",
    "Omar",
    "Huda",
    "Abdullah",
    "Reem",
    "Khalid",
    "Noor",
    "Hassan",
    "Dana",
    "Nasser",
    "Rania",
    "Saif",
    "Mariam",
    "Tariq",
    "Nour",
    "Ibrahim",
]

LAST_NAMES = [
    "Alharbi",
    "Alotaibi",
    "Alqahtani",
    "Alyami",
    "Alshammari",
    "Almutairi",
    "Alghamdi",
    "Alzahrani",
    "Alsubaie",
    "Almalki",
]

DATA_SCIENCE_TITLES = [
    "Data Scientist",
    "Senior Data Scientist",
    "Machine Learning Engineer",
    "ML Engineer",
    "Data Analyst",
    "Senior Data Analyst",
    "AI Engineer",
    "Applied Scientist",
]

EMPLOYERS = [
    "Saudi Data Labs",
    "PetroInsight Analytics",
    "DesertAI Solutions",
    "Riyadh Digital Systems",
    "Gulf Predictive Tech",
    "Aramco Digital Ventures",
    "Energy Intelligence Hub",
]

SKILL_POOLS = [
    ["python", "sql", "pandas", "machine learning", "data visualization"],
    ["python", "pytorch", "deep learning", "nlp", "mlops"],
    ["sql", "power bi", "tableau", "statistics", "excel"],
    ["python", "xgboost", "feature engineering", "model deployment", "docker"],
    ["python", "tensorflow", "computer vision", "mlflow", "kubernetes"],
]

DEGREES = ["Bachelor", "Master", "PhD"]
MAJORS = [
    "Computer Science",
    "Data Science",
    "Statistics",
    "Applied Mathematics",
    "Software Engineering",
    "Electrical Engineering",
]
INSTITUTIONS = [
    "King Fahd University of Petroleum and Minerals",
    "King Saud University",
    "Imam Abdulrahman bin Faisal University",
    "KAUST",
    "Prince Sultan University",
]


def _pick_driver() -> str:
    installed = set(pyodbc.drivers())
    for candidate in DRIVER_CANDIDATES:
        if candidate in installed:
            return candidate
    raise RuntimeError(f"No suitable SQL Server ODBC driver found. Installed: {sorted(installed)}")


def _connect(server: str, database: str, driver: str) -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True)


def _find_working_server(driver: str) -> str:
    server_override = os.getenv("SQL_SERVER")
    if server_override:
        with _connect(server=server_override, database="master", driver=driver) as conn:
            cur = conn.cursor()
            cur.execute("SELECT @@VERSION")
            _ = cur.fetchone()
            return server_override

    for server in SERVER_CANDIDATES:
        try:
            with _connect(server=server, database="master", driver=driver) as conn:
                cur = conn.cursor()
                cur.execute("SELECT @@VERSION")
                _ = cur.fetchone()
                return server
        except Exception:
            continue
    raise RuntimeError("Could not connect to SQL Server using known server candidates.")


def create_database(server: str, driver: str) -> None:
    with _connect(server=server, database="master", driver=driver) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            IF DB_ID('{DB_NAME}') IS NULL
                CREATE DATABASE [{DB_NAME}];
            """
        )


def create_tables(server: str, driver: str) -> None:
    with _connect(server=server, database=DB_NAME, driver=driver) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            IF OBJECT_ID('dbo.T_IIR_ARIF_CANDIDATE', 'U') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_CANDIDATE;
            IF OBJECT_ID('dbo.T_IIR_ARIF_EDUCATION', 'U') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_EDUCATION;
            IF OBJECT_ID('dbo.T_IIR_ARIF_EXPERIENCE', 'U') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_EXPERIENCE;
            IF OBJECT_ID('dbo.T_IIR_ARIF_SKILLS', 'U') IS NOT NULL DROP TABLE dbo.T_IIR_ARIF_SKILLS;
            """
        )

        cur.execute(
            """
            CREATE TABLE dbo.T_IIR_ARIF_CANDIDATE (
                ARIF_ID INT IDENTITY(10000000,1) NOT NULL PRIMARY KEY,
                CANDIDATE_ID INT NOT NULL,
                GIVENNAME NVARCHAR(300) NULL,
                MIDDLENAME NVARCHAR(300) NULL,
                SURNAME NVARCHAR(300) NULL,
                CREATED_ON DATE NULL,
                CURRENT_EMPLOYER NVARCHAR(300) NULL,
                CURRENT_JOB_TITLE NVARCHAR(300) NULL,
                YEARS_OF_EXPERIENCE NVARCHAR(300) NULL,
                COUNTRY NVARCHAR(300) NULL,
                NATIONAL_ID NVARCHAR(300) NULL,
                SAUDI_EXPAT NVARCHAR(300) NULL,
                GPA NVARCHAR(300) NULL,
                LAST_MODIFIED DATE NULL,
                SOURCE_OF_APPLICATION NVARCHAR(300) NULL,
                GENDER NVARCHAR(30) NULL,
                HIGHEST_JOB_REQ_ID NVARCHAR(255) NULL,
                HIGHEST_APPLICATION_ID NVARCHAR(255) NULL,
                HIGHEST_APPLICATION_STATUS NVARCHAR(255) NULL,
                APPLICATION_STATUS_CODE INT NULL,
                RESUME_UPLOADED INT NULL,
                RESUME_DATE DATE NULL,
                RESUME_FILE_TYPE NVARCHAR(30) NULL,
                RESUME_PROCESSED INT NULL,
                EDUCATION_EXTRACTED INT NULL,
                EXPERIENCE_EXTRACTED INT NULL,
                SKILLS_EXTRACTED INT NULL,
                SUMMARY_EXTRACTED INT NULL,
                WILD_SEARCH_EXTRACTED INT NULL,
                CANDIDATE_FLAG NVARCHAR(255) NULL,
                INDREASON NVARCHAR(30) NULL,
                NUMREASON NVARCHAR(30) NULL,
                VERBREASON NVARCHAR(30) NULL,
                SUMMARY NVARCHAR(MAX) NULL,
                TEXT_TOKENS NVARCHAR(MAX) NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE dbo.T_IIR_ARIF_EDUCATION (
                SCHOOL_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ARIF_ID INT NOT NULL,
                CANDIDATE_ID INT NOT NULL,
                DEGREE NVARCHAR(300) NULL,
                MAJOR NVARCHAR(300) NULL,
                INSTITUTION NVARCHAR(300) NULL,
                STARTDATE NVARCHAR(300) NULL,
                ENDDATE NVARCHAR(300) NULL,
                NORM_DEGREE NVARCHAR(300) NULL,
                NORM_INSTITUTION NVARCHAR(300) NULL,
                NORM_STARTDATE DATE NULL,
                NORM_ENDDATE DATE NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE dbo.T_IIR_ARIF_EXPERIENCE (
                JOB_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ARIF_ID INT NOT NULL,
                CANDIDATE_ID INT NOT NULL,
                TITLE NVARCHAR(300) NULL,
                EMPLOYER NVARCHAR(300) NULL,
                STARTDATE NVARCHAR(300) NULL,
                ENDDATE NVARCHAR(300) NULL,
                COUNTRY NVARCHAR(300) NULL,
                YEARS_OF_EXPERIENCE INT NULL,
                NORM_TITLE NVARCHAR(300) NULL,
                NORM_EMPLOYER NVARCHAR(300) NULL,
                NORM_STARTDATE DATE NULL,
                NORM_ENDDATE DATE NULL
            );
            """
        )

        cur.execute(
            """
            CREATE TABLE dbo.T_IIR_ARIF_SKILLS (
                SKILL_ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                ARIF_ID INT NOT NULL,
                CANDIDATE_ID INT NOT NULL,
                ORG_SKILL NVARCHAR(300) NULL,
                NORM_SKILL NVARCHAR(300) NULL
            );
            """
        )

        cur.execute("CREATE INDEX IX_CAND_ARIF ON dbo.T_IIR_ARIF_CANDIDATE (ARIF_ID);")
        cur.execute("CREATE INDEX IX_CAND_CANDIDATE_ID ON dbo.T_IIR_ARIF_CANDIDATE (CANDIDATE_ID);")
        cur.execute("CREATE INDEX IX_EDU_ARIF ON dbo.T_IIR_ARIF_EDUCATION (ARIF_ID);")
        cur.execute("CREATE INDEX IX_EXP_ARIF ON dbo.T_IIR_ARIF_EXPERIENCE (ARIF_ID);")
        cur.execute("CREATE INDEX IX_SKILL_ARIF ON dbo.T_IIR_ARIF_SKILLS (ARIF_ID);")


def _random_gender() -> str:
    return random.choice(["Male", "Female", "No Selection"])


def _build_summary(full_name: str, title: str, years: int, top_skills: list[str], degree: str, major: str) -> str:
    return (
        f"{full_name} is a data science applicant targeting {title} roles with {years}+ years of analytics and machine learning experience. "
        f"Holds a {degree} in {major}. Core strengths include {', '.join(top_skills[:4])}. "
        "Demonstrated ability to build predictive models, communicate findings, and deploy solutions in business environments."
    )


def seed_data(server: str, driver: str, candidate_count: int = 60) -> list[dict]:
    random.seed(42)
    inserted: list[dict] = []

    with _connect(server=server, database=DB_NAME, driver=driver) as conn:
        cur = conn.cursor()

        for idx in range(candidate_count):
            first = random.choice(FIRST_NAMES)
            middle = random.choice(["", random.choice(FIRST_NAMES)])
            last = random.choice(LAST_NAMES)
            full_name = " ".join([x for x in [first, middle, last] if x]).strip()

            candidate_id = 200000 + idx + 1
            title = random.choice(DATA_SCIENCE_TITLES)
            employer = random.choice(EMPLOYERS)
            years = random.randint(0, 12)
            saudi_expat = random.choice(["Saudi", "Expat"])
            degree = random.choices(DEGREES, weights=[0.55, 0.35, 0.10])[0]
            major = random.choice(MAJORS)
            institution = random.choice(INSTITUTIONS)
            gpa = round(random.uniform(2.1, 4.0), 2)
            skill_set = random.choice(SKILL_POOLS)
            random.shuffle(skill_set)
            selected_skills = skill_set[: random.randint(4, 5)]

            quality_band = random.choices(["high", "medium", "low"], weights=[0.25, 0.50, 0.25])[0]
            if quality_band == "high":
                indreason, numreason, verbreason = "95", "94", "96"
                candidate_flag = "AOC"
            elif quality_band == "medium":
                indreason, numreason, verbreason = "78", "74", "77"
                candidate_flag = "ASC"
            else:
                indreason, numreason, verbreason = "58", "55", "57"
                candidate_flag = "SED"

            created_on = date.today() - timedelta(days=random.randint(0, 1200))
            resume_date = created_on + timedelta(days=random.randint(0, 30))
            highest_job_req_id = str(random.randint(15000, 18999))
            highest_application_id = str(random.randint(4400000, 4999999))
            application_status = random.choice([
                "Interview Completed",
                "Shortlisted",
                "Application Review",
                "Availability Confirmation",
            ])
            application_status_code = random.choice([0, 1, 2, 3])
            phone = f"+9665{random.randint(10000000, 99999999)}"
            email = f"{first.lower()}.{last.lower()}{idx+1}@example.com"

            summary = _build_summary(
                full_name=full_name,
                title=title,
                years=years,
                top_skills=selected_skills,
                degree=degree,
                major=major,
            )
            text_tokens = (
                f"{full_name} {email} {phone} {summary} "
                f"Experience title {title} employer {employer}. Skills: {', '.join(selected_skills)}."
            )

            cur.execute(
                """
                INSERT INTO dbo.T_IIR_ARIF_CANDIDATE (
                    CANDIDATE_ID, GIVENNAME, MIDDLENAME, SURNAME, CREATED_ON,
                    CURRENT_EMPLOYER, CURRENT_JOB_TITLE, YEARS_OF_EXPERIENCE, COUNTRY,
                    NATIONAL_ID, SAUDI_EXPAT, GPA, LAST_MODIFIED, SOURCE_OF_APPLICATION,
                    GENDER, HIGHEST_JOB_REQ_ID, HIGHEST_APPLICATION_ID, HIGHEST_APPLICATION_STATUS,
                    APPLICATION_STATUS_CODE, RESUME_UPLOADED, RESUME_DATE, RESUME_FILE_TYPE,
                    RESUME_PROCESSED, EDUCATION_EXTRACTED, EXPERIENCE_EXTRACTED, SKILLS_EXTRACTED,
                    SUMMARY_EXTRACTED, WILD_SEARCH_EXTRACTED, CANDIDATE_FLAG, INDREASON,
                    NUMREASON, VERBREASON, SUMMARY, TEXT_TOKENS
                )
                OUTPUT INSERTED.ARIF_ID
                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, 1, ?, 'pdf',
                    1, 1, 1, 1,
                    1, 1, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    candidate_id,
                    first,
                    middle if middle else None,
                    last,
                    created_on,
                    employer,
                    title,
                    str(years),
                    "Saudi Arabia",
                    str(random.randint(1000000000, 1999999999)),
                    saudi_expat,
                    f"{gpa:.2f}",
                    date.today(),
                    "SF",
                    _random_gender(),
                    highest_job_req_id,
                    highest_application_id,
                    application_status,
                    application_status_code,
                    resume_date,
                    candidate_flag,
                    indreason,
                    numreason,
                    verbreason,
                    summary,
                    text_tokens,
                ),
            )
            arif_id = int(cur.fetchone()[0])

            edu_start = random.randint(2008, 2019)
            edu_end = edu_start + random.randint(3, 5)
            cur.execute(
                """
                INSERT INTO dbo.T_IIR_ARIF_EDUCATION (
                    ARIF_ID, CANDIDATE_ID, DEGREE, MAJOR, INSTITUTION,
                    STARTDATE, ENDDATE, NORM_DEGREE, NORM_INSTITUTION,
                    NORM_STARTDATE, NORM_ENDDATE
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    arif_id,
                    candidate_id,
                    degree,
                    major,
                    institution,
                    str(edu_start),
                    str(edu_end),
                    degree.lower(),
                    institution.lower(),
                    date(edu_start, 1, 1),
                    date(edu_end, 12, 31),
                ),
            )

            exp_rows = max(1, random.randint(1, 3))
            for exp_i in range(exp_rows):
                exp_years = max(0, years - exp_i * random.randint(1, 3))
                start_year = random.randint(2013, 2024)
                end_year = min(2026, start_year + random.randint(1, 4))
                exp_title = random.choice(DATA_SCIENCE_TITLES)
                exp_employer = random.choice(EMPLOYERS)
                cur.execute(
                    """
                    INSERT INTO dbo.T_IIR_ARIF_EXPERIENCE (
                        ARIF_ID, CANDIDATE_ID, TITLE, EMPLOYER, STARTDATE, ENDDATE,
                        COUNTRY, YEARS_OF_EXPERIENCE, NORM_TITLE, NORM_EMPLOYER,
                        NORM_STARTDATE, NORM_ENDDATE
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        arif_id,
                        candidate_id,
                        exp_title,
                        exp_employer,
                        f"Jan {start_year}",
                        f"Dec {end_year}",
                        "Saudi Arabia",
                        exp_years,
                        exp_title.lower(),
                        exp_employer.lower(),
                        date(start_year, 1, 1),
                        date(end_year, 12, 31),
                    ),
                )

            for skill in selected_skills:
                cur.execute(
                    """
                    INSERT INTO dbo.T_IIR_ARIF_SKILLS (ARIF_ID, CANDIDATE_ID, ORG_SKILL, NORM_SKILL)
                    VALUES (?, ?, ?, ?)
                    """,
                    (arif_id, candidate_id, skill, skill.lower()),
                )

            inserted.append(
                {
                    "arif_id": arif_id,
                    "candidate_id": candidate_id,
                    "full_name": full_name,
                    "title": title,
                    "employer": employer,
                    "years": years,
                    "degree": degree,
                    "major": major,
                    "skills": selected_skills,
                    "summary": summary,
                    "quality_band": quality_band,
                }
            )

    return inserted


def create_resume_pdfs(candidates: list[dict]) -> None:
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    for candidate in candidates:
        pdf_path = RESUME_DIR / f"{candidate['candidate_id']}.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=LETTER)

        y = 760
        lines = [
            f"Candidate ID: {candidate['candidate_id']}",
            f"Name: {candidate['full_name']}",
            f"Target Role: {candidate['title']}",
            f"Current/Recent Employer: {candidate['employer']}",
            f"Experience: {candidate['years']} years",
            f"Education: {candidate['degree']} in {candidate['major']}",
            f"Skills: {', '.join(candidate['skills'])}",
            f"Quality Band: {candidate['quality_band']}",
            "",
            "Summary:",
            candidate["summary"],
            "",
            "Projects:",
            "- Built and evaluated predictive models for business KPIs.",
            "- Cleaned and transformed messy datasets into reusable features.",
            "- Communicated findings to technical and non-technical stakeholders.",
        ]

        for line in lines:
            c.drawString(50, y, line[:110])
            y -= 18
            if y < 60:
                c.showPage()
                y = 760

        c.save()


def print_counts(server: str, driver: str) -> None:
    with _connect(server=server, database=DB_NAME, driver=driver) as conn:
        cur = conn.cursor()
        for table in [
            "dbo.T_IIR_ARIF_CANDIDATE",
            "dbo.T_IIR_ARIF_EDUCATION",
            "dbo.T_IIR_ARIF_EXPERIENCE",
            "dbo.T_IIR_ARIF_SKILLS",
        ]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"{table}: {count}")


def main() -> None:
    driver = _pick_driver()
    server = _find_working_server(driver)
    print(f"Connected using server={server}, driver={driver}")

    create_database(server=server, driver=driver)
    print("Database ensured: arif_recruitment")

    create_tables(server=server, driver=driver)
    print("Tables created.")

    candidates = seed_data(server=server, driver=driver, candidate_count=60)
    print(f"Seeded {len(candidates)} candidates and related rows.")

    create_resume_pdfs(candidates)
    print(f"Generated {len(candidates)} resume PDFs in: {RESUME_DIR}")

    print_counts(server=server, driver=driver)


if __name__ == "__main__":
    main()
