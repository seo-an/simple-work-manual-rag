from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import shutil

from fastapi.testclient import TestClient
from app.config import Settings
from app.ingest import build_index, read_registry
from app.search import retrieve
from app.main import create_app
from scripts.evaluate import evaluate

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class RetrievalTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Path(self.tmp.name) / "rag.db"
        build_index(SAMPLE, self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_excel_file_lookup(self):
        hits = retrieve("기안서 양식 어디 있나요?", self.db)
        self.assertEqual(hits[0].source_id, "doc-001")
        self.assertIn("공유드라이브", hits[0].location)
        self.assertEqual(hits[0].extension, "docx")

    def test_policy_retrieval(self):
        self.assertTrue(any("family_events.md" in h.source_id
                            for h in retrieve("경조휴가 규정을 알려줘", self.db)))

    def test_procedure_retrieval(self):
        self.assertTrue(any("travel.md" in h.source_id
                            for h in retrieve("출장 승인 절차는?", self.db)))

    def test_no_evidence(self):
        self.assertEqual(retrieve("양자 컴퓨터 대여 절차", self.db), [])

    def test_workbook_import(self):
        self.assertEqual(len(read_registry(SAMPLE / "file_registry.xlsx")), 6)

    def test_data_update_without_code_change(self):
        copy = Path(self.tmp.name) / "replacement"
        shutil.copytree(SAMPLE, copy)
        (copy / "manuals" / "break_room.md").write_text(
            "# 가상 규정\n## 실험실 출입\n남색 안전모를 착용해 주세요.\n", encoding="utf-8"
        )
        build_index(copy, self.db)
        self.assertTrue(any("break_room.md" in h.source_id
                            for h in retrieve("남색 안전모", self.db)))

    def test_atomic_index_on_bad_input(self):
        copy = Path(self.tmp.name) / "bad"
        shutil.copytree(SAMPLE, copy)
        (copy / "file_registry.xlsx").unlink()
        with self.assertRaises(FileNotFoundError):
            build_index(copy, self.db)
        self.assertTrue(retrieve("기안서 양식", self.db))

    def test_offline_evaluation(self):
        result = evaluate(self.db)
        self.assertEqual(result["total"], result["passed"], result)


class ApiTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        cfg = Settings(data_dir=SAMPLE, db_path=Path(self.tmp.name) / "idx.db")
        self.client_ctx = TestClient(create_app(cfg))
        self.client = self.client_ctx.__enter__()
        self.cfg = cfg

    def tearDown(self):
        self.client_ctx.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_health(self):
        self.assertEqual(self.client.get("/api/v1/health").json()["status"], "ok")

    def test_query_sources(self):
        response = self.client.post("/api/v1/query", json={"question": "기안서 어디 있나요?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "answered")
        self.assertTrue(response.json()["sources"])

    def test_abstain(self):
        response = self.client.post("/api/v1/query", json={"question": "양자 컴퓨터 대여 절차"})
        self.assertEqual(response.json()["status"], "insufficient_evidence")

    def test_empty_question(self):
        self.assertEqual(
            self.client.post("/api/v1/query", json={"question": ""}).status_code, 422
        )

    def test_dev_auth_never_allowed_in_production(self):
        with self.assertRaises(ValueError):
            create_app(replace(self.cfg, app_env="production"))

    def test_service_key_rejects_missing_or_bad(self):
        cfg = replace(self.cfg, app_env="production", auth_mode="service_key",
                      service_api_key="a" * 32)
        with TestClient(create_app(cfg)) as client:
            self.assertEqual(client.post("/api/v1/query", json={"question": "출장"}).status_code, 401)
            self.assertEqual(client.post("/api/v1/query", json={"question": "출장"},
                                         headers={"X-Service-Key": "bad"}).status_code, 401)
            self.assertEqual(client.post("/api/v1/query", json={"question": "출장"},
                                         headers={"X-Service-Key": "a" * 32}).status_code, 200)

    def test_short_service_key_denied(self):
        with self.assertRaises(ValueError):
            create_app(replace(self.cfg, auth_mode="service_key", service_api_key="123"))
