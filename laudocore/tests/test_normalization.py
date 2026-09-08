import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.normalization.text_normalization import (
    clean, normalized, exact_hash, normalized_hash,
)


class TestClean(unittest.TestCase):
    def test_preserves_clinical_content(self):
        raw = "Menisco medial​ com sinal normal.  \nLigamentos íntegros.\n\n\n\nSem derrame."
        result = clean(raw)
        self.assertIn("Menisco medial com sinal normal.", result)
        self.assertIn("Ligamentos íntegros.", result)
        self.assertIn("Sem derrame.", result)

    def test_removes_zero_width_space(self):
        self.assertNotIn("​", clean("teste​teste"))

    def test_strips_trailing_whitespace_per_line(self):
        result = clean("linha um   \nlinha dois\t\t\n")
        self.assertNotIn(" \n", result)
        self.assertNotIn("\t\n", result)

    def test_collapses_excessive_blank_lines(self):
        result = clean("a\n\n\n\n\n\nb")
        self.assertEqual(result, "a\n\nb")

    def test_is_idempotent(self):
        raw = "Achado A.\nAchado B.  \n\n\n\nAchado C."
        once = clean(raw)
        twice = clean(once)
        self.assertEqual(once, twice)


class TestNormalized(unittest.TestCase):
    def test_casefolds_and_collapses_whitespace(self):
        self.assertEqual(
            normalized("Pequeno   Derrame\nArticular"),
            "pequeno derrame articular",
        )

    def test_never_used_as_final_report_is_documented(self):
        # Regressao de contrato: normalized() nao pode ser usada como
        # texto de exibicao — deve ser sempre minuscula.
        self.assertEqual(normalized("ABC"), "abc")


class TestHashes(unittest.TestCase):
    def test_exact_hash_is_stable(self):
        text = "Menisco preservado."
        self.assertEqual(exact_hash(text), exact_hash(text))

    def test_exact_hash_differs_on_any_change(self):
        self.assertNotEqual(exact_hash("Pequeno derrame."), exact_hash("Discreto derrame."))

    def test_normalized_hash_collapses_case_and_spacing_variants(self):
        a = normalized_hash(normalized("Pequeno  derrame articular."))
        b = normalized_hash(normalized("pequeno derrame articular."))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
