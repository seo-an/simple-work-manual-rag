"""API runtime config; unsafe bypasses are rejected outside sample development."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    data_mode: str = "sample"
    auth_mode: str = "dev"
    data_dir: Path = Path("data/sample")
    db_path: Path = Path("runtime/manuals.db")
    service_api_key: str = ""
    llm_mode: str = "extractive"
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            data_mode=os.getenv("DATA_MODE", "sample"),
            auth_mode=os.getenv("AUTH_MODE", "dev"),
            data_dir=Path(os.getenv("DATA_DIR", "data/sample")),
            db_path=Path(os.getenv("DB_PATH", "runtime/manuals.db")),
            service_api_key=os.getenv("SERVICE_API_KEY", ""),
            llm_mode=os.getenv("LLM_MODE", "extractive"),
            llm_api_base=os.getenv("LLM_API_BASE", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
        )

    def validate(self) -> None:
        if self.auth_mode == "dev":
            if self.app_env != "development" or self.data_mode != "sample":
                raise ValueError("dev authentication is only permitted in development/sample")
        elif self.auth_mode == "service_key":
            if len(self.service_api_key) < 24:
                raise ValueError("SERVICE_API_KEY must contain at least 24 characters")
        else:
            raise ValueError("unsupported AUTH_MODE")
        if self.llm_mode not in {"extractive", "openai_compatible"}:
            raise ValueError("unsupported LLM_MODE")
        if self.llm_mode == "openai_compatible" and not all(
            (self.llm_api_base.startswith("https://"), self.llm_api_key, self.llm_model)
        ):
            raise ValueError("HTTPS LLM_API_BASE, LLM_API_KEY and LLM_MODEL are required")
