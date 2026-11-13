"""Tiny local FastAPI server for the dashboard.

POST /leads   queue a new enquiry (the "webhook")
GET  /leads   processed leads and the pending queue
GET  /runs    run history
POST /run     process leads now (pending webhook leads or the sample file)

Local use only: there is no authentication, so keep it bound to 127.0.0.1.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from leadgen.config import ConfigError, Settings, load_rulebook
from leadgen.llm import LLMConfigError
from leadgen.models import Lead
from leadgen.runner import SourceError, load_leads, run_leads
from leadgen.storage import LocalStorage, Storage


class NewLead(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    channel: str = Field(default="webhook", max_length=50)
    message: str = Field(min_length=1, max_length=5000)


class RunRequest(BaseModel):
    source: Literal["webhook", "sample"] = "webhook"
    dry_run: bool = False
    limit: int | None = Field(default=None, ge=1)


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    storage = storage or LocalStorage(settings.resolved_data_dir())
    app = FastAPI(title="Lead agent local API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "mock" if settings.mock_llm else settings.llm_provider}

    @app.post("/leads", status_code=201)
    def add_lead(new_lead: NewLead) -> dict[str, str]:
        lead = Lead(**new_lead.model_dump()).with_defaults()
        storage.enqueue_lead(lead)
        return {"id": lead.id, "status": "queued"}

    @app.get("/leads")
    def list_leads() -> dict[str, list]:
        return {
            "leads": [record.model_dump() for record in storage.list_records()],
            "pending": [lead.model_dump() for lead in storage.pending_leads()],
        }

    @app.get("/runs")
    def list_runs() -> dict[str, list]:
        return {"runs": [run.model_dump() for run in storage.list_runs()]}

    @app.post("/run")
    async def start_run(request: RunRequest) -> dict:
        try:
            rulebook = load_rulebook(settings.preset, settings.client_config)
            leads = load_leads(request.source, storage)
            outcome = await run_leads(
                leads,
                settings=settings,
                rulebook=rulebook,
                storage=storage,
                source=request.source,
                dry_run=request.dry_run,
                limit=request.limit,
            )
        except (ConfigError, LLMConfigError, SourceError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "run": outcome.run.model_dump(),
            "leads": [record.model_dump() for record in outcome.records],
        }

    return app


def main() -> None:
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
