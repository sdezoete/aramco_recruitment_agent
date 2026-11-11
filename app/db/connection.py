"""pyodbc connection to SQL Server from DB_* settings."""
from __future__ import annotations

import pyodbc

from app.config import Settings

pyodbc.pooling = True


def connection_string(s: Settings) -> str:
    parts = [
        f"DRIVER={{{s.DB_DRIVER}}}",
        f"SERVER={s.DB_SERVER}",
        f"DATABASE={s.DB_NAME}",
        f"Encrypt={'yes' if s.DB_ENCRYPT else 'no'}",
        f"TrustServerCertificate={'yes' if s.DB_TRUST_SERVER_CERTIFICATE else 'no'}",
        "APP=RecruitmentAgent",
    ]
    if s.DB_TRUSTED_CONNECTION:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={s.DB_USER}")
        parts.append("PWD={" + s.DB_PASSWORD.replace("}", "}}") + "}")
    return ";".join(parts)


def connect(s: Settings) -> pyodbc.Connection:
    conn = pyodbc.connect(connection_string(s), timeout=10, autocommit=True)
    return conn
