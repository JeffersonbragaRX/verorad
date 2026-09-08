import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clinical.labels import (
    structure_label, finding_label, location_label, severity_label,
)


class TestLabels(unittest.TestCase):
    def test_known_structure(self):
        self.assertEqual(structure_label("meniscus_medial"), "Menisco medial")

    def test_unknown_structure_falls_back_gracefully(self):
        self.assertEqual(structure_label("some_new_code"), "Some new code")

    def test_finding_known(self):
        self.assertEqual(finding_label("chondropathy"), "Condropatia")

    def test_location_none_is_empty_string(self):
        self.assertEqual(location_label(None), "")

    def test_severity_plain_grade(self):
        self.assertEqual(severity_label("grade_2"), "grau 2")

    def test_severity_grade_range(self):
        self.assertEqual(severity_label("grade_1_2"), "grau 1/2")

    def test_severity_combined_adjective_and_grade(self):
        self.assertEqual(severity_label("leve|grade_2_3"), "leve, grau 2/3")

    def test_severity_none_is_empty_string(self):
        self.assertEqual(severity_label(None), "")

    def test_severity_near_complete(self):
        self.assertEqual(severity_label("near_complete"), "quase completa")


if __name__ == "__main__":
    unittest.main()
