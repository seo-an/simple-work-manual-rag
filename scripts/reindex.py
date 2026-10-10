"""Rebuild index explicitly after replacing sample data or mounting private data."""
from __future__ import annotations
import json
from app.config import Settings
from app.ingest import build_index


def main() -> None:
    cfg = Settings.from_env()
    cfg.validate()
    print(json.dumps(build_index(cfg.data_dir, cfg.db_path), ensure_ascii=False))


if __name__ == "__main__":
    main()
