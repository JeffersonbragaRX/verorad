"""Teste de integracao da fila de revisao clinica (persistencia entre
execucoes). Requer o corpus real (ver ADR 0002) — pulado se ausente.
"""

import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "CMS_CORPUS_2026-06-06_A_2026-09-06"
DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
SCRIPT = ROOT / "scripts" / "extract_concepts.py"


def run_extraction():
    subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=ROOT, capture_output=True, text=True)


@unittest.skipUnless(RAW_ROOT.exists(), "corpus RAW ausente localmente (ver ADR 0002)")
class TestReviewQueuePersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run_extraction()

    def test_rerun_does_not_duplicate_items(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        before = cur.execute("SELECT COUNT(*) FROM clinical_review_queue").fetchone()[0]
        conn.close()

        run_extraction()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        after = cur.execute("SELECT COUNT(*) FROM clinical_review_queue").fetchone()[0]
        # cada (sentence_id, reason) e UNIQUE — duplicidade violaria a constraint
        dup_check = cur.execute(
            "SELECT sentence_id, reason, COUNT(*) c FROM clinical_review_queue "
            "GROUP BY sentence_id, reason HAVING c > 1"
        ).fetchall()
        conn.close()
        self.assertEqual(before, after)
        self.assertEqual(dup_check, [])

    def test_human_resolution_survives_rerun(self):
        # Restaura o item ao estado original ao final — este teste NAO
        # deve consumir permanentemente itens reais da fila a cada execucao.
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id FROM clinical_review_queue WHERE status = 'pending' LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row, "fila de revisao vazia — nao ha item para testar persistencia")
        item_id = row[0]
        cur.execute(
            "UPDATE clinical_review_queue SET status='resolved', reviewer_note='teste_persistencia' "
            "WHERE id=?", (item_id,),
        )
        conn.commit()
        conn.close()
        self.addCleanup(self._reset_item, item_id)

        run_extraction()

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        status, note = cur.execute(
            "SELECT status, reviewer_note FROM clinical_review_queue WHERE id=?", (item_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(status, "resolved")
        self.assertEqual(note, "teste_persistencia")

    @staticmethod
    def _reset_item(item_id: int) -> None:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE clinical_review_queue SET status='pending', reviewer_note=NULL, resolved_at=NULL "
            "WHERE id=?", (item_id,),
        )
        conn.commit()
        conn.close()

    def test_all_items_have_required_fields(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT original_text, reason, risk_level FROM clinical_review_queue"
        ).fetchall()
        conn.close()
        self.assertTrue(rows, "fila de revisao vazia")
        for original_text, reason, risk_level in rows:
            self.assertTrue(original_text.strip())
            self.assertIn(risk_level, {"low", "medium", "high"})
            self.assertTrue(reason)


if __name__ == "__main__":
    unittest.main()
