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
    ATS_USE_MOCK: bool = True
    ATS_RESUME_STORAGE_PATH: str = "candidate_pdf_files"

    # Session memory behavior
    SESSION_MEMORY_BACKEND: str = "sql"  # sql | file
    SESSION_MEMORY_DIR: str = "data/session_memory"

    # AI provider settings
    USE_LOCAL_AI: bool = False
    LOCAL_LLM_BASE_URL: str | None = None
    LOCAL_LLM_MODEL: str = "local-chat-model"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"


settings = Settings()
