from __future__ import annotations

import pyodbc

from app.config import settings


def open_db_connection() -> pyodbc.Connection:
    """Open a SQL Server connection for a single unit of work."""
    if settings.DB_TRUSTED_CONNECTION.lower() in ("yes", "true", "1"):
        conn_str = (
            f"DRIVER={settings.DB_DRIVER};"
            f"SERVER={settings.DB_SERVER};"
            f"DATABASE={settings.DB_NAME};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        return pyodbc.connect(conn_str, autocommit=True)

    if not settings.DB_USERNAME or not settings.DB_PASSWORD:
        raise ValueError("DB_USERNAME and DB_PASSWORD are required when trusted connection is disabled.")

    conn_str = (
        f"DRIVER={settings.DB_DRIVER};"
        f"SERVER={settings.DB_SERVER};"
        f"DATABASE={settings.DB_NAME};"
        f"UID={settings.DB_USERNAME};"
        f"PWD={settings.DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True)
