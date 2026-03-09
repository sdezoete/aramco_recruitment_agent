from __future__ import annotations

import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=DESKTOP-PI79SVO\\SQLEXPRESS;"
    "DATABASE=arif_recruitment;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

SQL = """
IF OBJECT_ID('dbo.AGENT_SESSION_MEMORY','U') IS NULL
BEGIN
    CREATE TABLE dbo.AGENT_SESSION_MEMORY (
        session_id NVARCHAR(128) NOT NULL PRIMARY KEY,
        requisition_id NVARCHAR(128) NULL,
        state_json NVARCHAR(MAX) NOT NULL,
        created_at DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2(7) NOT NULL DEFAULT SYSUTCDATETIME()
    );
END;
"""


def main() -> None:
    with pyodbc.connect(CONN_STR, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(SQL)
    print("AGENT_SESSION_MEMORY ensured")


if __name__ == "__main__":
    main()
