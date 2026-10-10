"""Hybrid deterministic lexical matching with exact file metadata priority."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import closing
import re
import sqlite3

STOP = {"어디", "어떻게", "알려줘", "알려주세요", "할까요", "있나요", "해야", "대한", "뭐야", "뭔가요", "위치", "관련", "절차", "규정", "방법", "사용", "서류", "파일", "자료", "안내"}
SYNONYMS = {
    "기안서": ("품의서", "품의", "기안", "결재"),
    "양식": ("서식", "신청서", "문서"),
    "경조사": ("경조휴가", "경조", "결혼", "조의"),
    "출장": ("여비", "교통비", "출장비"),
    "구매": ("비품", "물품", "구입"),
    "휴게실": ("탕비실", "라운지", "냉장고"),
}

@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    title: str
    section: str
    excerpt: str
    location: str | None = None
    extension: str | None = None
    score: float = 0

    def to_dict(self) -> dict:
        return asdict(self)


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def terms(question: str) -> list[str]:
    words = re.findall(r"[가-힣a-zA-Z0-9]+", question.lower())
    words = [w for w in words if len(w) >= 2 and w not in STOP]
    expanded = list(words)
    for word in words:
        for stem, variants in SYNONYMS.items():
            if stem in word or any(v in word for v in variants):
                expanded += [stem, *variants]
    return list(dict.fromkeys(expanded))


def _score(question: str, title: str, section: str, body: str, kind: str) -> float:
    q = compact(question)
    ti, se, bo = compact(title), compact(section), compact(body)
    score = 0.0
    for token in terms(question):
        if len(token) < 2:
            continue
        t = compact(token)
        weight = 1.0 if t in q else 0.24
        if t in ti:
            score += weight * 5
        if t in se:
            score += weight * 3
        if t in bo:
            score += weight * 1.2
    if len(q) >= 3 and q in (ti + se + bo):
        score += 7
    if kind == "file" and any(w in question for w in ("어디", "위치", "양식", "서식", "파일")):
        score *= 1.8
    return round(score, 3)


def retrieve(question: str, db_path: Path, limit: int = 3) -> list[Source]:
    if not question.strip() or len(question) > 1000:
        raise ValueError("question must be between 1 and 1000 characters")
    candidates: list[Source] = []
    with closing(sqlite3.connect(db_path)) as conn:
        for row in conn.execute("SELECT file_id,title,summary,location,extension,keywords FROM files"):
            file_id, title, summary, loc, ext, keywords = row
            score = _score(question, title, keywords, summary + " " + loc, "file")
            if score >= 2:
                candidates.append(Source(file_id, "file", title, "파일 목록", summary, loc, ext, score))
        for row in conn.execute("SELECT doc_id,title,section,body FROM chunks"):
            doc_id, title, section, body = row
            score = _score(question, title, section, body, "manual")
            if score >= 2:
                candidates.append(Source(doc_id + "#" + section, "manual", title, section, body[:1100], score=score))
    return sorted(candidates, key=lambda x: (-x.score, x.source_id))[:limit]
