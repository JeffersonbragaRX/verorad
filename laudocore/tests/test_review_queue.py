import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clinical.knee_concepts import extract_concepts
from backend.clinical.review_queue import detect_ambiguities


def _reasons(text):
    result = extract_concepts(text)
    items = detect_ambiguities(text, result.concepts)
    return {i.reason for i in items}, items


class TestHedgeLanguage(unittest.TestCase):
    def test_hedge_cue_flagged(self):
        reasons, items = _reasons(
            "imagem cística provavelmente relacionada a cisto gangliônico."
        )
        self.assertIn("hedge_language", reasons)

    def test_present_pathology_with_hedge_is_medium_risk(self):
        _, items = _reasons("rotura do ligamento cruzado anterior, sugestivo de lesão crônica.")
        item = next(i for i in items if i.reason == "hedge_language")
        self.assertEqual(item.risk_level, "medium")

    def test_no_hedge_no_flag(self):
        reasons, _ = _reasons("rotura completa do ligamento cruzado anterior.")
        self.assertNotIn("hedge_language", reasons)


class TestPostSurgicalContext(unittest.TestCase):
    def test_reconstruction_context_flagged_as_high_risk(self):
        reasons, items = _reasons(
            "pós-operatório de reconstrução do ligamento cruzado anterior, "
            "com rotura parcial do enxerto."
        )
        self.assertIn("post_surgical_context", reasons)
        item = next(i for i in items if i.reason == "post_surgical_context")
        self.assertEqual(item.risk_level, "high")

    def test_meniscectomy_context_flagged(self):
        reasons, _ = _reasons(
            "sinais de meniscectomia medial parcial prévia com redução volumétrica "
            "e rotura do remanescente do menisco medial."
        )
        self.assertIn("post_surgical_context", reasons)

    def test_no_flag_without_any_concept_extracted(self):
        # cue presente mas nenhum achado estruturado foi extraido desta frase
        reasons, _ = _reasons("controle evolutivo pós-operatório sem particularidades técnicas.")
        self.assertNotIn("post_surgical_context", reasons)


class TestMultipleMeasurements(unittest.TestCase):
    def test_two_measurements_flagged(self):
        reasons, _ = _reasons(
            "cisto poplíteo medindo 2,7 cm, associado a cisto parameniscal medindo 1,2 cm."
        )
        self.assertIn("multiple_measurements", reasons)

    def test_single_measurement_not_flagged(self):
        reasons, _ = _reasons("cisto poplíteo medindo 2,7 cm.")
        self.assertNotIn("multiple_measurements", reasons)


class TestGradeRangeOverflow(unittest.TestCase):
    def test_three_value_range_flagged(self):
        reasons, _ = _reasons("condropatia patelofemoral grau i/ii/iii.")
        self.assertIn("grade_range_overflow", reasons)

    def test_two_value_range_not_flagged(self):
        reasons, _ = _reasons("condropatia patelofemoral grau i/ii.")
        self.assertNotIn("grade_range_overflow", reasons)


class TestCleanSentenceNoAmbiguity(unittest.TestCase):
    def test_no_items_for_clean_sentence(self):
        reasons, items = _reasons("rotura completa do ligamento cruzado anterior.")
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
