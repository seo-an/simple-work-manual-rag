"""Read-only SQLite catalog used by the backoffice-facing HTTP API.

Excel and Markdown remain the sources of truth. This module never edits them.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


# Internal sample metadata must not appear as a manual section.
VISIBLE_SECTION = "LTRIM(body) NOT LIKE '> SAMPLE_POLICY:%'"


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open the published index read-only; never silently create an empty DB."""
    if not db_path.is_file():
        raise sqlite3.OperationalError("search index unavailable")
    return sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)


def _like(value: str) -> str:
    """Escape LIKE wildcards so literal user input cannot broaden a query."""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_files(
    db_path: Path, *, q: str | None = None, extension: str | None = None,
    limit: int = 20, offset: int = 0,
) -> dict:
    predicates = []
    values: list[object] = []
    if q:
        predicates.append(
            "(title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\' "
            "OR keywords LIKE ? ESCAPE '\\' OR location LIKE ? ESCAPE '\\')"
        )
        values.extend([_like(q)] * 4)
    if extension:
        predicates.append("LOWER(extension) = LOWER(?)")
        values.append(extension.lstrip("."))
    where = " WHERE " + " AND ".join(predicates) if predicates else ""
    columns = "file_id,title,summary,location,extension,keywords"

    with closing(open_index(db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM files" + where, values).fetchone()[0]
        rows = conn.execute(
            f"SELECT {columns} FROM files{where} "
            "ORDER BY title COLLATE NOCASE, file_id LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
    return {
        "items": [dict(zip(columns.split(","), row)) for row in rows],
        "total": total, "limit": limit, "offset": offset,
    }


def get_file(db_path: Path, file_id: str) -> dict | None:
    columns = "file_id,title,summary,location,extension,keywords"
    with closing(open_index(db_path)) as conn:
        row = conn.execute(
            f"SELECT {columns} FROM files WHERE file_id = ?", (file_id,),
        ).fetchone()
    return dict(zip(columns.split(","), row)) if row else None


def list_manuals(
    db_path: Path, *, q: str | None = None, limit: int = 20, offset: int = 0,
) -> dict:
    # Group by stable relative Markdown path; never use SQLite row IDs as public IDs.
    base = f"""
        WITH visible AS (
            SELECT doc_id,title,section,body FROM chunks WHERE {VISIBLE_SECTION}
        ),
        docs AS (
            SELECT doc_id, MAX(title) AS title, COUNT(*) AS section_count
            FROM visible GROUP BY doc_id
        )
        SELECT docs.doc_id, docs.title, docs.section_count
        FROM docs
    """
    params: list[object] = []
    if q:
        base += (
            " WHERE (docs.title LIKE ? ESCAPE '\\' OR EXISTS ("
            "SELECT 1 FROM visible s WHERE s.doc_id = docs.doc_id "
            "AND (s.section LIKE ? ESCAPE '\\' OR s.body LIKE ? ESCAPE '\\')))"
        )
        params = [_like(q)] * 3
    with closing(open_index(db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM (" + base + ") AS matches", params).fetchone()[0]
        rows = conn.execute(
            base + " ORDER BY docs.title COLLATE NOCASE, docs.doc_id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {
        "items": [
            {"manual_id": doc_id.removeprefix("manuals/"), "title": title,
             "section_count": count}
            for doc_id, title, count in rows
        ],
        "total": total, "limit": limit, "offset": offset,
    }


def get_manual(db_path: Path, manual_id: str) -> dict | None:
    if not manual_id or manual_id.startswith("/") or ".." in Path(manual_id).parts:
        return None
    doc_id = "manuals/" + manual_id
    with closing(open_index(db_path)) as conn:
        rows = conn.execute(
            f"SELECT title, section, body FROM chunks WHERE doc_id = ? "
            f"AND {VISIBLE_SECTION} ORDER BY id",
            (doc_id,),
        ).fetchall()
    if not rows:
        return None
    return {
        "manual_id": manual_id,
        "title": rows[0][0],
        "sections": [
            {"heading": section, "content": body, "source_id": f"{doc_id}#{section}"}
            for _, section, body in rows
        ],
    }


def index_status(db_path: Path) -> dict:
    with closing(open_index(db_path)) as conn:
        files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        manuals, sections = conn.execute(
            f"SELECT COUNT(DISTINCT doc_id), COUNT(*) FROM chunks "
            f"WHERE {VISIBLE_SECTION}"
        ).fetchone()
    return {
        "status": "ready",
        "files": files, "manuals": manuals, "sections": sections,
        "indexed_at": datetime.fromtimestamp(
            db_path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }
