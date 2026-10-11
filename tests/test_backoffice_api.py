"""Backoffice API contract tests. Run with Python unittest, not pytest."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


class BackofficeApiTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test-index.db"
        self.settings = Settings(data_dir=SAMPLE, db_path=self.db_path)
        self.context = TestClient(create_app(self.settings))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_openapi_groups_and_typed_models(self):
        spec = self.client.get("/openapi.json").json()
        paths = spec["paths"]
        for endpoint in (
            "/api/v1/health", "/api/v1/query", "/api/v1/files",
            "/api/v1/files/{file_id}", "/api/v1/manuals",
            "/api/v1/manuals/{manual_id}", "/api/v1/index/status",
        ):
            with self.subTest(path=endpoint):
                self.assertIn(endpoint, paths)
        for schema in ("FilePage", "FileRecord", "ManualPage", "ManualDetail", "IndexStatus"):
            self.assertIn(schema, spec["components"]["schemas"])

    def test_query_keeps_existing_response_fields_and_top_evidence(self):
        response = self.client.post(
            "/api/v1/query", json={"question": "경조휴가 규정을 알려줘"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["mode"], "extractive")
        self.assertEqual(payload["sources"][0]["kind"], "manual")
        self.assertIn("family_events.md", payload["sources"][0]["source_id"])
        self.assertTrue(all(k in payload for k in ("answer", "sources", "mode")))

    def test_file_list_paginates_with_stable_ids(self):
        first = self.client.get("/api/v1/files", params={"limit": 2, "offset": 0}).json()
        second = self.client.get("/api/v1/files", params={"limit": 2, "offset": 2}).json()
        self.assertEqual(first["total"], 6)
        self.assertEqual(second["total"], 6)
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(len(second["items"]), 2)
        self.assertEqual(
            set(row["file_id"] for row in first["items"]) &
            set(row["file_id"] for row in second["items"]),
            set(),
        )

    def test_file_search_and_extension_filter(self):
        by_name = self.client.get("/api/v1/files", params={"q": "기안서"}).json()
        self.assertIn("doc-001", [row["file_id"] for row in by_name["items"]])
        no_files = self.client.get(
            "/api/v1/files", params={"extension": "definitely_unknown"}
        ).json()
        self.assertEqual(no_files["items"], [])
        self.assertEqual(no_files["total"], 0)
        escaped = self.client.get(
            "/api/v1/files", params={"q": "never%match_this_string"}
        ).json()
        self.assertEqual(escaped["total"], 0)

    def test_file_detail_and_404(self):
        item = self.client.get("/api/v1/files/doc-001")
        self.assertEqual(item.status_code, 200)
        self.assertIn("공유드라이브", item.json()["location"])
        self.assertEqual(item.json()["extension"], "docx")
        missing = self.client.get("/api/v1/files/nonexistent")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "file_not_found")

    def test_manual_list_detail_and_source_link(self):
        listing = self.client.get("/api/v1/manuals").json()
        self.assertGreaterEqual(listing["total"], 1)
        self.assertTrue(any(i["manual_id"] == "family_events.md" for i in listing["items"]))
        detail = self.client.get("/api/v1/manuals/family_events.md")
        self.assertEqual(detail.status_code, 200)
        data = detail.json()
        self.assertEqual(data["manual_id"], "family_events.md")
        self.assertTrue(data["sections"])
        for item in data["sections"]:
            self.assertTrue(item["source_id"].startswith("manuals/family_events.md#"))
            self.assertNotIn("SAMPLE_POLICY", item["content"])

    def test_manual_search_and_missing(self):
        filtered = self.client.get("/api/v1/manuals", params={"q": "경조휴가"}).json()
        self.assertTrue(any(i["manual_id"] == "family_events.md" for i in filtered["items"]))
        self.assertEqual(self.client.get("/api/v1/manuals/missing.md").status_code, 404)

    def test_index_status_uses_live_index_statistics(self):
        response = self.client.get("/api/v1/index/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["files"], 6)
        self.assertGreaterEqual(data["manuals"], 1)
        self.assertGreaterEqual(data["sections"], data["manuals"])
        self.assertIn("+00:00", data["indexed_at"])

    def test_invalid_pagination_fails_validation(self):
        for url, params in (
            ("/api/v1/files", {"limit": 101}),
            ("/api/v1/files", {"offset": -1}),
            ("/api/v1/manuals", {"limit": 0}),
        ):
            with self.subTest(url=url, params=params):
                self.assertEqual(self.client.get(url, params=params).status_code, 422)

    def test_no_implicit_empty_index_creation_on_missing_db(self):
        self.db_path.unlink()
        for url in ("/api/v1/files", "/api/v1/manuals", "/api/v1/index/status"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 503)
        self.assertEqual(
            self.client.post("/api/v1/query", json={"question": "경조휴가"}).status_code,
            503,
        )
        self.assertFalse(self.db_path.exists())

    def test_service_key_protects_all_catalog_endpoints(self):
        protected = (
            ("/api/v1/query", "post", {"question": "경조휴가"}),
            ("/api/v1/files", "get", None),
            ("/api/v1/files/doc-001", "get", None),
            ("/api/v1/manuals", "get", None),
            ("/api/v1/manuals/family_events.md", "get", None),
            ("/api/v1/index/status", "get", None),
        )
        production = replace(
            self.settings, app_env="production", auth_mode="service_key",
            service_api_key="secret-" + "1" * 32,
        )
        with TestClient(create_app(production)) as client:
            for url, method, payload in protected:
                with self.subTest(url=url):
                    send = getattr(client, method)
                    args = {"json": payload} if payload is not None else {}
                    self.assertEqual(send(url, **args).status_code, 401)
                    self.assertEqual(
                        send(url, headers={"X-Service-Key": production.service_api_key},
                             **args).status_code,
                        200,
                    )
            self.assertEqual(client.get("/api/v1/health").status_code, 200)

    def test_arbitrary_file_id_does_not_execute_sql(self):
        response = self.client.get("/api/v1/files/doc-001%27%20OR%20%271%27%3D%271")
        self.assertEqual(response.status_code, 404)
