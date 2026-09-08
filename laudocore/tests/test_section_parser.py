"""Testes do section parser contra os padroes estruturais REAIS
observados por medico no vertical RM_JOELHO_D/RM_JOELHO_E (ver
docs/data_dictionary.md). O texto clinico abaixo e fabricado
(generico, sem relacao com nenhum paciente real) — apenas a
ESTRUTURA (cabecalhos, formato inline vs. isolado) reproduz o que foi
observado no corpus real, para nao commitar texto de laudo real no
repositorio.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.normalization.text_normalization import clean
from backend.parsers.section_parser import parse_sections

# Padrao CAIO/RAFAEL: cabecalho + conteudo na MESMA linha.
INLINE_STYLE = """RESSONÂNCIA MAGNÉTICA
JOELHO DIREITO
INFORMAÇÕES CLÍNICAS: dor no joelho.
TÉCNICA: Exame realizado em aparelho de alto campo.
RELATÓRIO:
Meniscos com morfologia e sinal normais.
Ligamentos cruzados e colaterais preservados.
IMPRESSÃO DIAGNÓSTICA:
Exame sem alterações significativas.
"""

# Padrao NEY: cabecalho isolado, CID como tag solta dentro da indicacao,
# secao de comparacao ocasional.
STANDALONE_STYLE_WITH_CID_AND_COMPARISON = """RESSONÂNCIA MAGNÉTICA
JOELHO ESQUERDO
INDICAÇÃO CLÍNICA:
CID M25.5
TÉCNICA:
Sequências FSE em múltiplos planos.
RELATÓRIO:
Menisco lateral sem evidências de lesões.
IMPRESSÃO DIAGNÓSTICA:
Exame sem alterações significativas.
ANÁLISE COMPARATIVA:
Sem alterações em relação ao exame anterior.
"""

# Padrao SAMIR: sem indicacao/impressao separadas, tudo em um bloco de
# achados apos "OS SEGUINTES ASPECTOS FORAM OBSERVADOS:".
NO_IMPRESSION_STYLE = """RESSONÂNCIA MAGNÉTICA BIOMATRIX
JOELHO ESQUERDO
TÉCNICA DE EXAME:
Sequências multiplanares ponderadas em T1 e T2.
OS SEGUINTES ASPECTOS FORAM OBSERVADOS:
Artropatia degenerativa leve.
Discreto derrame articular.
"""

UNKNOWN_HEADER_STYLE = """RESSONÂNCIA MAGNÉTICA
JOELHO DIREITO
RELATÓRIO:
Achado principal sem particularidades.
ACHADO ADICIONAL:
Pequeno cisto poplíteo.
"""


class TestSectionParserInlineStyle(unittest.TestCase):
    def setUp(self):
        self.result = parse_sections(clean(INLINE_STYLE))

    def test_finds_all_expected_types(self):
        for t in ("indication", "technique", "findings", "impression"):
            self.assertTrue(self.result.has_type(t), f"tipo ausente: {t}")

    def test_inline_content_is_captured_not_lost(self):
        indication = next(s for s in self.result.sections if s.section_type == "indication")
        self.assertIn("dor no joelho", indication.text_raw)
        technique = next(s for s in self.result.sections if s.section_type == "technique")
        self.assertIn("alto campo", technique.text_raw)

    def test_no_unmatched_headers(self):
        self.assertEqual(self.result.unmatched_header_candidates, [])


class TestSectionParserStandaloneWithCidAndComparison(unittest.TestCase):
    def setUp(self):
        self.result = parse_sections(clean(STANDALONE_STYLE_WITH_CID_AND_COMPARISON))

    def test_finds_comparison_section(self):
        self.assertTrue(self.result.has_type("comparison"))

    def test_cid_tag_stays_inside_indication_not_split_out(self):
        indication = next(s for s in self.result.sections if s.section_type == "indication")
        self.assertIn("CID M25.5", indication.text_raw)
        self.assertEqual(self.result.unmatched_header_candidates, [])

    def test_section_order_is_sequential(self):
        orders = [s.section_order for s in self.result.sections]
        self.assertEqual(orders, sorted(orders))


class TestSectionParserNoImpressionStyle(unittest.TestCase):
    def setUp(self):
        self.result = parse_sections(clean(NO_IMPRESSION_STYLE))

    def test_technique_and_findings_present(self):
        self.assertTrue(self.result.has_type("technique"))
        self.assertTrue(self.result.has_type("findings"))

    def test_does_not_fabricate_missing_impression(self):
        # Este medico genuinamente nao separa impressao — o parser NAO
        # deve inventar uma secao de impressao que nao existe no texto.
        self.assertFalse(self.result.has_type("impression"))
        self.assertFalse(self.result.has_type("indication"))


class TestSectionParserUnknownHeader(unittest.TestCase):
    def setUp(self):
        self.result = parse_sections(clean(UNKNOWN_HEADER_STYLE))

    def test_unknown_header_flagged_not_guessed(self):
        self.assertIn("ACHADO ADICIONAL:", self.result.unmatched_header_candidates)
        other_sections = [s for s in self.result.sections if s.section_type == "other"]
        self.assertTrue(any(s.unmatched_header for s in other_sections))

    def test_content_after_unknown_header_is_preserved(self):
        unmatched = next(s for s in self.result.sections if s.unmatched_header)
        self.assertIn("cisto poplíteo", unmatched.text_raw)


if __name__ == "__main__":
    unittest.main()
