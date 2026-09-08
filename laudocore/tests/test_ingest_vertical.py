"""Teste de integracao do pipeline de ingestao do vertical (Fase 1).

Requer o corpus real em data/raw/ (fora do git, ver ADR 0002) — roda
apenas localmente, onde o corpus foi colocado manualmente. Sem o
corpus, os testes sao pulados (skip), nao falham, para nao quebrar
uma checagem de CI que nao tenha acesso ao dado clinico.
"""

import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "CMS_CORPUS_2026-06-06_A_2026-09-06"
DB_PATH = ROOT / "data" / "processed" / "laudocore.db"
QA_PATH = ROOT / "data" / "derived" / "qa" / "QA_REPORT_FASE1.json"
SCRIPT = ROOT / "scripts" / "ingest_vertical.py"


def run_script() -> dict:
    subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=ROOT,
                    capture_output=True, text=True)
    return json.loads(QA_PATH.read_text(encoding="utf-8"))


@unittest.skipUnless(RAW_ROOT.exists(), "corpus RAW ausente localmente (ver ADR 0002)")
class TestIngestVertical(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = run_script()

    def test_ingests_expected_volume(self):
        # 911 e o numero confirmado na Fase 0 para RM_JOELHO_D + RM_JOELHO_E
        self.assertEqual(self.qa["totals"]["reports_ingested"], 911)

    def test_every_report_has_technique_and_findings(self):
        # technique e findings sao universais neste vertical (100% nos
        # 4 medicos, ja verificado manualmente); uma regressao aqui
        # indica quebra no parser de secao ou nos dados de entrada.
        for doctor, cov in self.qa["section_coverage_by_doctor"].items():
            self.assertEqual(cov["pct_with_technique"], 100.0, doctor)
            self.assertEqual(cov["pct_with_findings"], 100.0, doctor)

    def test_unmatched_headers_stay_low(self):
        # Nao deve crescer sem que alguem revise os novos casos.
        self.assertLessEqual(self.qa["unmatched_header_total_occurrences"], 10)

    def test_db_row_counts_consistent(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        n_reports = cur.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        n_sections = cur.execute("SELECT COUNT(*) FROM report_sections").fetchone()[0]
        n_sentences = cur.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        conn.close()
        self.assertEqual(n_reports, self.qa["totals"]["reports_ingested"])
        self.assertGreater(n_sections, n_reports)  # varias secoes por laudo
        self.assertEqual(n_sentences, self.qa["totals"]["sentences_extracted"])

    def test_idempotent_across_runs(self):
        first = self.qa
        second = run_script()

        def strip_volatile(d):
            d = dict(d)
            d.pop("generated_at", None)
            return d

        self.assertEqual(strip_volatile(first), strip_volatile(second))

    def test_no_report_text_lost_between_raw_and_sections(self):
        # Amostragem: para cada laudo, a soma de caracteres das secoes
        # nao pode ser drasticamente menor que o texto raw (ninguem foi
        # descartado silenciosamente). Tolerancia para cabecalhos removidos.
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT id, report_text_clean FROM reports ORDER BY id LIMIT 50"
        ).fetchall()
        for report_id, text_clean in rows:
            sections_len = cur.execute(
                "SELECT COALESCE(SUM(LENGTH(text_clean)), 0) FROM report_sections WHERE report_id = ?",
                (report_id,),
            ).fetchone()[0]
            self.assertGreaterEqual(
                sections_len, 0.7 * len(text_clean),
                f"report_id={report_id}: possivel perda de conteudo no parsing de secoes",
            )
        conn.close()


if __name__ == "__main__":
    unittest.main()
