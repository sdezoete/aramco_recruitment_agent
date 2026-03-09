from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.ats import router as ats_router
from app.api.routes.recruitment import router as recruitment_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aramco Recruitment Agent API",
        version="0.1.0",
        description="Development API for recruitment workflow and ATS mock integration.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "null",  # Some browsers use origin 'null' for local file previews.
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(recruitment_router)
    app.include_router(ats_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
