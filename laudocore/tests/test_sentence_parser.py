import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.parsers.sentence_parser import split_sentences


class TestSentenceParser(unittest.TestCase):
    def test_one_sentence_per_line_when_already_isolated(self):
        text = "Meniscos preservados.\nLigamentos íntegros.\nSem derrame articular."
        self.assertEqual(split_sentences(text), [
            "Meniscos preservados.",
            "Ligamentos íntegros.",
            "Sem derrame articular.",
        ])

    def test_splits_multiple_sentences_in_one_line(self):
        text = "Menisco medial preservado. Ligamento cruzado anterior íntegro."
        self.assertEqual(split_sentences(text), [
            "Menisco medial preservado.",
            "Ligamento cruzado anterior íntegro.",
        ])

    def test_does_not_split_on_field_strength_abbreviation(self):
        text = "Exame realizado em aparelho 3T com sequências em T1 e T2."
        result = split_sentences(text)
        self.assertEqual(len(result), 1)
        self.assertIn("3T", result[0])

    def test_does_not_split_on_decimal_comma(self):
        text = "Cisto medindo 2,7 cm no compartimento medial."
        result = split_sentences(text)
        self.assertEqual(len(result), 1)

    def test_ignores_blank_lines(self):
        text = "Achado A.\n\n\nAchado B."
        self.assertEqual(split_sentences(text), ["Achado A.", "Achado B."])

    def test_no_empty_sentences_produced(self):
        text = "Achado A..  \nAchado B."
        result = split_sentences(text)
        self.assertTrue(all(s.strip() for s in result))


if __name__ == "__main__":
    unittest.main()
