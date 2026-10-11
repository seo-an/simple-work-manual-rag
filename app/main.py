"""Backoffice-facing, read-only work-manual API.

This API is transport-neutral: UI/BFF, CLI, and agents can use the same contract.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import sqlite3
from typing import Callable, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import catalog
from .config import Settings
from .generation import generate
from .ingest import build_index
from .schemas import (
    FilePage, FileRecord, IndexStatus, ManualDetail, ManualPage,
    QueryRequest, QueryResponse,
)
from .search import retrieve

T = TypeVar("T")
AUTH_ERRORS = {401: {"description": "서비스 키 누락 또는 불일치"}}
INDEX_ERRORS = {503: {"description": "검색 색인이 준비되지 않음"}}


def _read_catalog(operation: Callable[..., T], *args, **kwargs) -> T:
    try:
        return operation(*args, **kwargs)
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(status_code=503, detail="search index unavailable") from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    cfg.validate()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not cfg.db_path.is_file():
            build_index(cfg.data_dir, cfg.db_path)
        yield

    app = FastAPI(
        title="Simple Work Manual API",
        version="0.2.0",
        description=(
            "가상 조직의 Excel 파일 목록과 Markdown 업무 매뉴얼을 검색·열람하는 "
            "백오피스 연동용 조회 API. 실제 사내 자료나 사용자 권한 모델은 포함하지 않습니다. "
            "기본 extractive 모드는 LLM을 호출하지 않습니다."
        ),
        openapi_tags=[
            {"name": "System", "description": "상태 확인"},
            {"name": "Search", "description": "자연어 근거 검색"},
            {"name": "Files", "description": "Excel 파일 레지스트리"},
            {"name": "Manuals", "description": "Markdown 업무 매뉴얼"},
            {"name": "Index", "description": "읽기 전용 색인 상태"},
        ],
        lifespan=lifespan,
    )

    def authorize(
        x_service_key: str | None = Header(
            default=None, alias="X-Service-Key",
            description="서버 간 인증용 키. 브라우저 코드에 포함하지 마세요.",
        ),
    ) -> None:
        if cfg.auth_mode == "dev":
            return
        if not x_service_key or not hmac.compare_digest(
            x_service_key, cfg.service_api_key
        ):
            raise HTTPException(status_code=401, detail="invalid service credentials")

    @app.get(
        "/api/v1/health", tags=["System"], summary="서비스 상태 확인",
        description="민감한 파일명이나 인덱스 통계를 노출하지 않는 공개 헬스 체크.",
    )
    def health() -> dict:
        return {"status": "ok" if cfg.db_path.is_file() else "not_ready"}

    @app.post(
        "/api/v1/query", response_model=QueryResponse, tags=["Search"],
        summary="자연어 질문에 근거 기반 답변 반환",
        description="기존 연동 계약 유지. 근거가 없을 때 insufficient_evidence를 반환합니다.",
        dependencies=[Depends(authorize)], responses={**AUTH_ERRORS, **INDEX_ERRORS},
    )
    def query(request: QueryRequest) -> QueryResponse:
        sources = _read_catalog(retrieve, request.question, cfg.db_path, request.top_k)
        answer = generate(request.question, sources, cfg)
        return QueryResponse(
            status="answered" if sources else "insufficient_evidence",
            answer=answer,
            sources=[s.to_dict() for s in sources],
            mode=cfg.llm_mode,
        )

    @app.get(
        "/api/v1/files", response_model=FilePage, tags=["Files"],
        summary="파일 목록 검색",
        description="파일명·설명·키워드·등록 경로의 부분 일치 검색. 조회 결과는 등록 정보이며 실재·접근권한을 증명하지 않습니다.",
        dependencies=[Depends(authorize)], responses={**AUTH_ERRORS, **INDEX_ERRORS},
    )
    def files(
        q: str | None = Query(default=None, min_length=1, max_length=200, description="검색어"),
        extension: str | None = Query(default=None, min_length=1, max_length=16, description="확장자, 예: docx"),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> FilePage:
        return FilePage(**_read_catalog(
            catalog.list_files, cfg.db_path, q=q,
            extension=extension, limit=limit, offset=offset,
        ))

    @app.get(
        "/api/v1/files/{file_id}", response_model=FileRecord, tags=["Files"],
        summary="파일 상세정보 조회",
        dependencies=[Depends(authorize)],
        responses={**AUTH_ERRORS, **INDEX_ERRORS, 404: {"description": "파일 ID 없음"}},
    )
    def file_detail(file_id: str) -> FileRecord:
        item = _read_catalog(catalog.get_file, cfg.db_path, file_id)
        if item is None:
            raise HTTPException(status_code=404, detail="file_not_found")
        return FileRecord(**item)

    @app.get(
        "/api/v1/manuals", response_model=ManualPage, tags=["Manuals"],
        summary="업무 매뉴얼 목록 조회",
        description="문서 제목 및 항목 내용 기준 검색. SAMPLE_POLICY 메타데이터는 제외합니다.",
        dependencies=[Depends(authorize)], responses={**AUTH_ERRORS, **INDEX_ERRORS},
    )
    def manuals(
        q: str | None = Query(default=None, min_length=1, max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> ManualPage:
        return ManualPage(**_read_catalog(
            catalog.list_manuals, cfg.db_path, q=q, limit=limit, offset=offset,
        ))

    @app.get(
        "/api/v1/manuals/{manual_id:path}", response_model=ManualDetail,
        tags=["Manuals"], summary="업무 매뉴얼 상세 항목 조회",
        description=(
            "manuals/ 폴더 아래의 상대 파일 경로를 지정합니다. "
            "예: family_events.md. 중첩 파일은 dir/name.md 형태로 지정합니다."
        ),
        dependencies=[Depends(authorize)],
        responses={**AUTH_ERRORS, **INDEX_ERRORS, 404: {"description": "매뉴얼 ID 없음"}},
    )
    def manual_detail(manual_id: str) -> ManualDetail:
        item = _read_catalog(catalog.get_manual, cfg.db_path, manual_id)
        if item is None:
            raise HTTPException(status_code=404, detail="manual_not_found")
        return ManualDetail(**item)

    @app.get(
        "/api/v1/index/status", response_model=IndexStatus,
        tags=["Index"], summary="색인 현황 조회",
        description="현재 SQLite 색인에 등록된 공개 샘플 데이터 개수와 파일 수정 시각.",
        dependencies=[Depends(authorize)], responses={**AUTH_ERRORS, **INDEX_ERRORS},
    )
    def get_index_status() -> IndexStatus:
        return IndexStatus(**_read_catalog(catalog.index_status, cfg.db_path))

    return app


app = create_app()
