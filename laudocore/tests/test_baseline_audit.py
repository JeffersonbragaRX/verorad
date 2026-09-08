"""Testes da Fase 0 (baseline do corpus).

Sem dependencias externas (unittest da stdlib) porque nesta fase o
projeto ainda nao tem ambiente Python fixado. Cobre exatamente o
criterio de aceite da Fase 0: 100% das linhas lidas ou justificadas
como invalidas, e contagens reprodutiveis entre execucoes.
"""

import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "data" / "derived" / "qa"
SCRIPT = ROOT / "scripts" / "baseline_audit.py"


def run_script() -> dict:
    subprocess.run([sys.executable, str(SCRIPT)], check=True, cwd=ROOT,
                    capture_output=True, text=True)
    return json.loads((QA_DIR / "QA_REPORT.json").read_text(encoding="utf-8"))


class TestBaselineAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = run_script()

    def test_every_line_accounted_for(self):
        t = self.qa["totals"]
        self.assertEqual(
            t["total_lines_read"], t["valid_records"] + t["invalid_records"],
            "Toda linha lida deve ser valida ou invalida com motivo registrado.",
        )

    def test_no_invalid_records_in_current_export(self):
        # Este export especifico ja chega auditado pelo CMS de origem;
        # se isso mudar em um proximo lote, este teste deve falhar e
        # alertar para investigar, nao ser silenciado.
        self.assertEqual(self.qa["totals"]["invalid_records"], 0)

    def test_cross_check_matches_source_export(self):
        cc = self.qa["cross_check_vs_source_export_stats"]
        self.assertTrue(cc["match_manifest_records"])
        self.assertTrue(cc["match_unique_patients"])
        self.assertTrue(cc["match_by_modality"])
        self.assertTrue(cc["match_laterality_null"])

    def test_exam_types_csv_sums_to_valid_records(self):
        total = 0
        with (QA_DIR / "exam_types.csv").open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                total += int(row["count"])
        self.assertEqual(total, self.qa["totals"]["valid_records"])

    def test_physicians_csv_sums_to_valid_records(self):
        total = 0
        with (QA_DIR / "physicians.csv").open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                total += int(row["total"])
        self.assertEqual(total, self.qa["totals"]["valid_records"])

    def test_reproducibility_across_runs(self):
        first = self.qa
        second = run_script()

        def strip_volatile(d: dict) -> dict:
            d = dict(d)
            d.pop("generated_at", None)
            return d

        self.assertEqual(strip_volatile(first), strip_volatile(second),
                          "Duas execucoes do baseline devem produzir as mesmas contagens.")


if __name__ == "__main__":
    unittest.main()
