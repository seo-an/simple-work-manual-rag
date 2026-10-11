# 백오피스 연동 API 계약서 (v0.2)

> **범위:** 가상 조직 샘플 Excel 파일 목록과 Markdown 업무 매뉴얼. 실제 회사 자료·권한 체계·운영 배포를 의미하지 않는다.
>
> **상태:** 구현된 조회 API의 사용 계약. 웹 백오피스 구현과 실제 인계/운영 적용은 별도 단계다.

## 통합 방식

백오피스 **브라우저 → 백오피스 백엔드(BFF) → RAG API** 순으로 호출한다.
사용자 인증/화면 권한 확인은 백오피스 백엔드에서 수행한다.
RAG API의 `X-Service-Key`는 **서비스 간 공유키**이므로 절대로 브라우저 JavaScript, HTML, 모바일 앱, 공개 Git, API 응답에 포함하지 않는다.

샘플 API: `http://127.0.0.1:23232`, Swagger UI: `/docs`, OpenAPI JSON: `/openapi.json`.
프로덕션을 흉내 낸 테스트는 `AUTH_MODE=service_key`로 하고 HTTPS 역방향 프록시/터널을 이용한다.
`AUTH_MODE=dev`는 development/sample에서만 허용한다.

### 요청 / 응답 공통

- JSON 콘텐츠 타입: `application/json`
- API 버전: `/api/v1`
- 인증 헤더(health 제외): `X-Service-Key: <service key>`
- 파일/매뉴얼 목록: `{items: [...], total: 정수, limit: 정수, offset: 정수}`
- 성공: 200
- 인증 실패: 401 `{"detail":"invalid service credentials"}`
- 미존재 ID: 404 `{"detail":"file_not_found"}` 또는 `{"detail":"manual_not_found"}`
- 입력 오류: 422 (FastAPI 표준 ValidationError)
- 색인 누락/SQLite 오류: 503 `{"detail":"search index unavailable"}`
- `source_id`는 인용 근거를 연결하는 식별자이지, 링크나 사용자 다운로드 권한이 아니다.
- `indexed_at`은 색인 파일의 수정 시각으로, 원본 문서의 최신 변경 시각은 아니다.

## 엔드포인트

| Method | Path | 기능 | Auth |
|---|---|---|---|
| GET | /api/v1/health | 서비스 프로세스 상태 | 불필요 |
| POST | /api/v1/query | 자연어 질문 → 근거 기반 답변 | 필요 |
| GET | /api/v1/files | 파일 목록·검색·확장자 필터·페이지 조회 | 필요 |
| GET | /api/v1/files/{file_id} | Excel 파일 레지스트리의 단일 항목 | 필요 |
| GET | /api/v1/manuals | 매뉴얼 목록·내용 검색·페이지 조회 | 필요 |
| GET | /api/v1/manuals/{manual_id} | Markdown 문서의 섹션별 내용 | 필요 |
| GET | /api/v1/index/status | 색인에 등록된 파일·매뉴얼·섹션 수 | 필요 |

매뉴얼 ID는 `manuals/` 기준 상대 경로를 사용한다. 예: `family_events.md`.
폴더가 중첩된 경우 `department/name.md`처럼 지정할 수 있다.
검색 결과에서 반환하는 `source_id`는 `manuals/family_events.md#경조휴가 예시` 형식이다.

## 화면 개발 기준 시나리오

### 파일 목록 페이지

`GET /api/v1/files?q=기안서&limit=20&offset=0`

```json
{
  "items": [
    {
      "file_id": "doc-001",
      "title": "(Excel에 등록된 파일 제목)",
      "summary": "(등록된 파일 설명)",
      "location": "(등록된 경로)",
      "extension": "docx",
      "keywords": "(등록된 키워드)"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

위 JSON은 **응답 형식 예시**이며 실제 실행 결과의 전체 문구를 복제한 것이 아니다.
파일 클릭 시 `GET /api/v1/files/doc-001`을 호출한다. 등록 위치는 문자열이지 다운로드 URL이 아니다.

### 매뉴얼 탐색 페이지

`GET /api/v1/manuals?q=경조휴가&limit=20&offset=0`

```json
{
  "items": [
    {"manual_id": "family_events.md", "title": "경조사 지원 규정 (가상 기업 샘플)", "section_count": 3}
  ],
  "total": 1, "limit": 20, "offset": 0
}
```

위 예시는 현재 샘플 매뉴얼의 제목과 조회 가능한 섹션 3개를 기준으로 작성한 응답 예시다.
문서 클릭 시 `GET /api/v1/manuals/family_events.md`로 내용을 읽고, 응답의 `sections[].source_id`를 근거 참조 ID로 사용한다.

### 자연어 검색

`POST /api/v1/query`

```json
{"question": "경조휴가 규정을 알려줘", "top_k": 3}
```

기존 응답 필드 `status`, `answer`, `sources`, `mode`는 변경하지 않는다.

- `answered`: 등록된 문서 근거에서 조회 결과를 반환
- `insufficient_evidence`: 근거를 찾지 못함. 추측으로 채우지 않음
- 기본 `mode=extractive`: **LLM 호출 없음**, 상위 근거 발췌 응답
- 선택적 `openai_compatible`: 연결 계약은 있으나 실제 LLM 라이브 검증은 별도

### 색인 상태 확인

`GET /api/v1/index/status`는 색인 파일 기반 `status=ready`, `files`, `manuals`, `sections`, `indexed_at`을 반환한다. 읽기 전용 API이며 색인 재구성은 수행하지 않는다.

## 운영·보안 경계

- 데이터 정본은 `data/sample/file_registry.xlsx`, `data/sample/manuals/*.md`다.
- 문서 변경 후 `python3 -m scripts.reindex`로 재색인한다. 데이터 읽기/색인 오류 시 기존 색인을 덮어쓰지 않도록 원자 교체를 사용한다.
- 모든 조회와 검색은 SQLite 인덱스 읽기 전용 연결을 사용한다.
- 파일 업로드, 등록/수정/삭제, 문서 승인, 파일 실재 여부 검증, 사용자별 접근 제어, 다운로드, UI 및 배포 모니터링은 **이번 프로젝트 미구현**이다.
- 제공 샘플은 전부 가상 사례이며 실제 취업규칙·사내 정책·법률 근거로 사용할 수 없다.
- 등록 문서가 대폭 증가할 경우 검색 인덱스 및 캐시, 권한 필터, 검색 성능 측정이 별도로 필요하다.

## 재현 및 검증

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m scripts.evaluate
docker compose -f infrastructure/compose.yaml up -d --build
```

Swagger UI `/docs`에서 인증 및 Query/Files/Manuals/Index를 순서대로 확인한다.
서버 키는 로컬 `.env` 또는 비밀 관리 시스템에 두고 문서·스크린샷에 노출하지 않는다.

### 포트폴리오에서의 정확한 설명

"사내 백오피스 연동을 가정하여 Excel·Markdown 기반 업무 문서의 목록/상세 조회와 근거 기반 질의 API를 설계·구현하고, OpenAPI 계약 및 예외 처리·검증 테스트를 문서화했다."

**실제 담당자에게 전달했다거나 운영 배포·사용자 테스트를 완료했다는 문구는 실제 증빙이 있을 때에만 사용한다.**
