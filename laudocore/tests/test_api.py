"""Testes da API (FastAPI TestClient) contra um banco SQLite temporario
semeado com dados FABRICADOS (mesma razao das outras suites: nao
commitar/usar texto real de laudo em teste)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backend.api.db as api_db  # noqa: E402
from backend.db.schema import rebuild_schema, rebuild_concepts_schema, ensure_review_queue_schema  # noqa: E402


def _seed(conn):
    conn.execute(
        """INSERT INTO reports (
            id, record_id, patient_id, age_at_exam, sex, exam_datetime,
            modality, domain, anatomy, laterality, exam_type,
            study_description_raw, doctor, report_text_raw,
            report_text_clean, report_text_normalized, exact_hash,
            normalized_hash, source, import_batch, created_at
        ) VALUES (1,1,'0',40,'F','01/01/2026 00:00','RM','MSK','JOELHO','D',
                  'RM_JOELHO_D','Joelho^Direito','NEY','raw laudo texto completo.',
                  'raw','raw','h1','nh1','test','batch','2026-01-01T00:00:00Z')"""
    )
    conn.execute(
        """INSERT INTO report_sections (id, report_id, section_type, section_order,
            text_raw, text_clean, header_line, unmatched_header)
            VALUES (1,1,'technique',0,'Sequências FSE.','Sequências FSE.','TÉCNICA:',0)"""
    )
    conn.execute(
        """INSERT INTO report_sections (id, report_id, section_type, section_order,
            text_raw, text_clean, header_line, unmatched_header)
            VALUES (2,1,'findings',1,
                    'Menisco lateral sem evidências de lesões.',
                    'Menisco lateral sem evidências de lesões.','RELATÓRIO:',0)"""
    )
    conn.execute(
        """INSERT INTO report_sections (id, report_id, section_type, section_order,
            text_raw, text_clean, header_line, unmatched_header)
            VALUES (3,1,'other',2,'ACHADO ADICIONAL: nota residual.',
                    'ACHADO ADICIONAL: nota residual.','ACHADO ADICIONAL:',1)"""
    )
    conn.execute(
        """INSERT INTO sentences (id, report_id, section_id, sentence_order,
            text_raw, text_normalized, doctor, exam_type, exact_hash, normalized_hash)
            VALUES (1,1,2,0,'Menisco lateral sem evidências de lesões.',
                    'menisco lateral sem evidências de lesões.','NEY','RM_JOELHO_D','h','nh')"""
    )
    conn.execute(
        """INSERT INTO sentences (id, report_id, section_id, sentence_order,
            text_raw, text_normalized, doctor, exam_type, exact_hash, normalized_hash)
            VALUES (2,1,3,0,'nota residual.','nota residual.','NEY','RM_JOELHO_D','h2','nh2')"""
    )
    conn.execute(
        """INSERT INTO clinical_concepts (
            report_id, sentence_id, section_type, organ, structure, finding,
            status, severity, location, measurement_cm, certainty, rule_id,
            doctor, exam_type
        ) VALUES (1,1,'findings','knee','meniscus_lateral','tear','absent',
                  NULL,NULL,NULL,'definitive','meniscus_explicit_normal','NEY','RM_JOELHO_D')"""
    )
    conn.execute(
        """INSERT INTO clinical_review_queue (
            report_id, sentence_id, section_type, doctor, exam_type,
            original_text, system_output_json, rule_id, reason, risk_level,
            status, created_at
        ) VALUES (1,2,'other','NEY','RM_JOELHO_D','ACHADO ADICIONAL: nota residual.',
                  '[]',NULL,'unmatched_header','medium','pending','2026-01-01T00:00:00Z')"""
    )
    conn.commit()


class ApiTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmpdir.name) / "test.db"
        cls._original_db_path = api_db.DB_PATH
        api_db.DB_PATH = cls.db_path

        import sqlite3
        conn = sqlite3.connect(cls.db_path)
        rebuild_schema(conn)
        rebuild_concepts_schema(conn)
        ensure_review_queue_schema(conn)
        _seed(conn)
        conn.close()

        from backend.api.app import app
        from fastapi.testclient import TestClient
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        api_db.DB_PATH = cls._original_db_path
        cls.tmpdir.cleanup()


class TestHealth(ApiTestBase):
    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)


class TestReportsEndpoints(ApiTestBase):
    def test_list_reports(self):
        r = self.client.get("/api/reports")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["doctor"], "NEY")

    def test_filter_by_doctor(self):
        r = self.client.get("/api/reports", params={"doctor": "RAFAEL"})
        self.assertEqual(r.json(), [])

    def test_report_detail_includes_sections_and_concepts(self):
        r = self.client.get("/api/reports/1")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["sections"]), 3)
        findings_section = next(s for s in data["sections"] if s["section_type"] == "findings")
        self.assertEqual(len(findings_section["sentences"]), 1)
        concept = findings_section["sentences"][0]["concepts"][0]
        self.assertEqual(concept["structure"], "meniscus_lateral")
        self.assertEqual(concept["structure_label"], "Menisco lateral")

    def test_report_not_found(self):
        r = self.client.get("/api/reports/999")
        self.assertEqual(r.status_code, 404)


class TestTaxonomyAndPhrases(ApiTestBase):
    def test_taxonomy_lists_seeded_combination(self):
        r = self.client.get("/api/taxonomy")
        self.assertEqual(r.status_code, 200)
        combos = {(o["structure"], o["finding"], o["status"]) for o in r.json()}
        self.assertIn(("meniscus_lateral", "tear", "absent"), combos)

    def test_phrases_search_by_structure(self):
        r = self.client.get("/api/phrases", params={"structure": "meniscus_lateral"})
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertIn("Menisco lateral", data[0]["example_text"])

    def test_phrases_search_by_text(self):
        r = self.client.get("/api/phrases", params={"search": "evidências"})
        self.assertEqual(len(r.json()), 1)
        r_empty = self.client.get("/api/phrases", params={"search": "termo_inexistente_xyz"})
        self.assertEqual(r_empty.json(), [])


class TestCompileEndpoint(ApiTestBase):
    def test_compile_resolves_known_finding(self):
        body = {
            "findings": [{"structure": "meniscus_lateral", "finding": "tear", "status": "absent"}],
            "doctor": "NEY",
        }
        r = self.client.post("/api/compile", json=body)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["findings_lines"]), 1)
        self.assertIn("RELATÓRIO", data["rendered_text"])
        self.assertEqual(data["unresolved"], [])

    def test_compile_flags_unresolved_finding(self):
        body = {"findings": [{"structure": "acl", "finding": "tear", "status": "present"}]}
        r = self.client.post("/api/compile", json=body)
        data = r.json()
        self.assertEqual(len(data["unresolved"]), 1)
        self.assertEqual(data["findings_lines"], [])

    def test_compile_flags_duplicate_warning(self):
        f = {"structure": "meniscus_lateral", "finding": "tear", "status": "absent"}
        body = {"findings": [f, f]}
        r = self.client.post("/api/compile", json=body)
        data = r.json()
        self.assertTrue(any("DUPLICIDADE" in w for w in data["warnings"]))


class TestReviewQueueEndpoints(ApiTestBase):
    def test_list_pending(self):
        r = self.client.get("/api/review-queue", params={"status": "pending"})
        data = r.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["reason"], "unmatched_header")
        self.assertEqual(json.loads(json.dumps(data[0]["system_output"])), [])

    def test_resolve_item(self):
        item = self.client.get("/api/review-queue").json()[0]
        r = self.client.post(
            f"/api/review-queue/{item['id']}/resolve", json={"reviewer_note": "revisado em teste"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "resolved")
        self.assertEqual(r.json()["reviewer_note"], "revisado em teste")
        # reabre para nao deixar efeito colateral entre testes desta classe
        self.client.post(f"/api/review-queue/{item['id']}/reopen")

    def test_resolve_nonexistent_item_returns_404(self):
        r = self.client.post("/api/review-queue/999999/resolve", json={})
        self.assertEqual(r.status_code, 404)


class TestStatsEndpoint(ApiTestBase):
    def test_stats(self):
        r = self.client.get("/api/stats")
        data = r.json()
        self.assertEqual(data["reports_total"], 1)
        self.assertEqual(data["concepts_total"], 1)
        self.assertEqual(data["review_queue_pending"], 1)
        self.assertIn("NEY", data["doctors"])


if __name__ == "__main__":
    unittest.main()
