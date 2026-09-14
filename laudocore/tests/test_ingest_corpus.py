"""Teste de integracao do pipeline de ingestao do vertical (Fase 1).

Requer o corpus real em data/raw/ (fora do git, ver ADR 0002) — roda
apenas localmente, onde o corpus foi colocado manualmente. Sem o
corpus, os testes sao pulados (skip), nao falham, para nao quebrar
uma checagem de CI que nao tenha acesso ao dado clinico.
"""

import json
import sqlite3
import os
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "raw" / "CMS_CORPUS_2026-06-06_A_2026-09-06"
PROD_QA = ROOT / "data" / "derived" / "qa" / "QA_REPORT_FASE1.json"
SCRIPT = ROOT / "scripts" / "ingest_corpus.py"
# Banco TEMPORARIO, nunca o de producao. Bug real corrigido: estes
# testes rodavam os scripts por subprocess contra data/processed/
# laudocore.db, reconstruindo o schema e apagando a ingestao global
# (8.402 laudos viravam os 911 do vertical), alem de deixar
# clinical_concepts_universal orfao. Ver ADR 0011.
_TMP_DB = tempfile.mkdtemp(prefix="laudocore_test_")


DB_PATH = Path(_TMP_DB) / "laudocore.db"
QA_PATH = Path(_TMP_DB) / "derived" / "qa" / "QA_REPORT_FASE1.json"


def _env_with_temp_db() -> dict:
    env = dict(os.environ)
    env["LAUDOCORE_DB"] = str(DB_PATH)
    return env



def run_script() -> dict:
    subprocess.run([sys.executable, str(SCRIPT), "--exam-type",
                     "RM_JOELHO_D", "RM_JOELHO_E"],
                    check=True, cwd=ROOT, env=_env_with_temp_db(),
                    capture_output=True, text=True)
    return json.loads(QA_PATH.read_text(encoding="utf-8"))


@unittest.skipUnless(RAW_ROOT.exists(), "corpus RAW ausente localmente (ver ADR 0002)")
class TestIngestCorpusVerticalSubset(unittest.TestCase):
    """Roda o pipeline global restrito ao vertical, em banco temporario."""

    @classmethod
    def setUpClass(cls):
        cls.qa = run_script()

    def test_ingests_expected_volume(self):
        # 911 e o numero confirmado na Fase 0 para RM_JOELHO_D + RM_JOELHO_E
        self.assertEqual(self.qa["totals"]["reports"], 911)

    def test_does_not_touch_production_database(self):
        """Regressao do bug que este arquivo causava: rodar a suite
        reconstruia o banco de PRODUCAO com os 911 do vertical,
        destruindo a ingestao global de 8.402 laudos."""
        self.assertNotEqual(DB_PATH.resolve(),
                            (ROOT / "data" / "processed" / "laudocore.db").resolve())
        if PROD_QA.exists():
            prod = json.loads(PROD_QA.read_text(encoding="utf-8"))
            self.assertNotEqual(prod["totals"]["reports"], 911,
                                 "QA de producao foi sobrescrito pelo teste")

    def test_every_report_has_technique_and_findings(self):
        # technique e findings sao universais neste vertical (100% nos
        # 4 medicos, ja verificado manualmente); uma regressao aqui
        # indica quebra no parser de secao ou nos dados de entrada.
        for doctor, cov in self.qa["coverage_by_doctor"].items():
            self.assertEqual(cov["pct_with_technique"], 100.0, doctor)
            self.assertEqual(cov["pct_with_findings"], 100.0, doctor)

    def test_unmatched_headers_stay_low(self):
        # Nao deve crescer sem que alguem revise os novos casos.
        rx = self.qa["parser_quality"]["reports_with_unmatched_header_by_modality"]
        for modality, stats in rx.items():
            self.assertLessEqual(stats["pct"], 10.0, modality)

    def test_db_row_counts_consistent(self):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        n_reports = cur.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        n_sections = cur.execute("SELECT COUNT(*) FROM report_sections").fetchone()[0]
        n_sentences = cur.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        conn.close()
        self.assertEqual(n_reports, self.qa["totals"]["reports"])
        self.assertGreater(n_sections, n_reports)  # varias secoes por laudo
        self.assertEqual(n_sentences, self.qa["totals"]["sentences"])

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
