from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQL Server connection
    DB_DRIVER: str = "{ODBC Driver 18 for SQL Server}"
    DB_SERVER: str = "DESKTOP-PI79SVO\\SQLEXPRESS"
    DB_NAME: str = "arif_recruitment"
    DB_TRUSTED_CONNECTION: str = "yes"
    DB_USERNAME: str | None = None
    DB_PASSWORD: str | None = None

    # ATS API (internal network)
    ATS_BASE_URL: str = "https://internal-ats.example.local"
    ATS_TOKEN: str | None = None
    ATS_TIMEOUT_SECONDS: int = 20

    # Session memory behavior
    SESSION_MEMORY_BACKEND: str = "sql"  # sql | file
    SESSION_MEMORY_DIR: str = "data/session_memory"


settings = Settings()
