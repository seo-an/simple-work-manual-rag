"""Offline top-1 retrieval + no-evidence evaluation (no LLM required)."""
from __future__ import annotations
import json
from app.config import Settings
from app.ingest import build_index
from app.search import retrieve

CASES = [
    ("기안서 양식 어디 있나요?", "file", "doc-001"),
    ("출장신청서 파일 위치 알려줘", "file", "doc-002"),
    ("경조휴가 규정을 알려줘", "manual", "family_events.md"),
    ("출장 승인 절차는?", "manual", "travel.md"),
    ("휴게실 냉장고 사용 규칙", "manual", "break_room.md"),
    ("양자 컴퓨터 대여 절차", "none", None),
]


def evaluate(db_path):
    outcomes = []
    for query, kind, expected in CASES:
        sources = retrieve(query, db_path, limit=3)
        # The answer generator uses sources[0]. Recall@3 alone can conceal wrong answers.
        first = sources[0] if sources else None
        passed = (
            first is not None and first.kind == kind and expected in first.source_id
            if expected else not sources
        )
        outcomes.append({
            "question": query,
            "pass": passed,
            "top_source": first.source_id if first else None,
            "source_ids": [s.source_id for s in sources],
        })
    return {"total": len(outcomes), "passed": sum(i["pass"] for i in outcomes), "cases": outcomes}


def main():
    cfg = Settings.from_env()
    cfg.validate()
    if not cfg.db_path.is_file():
        build_index(cfg.data_dir, cfg.db_path)
    print(json.dumps(evaluate(cfg.db_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
