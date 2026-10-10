"""Transport-neutral RAG API for Slack adapter now and Next.js later."""
from __future__ import annotations
from contextlib import asynccontextmanager
import hmac
import sqlite3
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .config import Settings
from .generation import generate
from .ingest import build_index
from .search import retrieve

class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=5)

class QueryResponse(BaseModel):
    status: str
    answer: str
    sources: list[dict]
    mode: str


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    cfg.validate()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not cfg.db_path.is_file():
            build_index(cfg.data_dir, cfg.db_path)
        yield

    app = FastAPI(title="Simple Work Manual RAG", version="0.1.0", lifespan=lifespan)

    def authorize(x_service_key: str | None = Header(default=None)) -> None:
        if cfg.auth_mode == "dev":
            return
        if not x_service_key or not hmac.compare_digest(x_service_key, cfg.service_api_key):
            raise HTTPException(status_code=401, detail="invalid service credentials")

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok" if cfg.db_path.is_file() else "not_ready"}

    @app.post("/api/v1/query", response_model=QueryResponse, dependencies=[Depends(authorize)])
    def query(request: QueryRequest) -> QueryResponse:
        try:
            sources = retrieve(request.question, cfg.db_path, request.top_k)
        except sqlite3.Error:
            raise HTTPException(status_code=503, detail="search index unavailable")
        answer = generate(request.question, sources, cfg)
        return QueryResponse(
            status="answered" if sources else "insufficient_evidence",
            answer=answer,
            sources=[s.to_dict() for s in sources],
            mode=cfg.llm_mode,
        )

    return app

app = create_app()
