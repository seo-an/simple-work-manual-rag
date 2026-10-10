"""Regression tests for user intent vs source type.

These tests reproduce a real Swagger UI failure: asking for a leave policy
returned the location of the request form instead of the policy itself.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient
from app.config import Settings
from app.ingest import build_index
from app.main import create_app
from app.search import query_intent, retrieve

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


class IntentRankingTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "index.db"
        build_index(SAMPLE, self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_intent_rules(self):
        cases = {
            "경조휴가 규정을 알려줘": "manual",
            "출장 승인 절차는?": "manual",
            "기안서 양식 어디 있어?": "file",
            "출장신청서 파일 위치": "file",
            "경조휴가 신청서": "file",
            "냉장고": None,
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(query_intent(question), expected)

    def test_policy_question_selects_manual_as_first_evidence(self):
        hits = retrieve("경조휴가 규정을 알려줘", self.db_path)
        self.assertTrue(hits)
        self.assertEqual(hits[0].kind, "manual")
        self.assertIn("family_events.md", hits[0].source_id)

    def test_travel_procedure_selects_manual(self):
        hits = retrieve("출장 승인 절차는?", self.db_path)
        self.assertEqual(hits[0].kind, "manual")
        self.assertIn("travel.md", hits[0].source_id)

    def test_file_location_question_selects_excel(self):
        hits = retrieve("기안서 양식 어디 있어?", self.db_path)
        self.assertEqual(hits[0].kind, "file")
        self.assertEqual(hits[0].source_id, "doc-001")

    def test_metadata_is_not_answer_evidence(self):
        hits = retrieve("경조휴가 규정을 알려줘", self.db_path)
        self.assertTrue(all("SAMPLE_POLICY" not in h.excerpt for h in hits))

    def test_unrelated_question_still_abstains(self):
        self.assertEqual(retrieve("양자 컴퓨터 대여 절차", self.db_path), [])

    def test_http_answer_matches_policy_intent(self):
        cfg = Settings(data_dir=SAMPLE, db_path=self.db_path)
        with TestClient(create_app(cfg)) as client:
            response = client.post(
                "/api/v1/query", json={"question": "경조휴가 규정을 알려줘"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "answered")
        self.assertEqual(body["sources"][0]["kind"], "manual")
        self.assertNotIn("등록된 파일 목록 기준", body["answer"])


if __name__ == "__main__":
    import unittest
    unittest.main()
