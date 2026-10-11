"""Typed HTTP response contracts rendered directly into FastAPI OpenAPI docs."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class FileRecord(BaseModel):
    file_id: str = Field(description="엑셀 파일 목록의 고유 ID", examples=["doc-001"])
    title: str = Field(description="문서 또는 서식 이름")
    summary: str = Field(description="파일 설명")
    location: str = Field(description="목록에 등록된 경로. 실제 접근 권한을 보장하지 않음")
    extension: str = Field(description="확장자(점 제외)", examples=["docx"])
    keywords: str = Field(description="Excel 원본의 검색 키워드 문자열")


class FilePage(BaseModel):
    items: list[FileRecord]
    total: int = Field(ge=0, description="필터 조건에 맞는 전체 파일 수")
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ManualSummary(BaseModel):
    manual_id: str = Field(description="manuals/ 이하 상대 Markdown 경로", examples=["family_events.md"])
    title: str
    section_count: int = Field(ge=1)


class ManualPage(BaseModel):
    items: list[ManualSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ManualSection(BaseModel):
    heading: str
    content: str = Field(description="Markdown 색인에서 추출한 근거 내용")
    source_id: str = Field(description="query API의 sources[].source_id와 같은 형식")


class ManualDetail(BaseModel):
    manual_id: str
    title: str
    sections: list[ManualSection]


class IndexStatus(BaseModel):
    status: str = Field(description="색인 준비 상태", examples=["ready"])
    files: int = Field(ge=0)
    manuals: int = Field(ge=0)
    sections: int = Field(ge=0)
    indexed_at: str = Field(description="SQLite 인덱스 파일 수정 시각 (UTC ISO 8601)")


class SourceEvidence(BaseModel):
    source_id: str
    kind: str = Field(description="file 또는 manual")
    title: str
    section: str
    excerpt: str
    location: str | None = None
    extension: str | None = None
    score: float = 0


class QueryRequest(BaseModel):
    question: str = Field(
        min_length=1, max_length=1000,
        description="한국어 자연어 질문", examples=["경조휴가 규정을 알려줘"],
    )
    top_k: int = Field(default=3, ge=1, le=5, description="최대 근거 자료 수")

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be blank")
        return value


class QueryResponse(BaseModel):
    status: str = Field(description="answered 또는 insufficient_evidence")
    answer: str
    sources: list[SourceEvidence]
    mode: str = Field(description="extractive 또는 openai_compatible")
