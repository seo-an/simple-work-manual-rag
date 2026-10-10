# Simple Work Manual RAG

**Python + FastAPI + SQLite · Excel + Markdown · Public 샘플 RAG API**

이 프로젝트의 데이터는 특정 회사 문서를 익명화하여 전재한 것이 아니라 새로 작성한 **가상 조직의 예시**입니다. 회사 고유 규정, 경조휴가 일수, 파일 위치는 실제 근로조건이 아닙니다.

## 구현 기능
- Hybrid retrieval: Excel 파일 목록 + Markdown 업무 규정 검색 (SQLite, FTS5 인덱스 생성 시도, 한국어 별칭 점수화)
- Evidence grounding: 출처 배열과 근거 부족 시 insufficient_evidence 반환
- Data-driven knowledge: Excel/Markdown 교체 후 재색인
- RAG evaluation: 오프라인 질문 세트 및 unittest
- Transport-neutral API: Hermes/Slack 및 추후 Next.js에서 동일하게 호출

## 로컬 실행

Python 3.12 권장. 저장소 루트에서:

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt
    python3 -m scripts.reindex
    uvicorn app.main:app --host 127.0.0.1 --port 23232

API:
- GET http://127.0.0.1:23232/api/v1/health
- POST http://127.0.0.1:23232/api/v1/query
- JSON 요청: {"question":"기안서 양식 어디 있어?"}
- OpenAPI 문서: http://127.0.0.1:23232/docs

Docker:

    cp .env.example .env
    mkdir -p runtime
    docker compose -f infrastructure/compose.yaml up --build -d

포트는 127.0.0.1:23232로만 공개한다. Hermes 연결은 별도 Private agent-config PR에서 수행한다.

## 데이터 교체

- data/sample/manuals/*.md: 첫 레벨 제목과 2단계 소제목 사용
- data/sample/file_registry.xlsx: 첫 시트 헤더 file_id,title,summary,location,extension,keywords
- 실제 사내자료는 Git에 올리지 않고 data/private/ 등을 사용
- DATA_DIR 환경변수로 새로운 데이터 폴더 지정, 이후 python3 -m scripts.reindex
- 원자적 SQLite 재색인으로 잘못된 입력 시 기존 검색 DB 보호

## LLM

기본 LLM_MODE=extractive는 **LLM을 호출하지 않는 무료 검색 근거 응답**이다. 실제 RAG 생성 실험에는 HTTPS 기반 OpenAI 호환 API용 환경변수 LLM_MODE=openai_compatible, LLM_API_BASE, LLM_API_KEY, LLM_MODEL을 설정한다. 답변 생성 실패 시 근거 문구를 반환한다. 출처는 검색기가 생성한다. 이번 PoC에서 실제 LLM API의 라이브 응답은 아직 검증하지 않았다.

## 인증

개발용 샘플 데이터에서만 APP_ENV=development, DATA_MODE=sample, AUTH_MODE=dev 조합의 토큰 우회를 허용한다. 운영 환경은 서비스 간 X-Service-Key 검증이 필요하다. 사용자의 Access/Refresh Token 검증 상태 머신은 별도 계약과 Mock 테스트로만 구현되며, 실운영 로그인·토큰 저장·회전은 후속 과제이다.

## 테스트

    python3 -m unittest discover -s tests -p 'test_*.py' -v
    python3 -m scripts.evaluate

오프라인 테스트 질문 6개는 공개용 소규모 예제일 뿐 실제 환경의 검색 정확도를 의미하지 않는다.

## 후속 과제
- 새 Hermes 상담봇과 Slack DM 연결 (Private 저장소 별도 PR)
- Next.js 프론트, 사용자별 접근권한, 실제 사내자료 반영
- 고충 접수·신고서 작성 (이번 범위 제외)
