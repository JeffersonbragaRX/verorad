"""Testes do extrator de conceitos clinicos (Fase 4, RM de joelho).

Frases fabricadas (genericas, sem relacao com paciente real), cobrindo
os padroes reais encontrados na revisao manual da amostra de extracao
(ver data/derived/qa/QA_REPORT_FASE4.json) — incluindo um caso que foi
um bug real corrigido durante o desenvolvimento (ver
test_patella_word_boundary_not_confused_with_patellar_tendon).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clinical.knee_concepts import extract_concepts


def _by_structure(result, structure):
    return [c for c in result.concepts if c.structure == structure]


class TestMeniscus(unittest.TestCase):
    def test_tear_present_with_location(self):
        r = extract_concepts("rotura no corno posterior do menisco medial.")
        c = _by_structure(r, "meniscus_medial")[0]
        self.assertEqual(c.finding, "tear")
        self.assertEqual(c.status, "present")
        self.assertEqual(c.location, "posterior_horn")

    def test_tear_negated(self):
        r = extract_concepts("menisco lateral sem sinais de rotura.")
        c = _by_structure(r, "meniscus_lateral")[0]
        self.assertEqual(c.status, "absent")

    def test_plural_meniscos_yields_both_sides(self):
        r = extract_concepts("meniscos sem evidências de lesões.")
        self.assertTrue(_by_structure(r, "meniscus_medial"))
        self.assertTrue(_by_structure(r, "meniscus_lateral"))
        for c in r.concepts:
            self.assertEqual(c.status, "absent")

    def test_degeneration_without_tear(self):
        r = extract_concepts("degeneração no corno posterior do menisco medial.")
        c = _by_structure(r, "meniscus_medial")[0]
        self.assertEqual(c.finding, "degeneration")


class TestCruciateLigaments(unittest.TestCase):
    def test_acl_complete_tear(self):
        r = extract_concepts("rotura completa do ligamento cruzado anterior.")
        c = _by_structure(r, "acl")[0]
        self.assertEqual(c.finding, "tear")
        self.assertEqual(c.status, "present")
        self.assertEqual(c.severity, "complete")

    def test_pcl_preserved(self):
        r = extract_concepts("ligamento cruzado posterior íntegro.")
        c = _by_structure(r, "pcl")[0]
        self.assertEqual(c.status, "absent")

    def test_combined_coordinated_form_yields_all_four_ligaments(self):
        r = extract_concepts("ligamentos cruzados e colaterais íntegros.")
        structures = {c.structure for c in r.concepts}
        self.assertEqual(structures, {"acl", "pcl", "mcl", "lcl"})
        self.assertTrue(all(c.status == "absent" for c in r.concepts))


class TestChondropathy(unittest.TestCase):
    def test_grade_extraction_roman(self):
        r = extract_concepts("condropatia patelofemoral grau iii.")
        c = r.concepts[0]
        self.assertIn("grade_3", c.severity)
        self.assertEqual(c.location, "patellofemoral")

    def test_patelar_fallback_maps_to_patellofemoral(self):
        r = extract_concepts("condropatia patelar grau iv.")
        c = r.concepts[0]
        self.assertEqual(c.location, "patellofemoral")

    def test_no_compartment_mentioned_is_unspecified_not_guessed(self):
        r = extract_concepts("condropatia difusa de grau leve.")
        c = r.concepts[0]
        self.assertIsNone(c.location)
        self.assertEqual(c.rule_id, "chondropathy_unspecified_compartment")


class TestEffusion(unittest.TestCase):
    def test_severity_captured(self):
        r = extract_concepts("pequeno derrame articular.")
        c = r.concepts[0]
        self.assertEqual(c.finding, "effusion")
        self.assertEqual(c.severity, "pequeno")


class TestCyst(unittest.TestCase):
    def test_measurement_extracted(self):
        r = extract_concepts("cisto poplíteo medindo 2,7 cm.")
        c = _by_structure(r, "baker_cyst")[0]
        self.assertEqual(c.measurement_cm, 2.7)


class TestPatellaWordBoundaryBug(unittest.TestCase):
    """Regressao: 'patela' e prefixo textual de 'patelar'. Um match por
    substring simples atribuiria ao OSSO patela um achado que na
    verdade e sobre o TENDAO patelar. Bug real encontrado na revisao
    manual da Fase 4."""

    def test_patella_word_boundary_not_confused_with_patellar_tendon(self):
        r = extract_concepts("tendões do quadríceps e patelar de aspecto preservado.")
        structures = {c.structure for c in r.concepts}
        self.assertIn("quadriceps_tendon", structures)
        self.assertIn("patellar_tendon", structures)
        self.assertNotIn("patella", structures)

    def test_bare_patella_word_is_still_detected(self):
        r = extract_concepts("patela normoposicionada e de altura preservada.")
        self.assertIn("patella", {c.structure for c in r.concepts})


class TestNoFalsePositiveOnUnrelatedSentence(unittest.TestCase):
    def test_technique_sentence_yields_no_concepts(self):
        r = extract_concepts("sequências fse e cortes multiplanares em aparelho de alto campo.")
        self.assertEqual(r.concepts, [])


if __name__ == "__main__":
    unittest.main()
