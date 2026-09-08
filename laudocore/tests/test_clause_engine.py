"""Testes ADVERSARIAIS do Clause Engine (Fase 4A).

Cobrem, um a um, os cenarios exigidos pela secao 6 do PROMPT MESTRE V2
— os casos em que a versao anterior (checagem de negacao na sentenca
inteira) invertia polaridade ou trocava a estrutura alvo.

Frases fabricadas no padrao real do corpus (nao copiadas de laudo de
paciente), cobrindo multiplas modalidades e dominios — o engine e'
agnostico de dominio e precisa ser testado como tal.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.clinical.clause_engine import analyze_sentence  # noqa: E402


def span(sentence: str, mention: str) -> tuple[int, int]:
    """Posicao da mencao na sentenca (o engine trabalha por posicao)."""
    idx = sentence.lower().index(mention.lower())
    return idx, idx + len(mention)


class TestNegationScope(unittest.TestCase):
    def test_positive_acl_with_negated_meniscus_in_same_sentence(self):
        """Caso 1 do prompt. Bug real da versao anterior: 'sem lesao'
        (sobre o menisco) negava a rotura do LCA afirmada antes."""
        s = "Rotura do ligamento cruzado anterior, sem lesão meniscal."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Rotura"))[0], "present")
        self.assertEqual(a.status_at(*span(s, "lesão meniscal"))[0], "absent")

    def test_medial_negative_lateral_positive_same_sentence(self):
        """Caso 2 do prompt: os dois meniscos na mesma sentenca com
        polaridades opostas."""
        s = "Menisco medial sem roturas, observando-se lesão do menisco lateral."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "roturas"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "lesão do menisco lateral"))[0], "present")

    def test_partial_tear_with_negated_transfixing_component(self):
        """Caso 3 do prompt: negacao PARCIAL — nega o qualificador, nao
        o achado principal. 'Rotura parcial' continua presente."""
        s = "Rotura parcial do supraespinal sem componente transfixante."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Rotura parcial"))[0], "present")
        self.assertEqual(a.status_at(*span(s, "componente transfixante"))[0], "absent")

    def test_degeneration_present_with_tear_absent(self):
        """Caso 4 do prompt: eixos independentes na mesma sentenca."""
        s = "Degeneração difusa do menisco lateral, sem roturas."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Degeneração difusa"))[0], "present")
        self.assertEqual(a.status_at(*span(s, "roturas"))[0], "absent")

    def test_negation_does_not_leak_past_adversative(self):
        s = "Sem sinais de fratura, porém há edema medular no platô tibial."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "fratura"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "edema medular"))[0], "present")

    def test_sem_does_not_match_sempre(self):
        """'sempre' contem 'sem' — fronteira de palavra obrigatoria."""
        s = "Achado sempre presente nos controles anteriores."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "presente"))[0], "present")

    def test_negation_applies_to_coordinated_pair(self):
        """Coordenacao com 'e' NAO encerra escopo: a negacao vale para
        os dois itens coordenados."""
        s = "Sem sinais de fratura ou luxação."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "fratura"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "luxação"))[0], "absent")


class TestNormalityIsNotNegation(unittest.TestCase):
    """Normalidade explicita e' diferente de negacao de um achado — a
    especificacao trata as duas como coisas distintas (secao 13)."""

    def test_preserved_structure_marked_normal_not_absent(self):
        s = "Ligamentos cruzados e colaterais preservados."
        a = analyze_sentence(s)
        status, _ = a.status_at(*span(s, "Ligamentos cruzados"))
        self.assertEqual(status, "normal")

    def test_normality_does_not_leak_to_next_clause(self):
        s = "Meniscos preservados, com rotura do supraespinal."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Meniscos"))[0], "normal")
        self.assertEqual(a.status_at(*span(s, "rotura do supraespinal"))[0], "present")


class TestCertainty(unittest.TestCase):
    def test_cannot_exclude(self):
        s = "Não se pode excluir lesão secundária."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "lesão secundária")), "cannot_exclude")

    def test_probable_vs_possible(self):
        s = "Achado sugestivo de hemangioma."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "hemangioma")), "probable")

        s2 = "Nódulo que pode corresponder a granuloma."
        a2 = analyze_sentence(s2)
        self.assertEqual(a2.certainty_at(*span(s2, "granuloma")), "possible")

    def test_definite_when_no_hedge(self):
        s = "Fratura do rádio distal."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "Fratura")), "definite")

    def test_uncertainty_does_not_leak_across_clause(self):
        """Caso 7 do prompt: achado incerto no corpo nao pode tornar
        incerto um achado definitivo citado na mesma sentenca."""
        s = "Nódulo possivelmente inflamatório, associado a fratura do platô tibial."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "Nódulo")), "possible")
        self.assertEqual(a.certainty_at(*span(s, "fratura do platô tibial")), "definite")

    def test_certainty_never_increases(self):
        """Com dois cues no mesmo escopo, prevalece o MENOR nivel."""
        s = "Provavelmente sequelar, não se pode excluir componente agudo."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "componente agudo")), "cannot_exclude")


class TestDoubleNegationAndCueOverlap(unittest.TestCase):
    """Dois bugs reais encontrados ao rodar o engine sobre as 150.868
    sentencas clinicas do corpus (nao em frase fabricada)."""

    def test_cannot_exclude_is_not_read_as_absence(self):
        """INVERSAO DE POLARIDADE: 'não podendo ser descartada
        infiltração' significa que a infiltracao NAO pode ser excluida
        (incerteza). O cue de negacao 'descartada' sozinho marcava o
        achado como AUSENTE — o oposto do que o laudo diz."""
        s = "Nódulo abaulando os contornos, não podendo ser descartada infiltração."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "infiltração"))[0], "present")
        self.assertEqual(a.certainty_at(*span(s, "infiltração")), "cannot_exclude")

    def test_nao_e_possivel_excluir_keeps_cannot_exclude(self):
        """'possível' dentro de 'não é possível excluir' disparava um
        segundo cue (possible) competindo com cannot_exclude."""
        s = "Diante da sobreposição dos achados, não é possível excluir focos neoplásicos."
        a = analyze_sentence(s)
        self.assertEqual(a.certainty_at(*span(s, "focos neoplásicos")), "cannot_exclude")
        kinds = [(c.kind, c.value) for c in a.cues]
        self.assertNotIn(("uncertainty", "possible"), kinds)

    def test_longer_negation_cue_wins_over_shorter(self):
        s = "Sem sinais de fratura."
        a = analyze_sentence(s)
        negations = [c for c in a.cues if c.kind == "negation"]
        self.assertEqual(len(negations), 1)
        self.assertIn("sinais", negations[0].raw.lower())


class TestAppositionRuleSafety(unittest.TestCase):
    """A regra de aposicao (qualificador no fim da frase modifica a
    clausula anterior) e' o unico ponto em que um cue atravessa uma
    virgula para tras. Estes testes fixam a fronteira: ela NAO pode
    reabrir o vazamento de negacao que a segmentacao existe para
    impedir."""

    def test_apposition_does_not_apply_when_clause_has_own_content(self):
        s = "Rotura do ligamento cruzado anterior, sem lesão meniscal."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Rotura"))[0], "present")

    def test_apposition_does_not_reach_across_two_clauses(self):
        s = "Rotura do supraespinal, tendinopatia do infraespinal, inespecífica."
        a = analyze_sentence(s)
        # o qualificador alcanca a clausula imediatamente anterior...
        self.assertEqual(a.etiologic_at(*span(s, "tendinopatia do infraespinal")), "nonspecific")
        # ...e nao a primeira, duas clausulas atras
        self.assertIsNone(a.etiologic_at(*span(s, "Rotura do supraespinal")))


class TestEtiologicQualifier(unittest.TestCase):
    """'inespecífico' (970x no corpus) e 'indeterminado' (292x)
    qualificam a NATUREZA do achado, nao a existencia dele. Mapear para
    incerteza rebaixaria indevidamente a certeza do proprio achado."""

    def test_nonspecific_does_not_lower_certainty(self):
        s = "Focos de alteração de sinal na substância branca, inespecíficos."
        a = analyze_sentence(s)
        pos = span(s, "Focos de alteração de sinal")
        self.assertEqual(a.status_at(*pos)[0], "present")
        self.assertEqual(a.certainty_at(*pos), "definite")
        self.assertEqual(a.etiologic_at(*pos), "nonspecific")

    def test_indeterminate(self):
        s = "Lesão hepática de aspecto indeterminado."
        a = analyze_sentence(s)
        self.assertEqual(a.etiologic_at(*span(s, "Lesão hepática")), "indeterminate")


class TestMeasurementsAndGrades(unittest.TestCase):
    def test_two_measurements_bound_to_own_clause(self):
        """Caso 6 do prompt: medida do cisto nao pode ser atribuida a
        lesao condral citada na mesma sentenca."""
        s = "Cisto poplíteo medindo 3,2 cm, com lesão condral de 0,8 cm no côndilo medial."
        a = analyze_sentence(s)
        cyst = a.measurements_for(*span(s, "Cisto poplíteo"))
        chondral = a.measurements_for(*span(s, "lesão condral"))
        self.assertEqual([m.values[0] for m in cyst], [3.2])
        self.assertEqual([m.values[0] for m in chondral], [0.8])

    def test_three_dimensional_measurement(self):
        s = "Próstata medindo 3,4 x 4,0 x 4,5 cm."
        a = analyze_sentence(s)
        m = a.measurements[0]
        self.assertEqual(m.values, [3.4, 4.0, 4.5])
        self.assertEqual(m.unit, "cm")

    def test_grade_range_not_truncated(self):
        s = "Condropatia femoropatelar grau II/III."
        a = analyze_sentence(s)
        self.assertEqual(a.grades_for(*span(s, "Condropatia")), ["2_3"])

    def test_different_grades_in_different_clauses(self):
        """Caso 5 do prompt: condropatia em compartimentos diferentes
        com graus diferentes na mesma sentenca."""
        s = "Condropatia patelofemoral grau III, condropatia femorotibial medial grau I."
        a = analyze_sentence(s)
        self.assertEqual(a.grades_for(*span(s, "Condropatia patelofemoral")), ["3"])
        self.assertEqual(a.grades_for(*span(s, "condropatia femorotibial medial")), ["1"])


class TestLaterality(unittest.TestCase):
    def test_local_laterality_detected(self):
        """Caso 8 do prompt: o lado citado NO CORPO e' local e pode
        divergir do lado do exame (metadado). O engine devolve o local;
        combinar com o global e' decisao do chamador, que precisa poder
        ver o conflito."""
        s = "Derrame articular no joelho esquerdo."
        a = analyze_sentence(s)
        self.assertEqual(a.laterality_at(*span(s, "Derrame articular")), "left")

    def test_bilateral(self):
        s = "Alterações degenerativas bilaterais nos quadris."
        a = analyze_sentence(s)
        self.assertEqual(a.laterality_at(*span(s, "Alterações degenerativas")), "bilateral")

    def test_two_sides_in_one_sentence_bound_per_clause(self):
        s = "Rotura do supraespinal à direita, tendinopatia à esquerda."
        a = analyze_sentence(s)
        self.assertEqual(a.laterality_at(*span(s, "Rotura do supraespinal")), "right")
        self.assertEqual(a.laterality_at(*span(s, "tendinopatia")), "left")


class TestTemporalityComparisonPostop(unittest.TestCase):
    def test_postoperative_reconstruction_vs_native(self):
        """Caso 9 do prompt: enxerto/reconstrucao nao pode ser lido como
        estrutura nativa — o contexto precisa ficar explicito."""
        s = "Reconstrução do ligamento cruzado anterior, enxerto íntegro."
        a = analyze_sentence(s)
        self.assertEqual(a.postop_at(*span(s, "Reconstrução")), "postoperative")
        self.assertEqual(a.postop_at(*span(s, "enxerto")), "graft")

    def test_temporality_chronic(self):
        s = "Alterações crônicas na inserção do tendão."
        a = analyze_sentence(s)
        self.assertEqual(a.temporality_at(*span(s, "Alterações")), "chronic")

    def test_comparison_stable_and_increased(self):
        s = "Nódulo estável, com linfonodo aumentado."
        a = analyze_sentence(s)
        self.assertEqual(a.comparison_at(*span(s, "Nódulo")), "stable")
        self.assertEqual(a.comparison_at(*span(s, "linfonodo")), "increased")


class TestCrossDomainGenerality(unittest.TestCase):
    """O engine e' agnostico de dominio: os mesmos mecanismos precisam
    funcionar fora do MSK (onde o vertical anterior foi calibrado)."""

    def test_neuro(self):
        s = "Sem sinais de hemorragia intracraniana, com hipersinal na substância branca periventricular."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "hemorragia intracraniana"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "hipersinal"))[0], "present")

    def test_thorax(self):
        s = "Ausência de consolidações alveolares, notando-se nódulo pulmonar de 0,6 cm."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "consolidações alveolares"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "nódulo pulmonar"))[0], "present")
        self.assertEqual(a.measurements_for(*span(s, "nódulo pulmonar"))[0].values, [0.6])

    def test_abdomen(self):
        s = "Fígado sem lesões focais, vesícula biliar com cálculo de 1,1 cm."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "lesões focais"))[0], "absent")
        self.assertEqual(a.status_at(*span(s, "cálculo"))[0], "present")

    def test_radiography(self):
        s = "Espaços articulares preservados, sem sinais de fratura."
        a = analyze_sentence(s)
        self.assertEqual(a.status_at(*span(s, "Espaços articulares"))[0], "normal")
        self.assertEqual(a.status_at(*span(s, "fratura"))[0], "absent")


if __name__ == "__main__":
    unittest.main()
