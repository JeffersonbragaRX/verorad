"""Integridade referencial das tabelas derivadas.

Regressao de um bug real encontrado pela auditoria da propria entrega
(ADR 0011): `reports` e `sentences` usam id autoincremental, e uma
reingestao os reatribui. As tabelas derivadas sobreviviam ao
rebuild_schema() e passavam a apontar para as linhas ERRADAS — depois
da ingestao global, 12.946 dos 15.222 conceitos do vertical de joelho
referenciavam exames que nao eram de joelho, em silencio.

Nenhum teste pegou isso porque todos rodavam sobre um banco que eles
mesmos acabavam de reconstruir.
"""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db.paths import db_path  # noqa: E402

DB_PATH = db_path()


@unittest.skipUnless(DB_PATH.exists(), "banco local ausente (ver ADR 0002)")
class TestDerivedTableIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(DB_PATH)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _table_exists(self, name: str) -> bool:
        return bool(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone())

    def test_universal_concepts_have_no_orphan_reports(self):
        if not self._table_exists("clinical_concepts_universal"):
            self.skipTest("camada universal ainda nao gerada")
        orphans = self.conn.execute("""
            SELECT COUNT(*) FROM clinical_concepts_universal cu
            LEFT JOIN reports r ON cu.report_id = r.id WHERE r.id IS NULL
        """).fetchone()[0]
        self.assertEqual(orphans, 0)

    def test_universal_concept_exam_type_matches_its_report(self):
        """O conceito guarda exam_type denormalizado. Se ele divergir do
        laudo que referencia, o id foi reatribuido por baixo."""
        if not self._table_exists("clinical_concepts_universal"):
            self.skipTest("camada universal ainda nao gerada")
        mismatched = self.conn.execute("""
            SELECT COUNT(*) FROM clinical_concepts_universal cu
            JOIN reports r ON cu.report_id = r.id
            WHERE cu.exam_type <> r.exam_type
        """).fetchone()[0]
        self.assertEqual(mismatched, 0, "conceito aponta para laudo de outro exame")

    def test_legacy_knee_concepts_only_reference_knee_reports(self):
        """O extrator legado so roda no vertical de joelho. Qualquer
        conceito dele apontando para outro exame significa que a tabela
        sobreviveu a uma reingestao — exatamente o bug corrigido."""
        if not self._table_exists("clinical_concepts"):
            self.skipTest("tabela legada ausente")
        n = self.conn.execute("SELECT COUNT(*) FROM clinical_concepts").fetchone()[0]
        if n == 0:
            self.skipTest("extracao do vertical nao executada neste banco")
        wrong = self.conn.execute("""
            SELECT COUNT(*) FROM clinical_concepts cc
            JOIN reports r ON cc.report_id = r.id
            WHERE r.exam_type NOT IN ('RM_JOELHO_D', 'RM_JOELHO_E')
        """).fetchone()[0]
        self.assertEqual(wrong, 0)

    def test_review_queue_anchors_match_their_sentence(self):
        """A fila guarda julgamento humano e nao pode cair no rebuild —
        entao precisa se reancorar pelo texto (repair_stale_references)."""
        if not self._table_exists("clinical_review_queue"):
            self.skipTest("fila ausente")
        broken = self.conn.execute("""
            SELECT COUNT(*) FROM clinical_review_queue rq
            JOIN sentences s ON rq.sentence_id = s.id
            WHERE rq.original_text <> s.text_raw
              AND rq.status <> 'stale_reference'
        """).fetchone()[0]
        self.assertEqual(broken, 0, "item da fila aponta para outra sentenca")


if __name__ == "__main__":
    unittest.main()
