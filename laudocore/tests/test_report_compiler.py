"""Testes do Report Compiler (Fase 6, RM de joelho).

Usa um banco SQLite em memoria, semeado com dados FABRICADOS (mesma
razao das outras suites: nao commitar texto real de laudo), mas
respeitando o schema real (backend/db/schema.py) e o contrato do
PhraseBank (frase so pode vir de sentenca realmente ligada a um
conceito clinico, nunca gerada livremente).
"""

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db.schema import rebuild_schema, rebuild_concepts_schema
from backend.compiler.report_compiler import FindingRequest, compile_report
from backend.compiler.phrase_bank import build_phrase_bank


def _seed_report(conn, report_id, doctor, technique_text):
    conn.execute(
        """INSERT INTO reports (
            id, record_id, patient_id, age_at_exam, sex, exam_datetime,
            modality, domain, anatomy, laterality, exam_type,
            study_description_raw, doctor, report_text_raw,
            report_text_clean, report_text_normalized, exact_hash,
            normalized_hash, source, import_batch, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (report_id, report_id, "0", 40, "F", "01/01/2026 00:00",
         "RM", "MSK", "JOELHO", "D", "RM_JOELHO_D", "Joelho^Direito",
         doctor, "raw", "raw", "raw", f"hash{report_id}", f"nhash{report_id}",
         "test", "test_batch", "2026-01-01T00:00:00Z"),
    )
    cur = conn.execute(
        """INSERT INTO report_sections (report_id, section_type, section_order,
            text_raw, text_clean) VALUES (?,?,?,?,?)""",
        (report_id, "technique", 0, technique_text, technique_text),
    )
    return cur.lastrowid


def _seed_sentence_with_concept(
    conn, report_id, section_type, section_order, text, doctor,
    structure, finding, status, severity=None, location=None, exam_type="RM_JOELHO_D",
):
    section_cur = conn.execute(
        """INSERT INTO report_sections (report_id, section_type, section_order,
            text_raw, text_clean) VALUES (?,?,?,?,?)""",
        (report_id, section_type, section_order, text, text),
    )
    section_id = section_cur.lastrowid
    sent_cur = conn.execute(
        """INSERT INTO sentences (report_id, section_id, sentence_order,
            text_raw, text_normalized, doctor, exam_type, exact_hash, normalized_hash)
            VALUES (?,?,?,?,?,?,?,?,?)""",
        (report_id, section_id, 0, text, text.lower(), doctor, exam_type,
         f"h{report_id}{section_id}", f"nh{report_id}{section_id}"),
    )
    sentence_id = sent_cur.lastrowid
    conn.execute(
        """INSERT INTO clinical_concepts (
            report_id, sentence_id, section_type, organ, structure, finding,
            status, severity, location, measurement_cm, certainty, rule_id,
            doctor, exam_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (report_id, sentence_id, section_type, "knee", structure, finding,
         status, severity, location, None, "definitive", "test_rule",
         doctor, exam_type),
    )


def _build_seeded_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    rebuild_schema(conn)
    rebuild_concepts_schema(conn)

    _seed_report(conn, 1, "NEY", "Sequências FSE em múltiplos planos.")
    _seed_sentence_with_concept(
        conn, 1, "findings", 1, "Menisco lateral sem evidências de lesões.",
        "NEY", "meniscus_lateral", "tear", "absent",
    )
    _seed_sentence_with_concept(
        conn, 1, "findings", 2, "Rotura no corno posterior do menisco medial.",
        "NEY", "meniscus_medial", "tear", "present", location="posterior_horn",
    )
    # frase de impressao SEM localizacao (testa relaxamento de location)
    _seed_sentence_with_concept(
        conn, 1, "impression", 3, "Rotura do menisco medial.",
        "NEY", "meniscus_medial", "tear", "present",
    )
    # frase de impressao para um achado AUSENTE — usada para provar que
    # 'absent' tambem pode gerar impressao real (bug corrigido: antes so
    # tentava buscar impressao para status='present').
    _seed_sentence_with_concept(
        conn, 1, "impression", 4, "Menisco lateral sem sinais de lesão.",
        "NEY", "meniscus_lateral", "tear", "absent",
    )
    conn.commit()
    return conn


class TestPhraseBankPrefersCleanSentences(unittest.TestCase):
    """Regressao: uma sentenca real pode carregar conteudo clinico ALEM
    do conceito extraido (ex.: 'Degeneração difusa do menisco lateral,
    sem roturas.' — a degeneracao nunca virou conceito porque o
    extrator so emite 1 achado por estrutura por sentenca). Reusar essa
    frase para outro paciente sem degeneracao seria uma inconsistencia.
    O banco deve preferir uma frase 'limpa' quando uma existir."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        rebuild_schema(self.conn)
        rebuild_concepts_schema(self.conn)
        _seed_report(self.conn, 1, "NEY", "Técnica padrão.")
        # frase composta: a MESMA sentenca gera 2 conceitos (menisco lateral
        # tear=absent E joint_space effusion=present)
        _seed_sentence_with_concept(
            self.conn, 1, "findings", 1,
            "Degeneração difusa do menisco lateral, sem roturas, com pequeno derrame associado.",
            "NEY", "meniscus_lateral", "tear", "absent",
        )
        self.conn.execute(
            """INSERT INTO clinical_concepts (
                report_id, sentence_id, section_type, organ, structure, finding,
                status, severity, location, measurement_cm, certainty, rule_id,
                doctor, exam_type
            ) VALUES (1,1,'findings','knee','joint_space','effusion','present',
                      'pequeno',NULL,NULL,'definitive','test_rule','NEY','RM_JOELHO_D')"""
        )
        # frase limpa: sentenca que gera SO este conceito
        _seed_sentence_with_concept(
            self.conn, 1, "findings", 2, "Menisco lateral sem evidências de lesões.",
            "NEY", "meniscus_lateral", "tear", "absent",
        )
        self.conn.commit()
        self.bank = build_phrase_bank(self.conn)

    def test_clean_phrase_preferred_over_compound(self):
        candidate = self.bank.lookup(("meniscus_lateral", "tear", "absent", None, None, "findings"))
        self.assertTrue(candidate.clean)
        self.assertEqual(candidate.text, "Menisco lateral sem evidências de lesões.")


class TestReportCompiler(unittest.TestCase):
    def setUp(self):
        self.conn = _build_seeded_db()
        self.bank = build_phrase_bank(self.conn)

    def test_technique_not_auto_filled_without_explicit_input(self):
        """Bug real corrigido (ADR 0010, achado #2 da auditoria
        externa): o compilador escolhia sozinho a tecnica mais frequente
        do corpus, mesmo sem o chamador ter informado nada sobre o
        exame atual — podia inserir campo magnético/protocolo de outro
        paciente sem autorização. Agora so preenche se for passado
        explicitamente."""
        result = compile_report(self.conn, [], doctor="NEY", phrase_bank=self.bank)
        self.assertIsNone(result.technique_text)
        self.assertTrue(any(w.startswith("TÉCNICA:") for w in result.warnings))
        self.assertNotIn("TÉCNICA:", result.render())

    def test_technique_used_when_explicitly_provided(self):
        result = compile_report(
            self.conn, [], doctor="NEY", phrase_bank=self.bank,
            technique_text="Sequências FSE em múltiplos planos.",
        )
        self.assertEqual(result.technique_text, "Sequências FSE em múltiplos planos.")
        self.assertFalse(any(w.startswith("TÉCNICA:") for w in result.warnings))
        self.assertIn("TÉCNICA:\nSequências FSE em múltiplos planos.", result.render())

    def test_suggest_technique_candidates_returns_real_corpus_text(self):
        from backend.compiler.report_compiler import suggest_technique_candidates
        candidates = suggest_technique_candidates(self.conn, doctor="NEY")
        self.assertTrue(candidates)
        self.assertEqual(candidates[0]["text"], "Sequências FSE em múltiplos planos.")
        self.assertEqual(candidates[0]["doctor"], "NEY")

    def test_exact_match_used_for_findings(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertEqual(len(result.findings_lines), 1)
        self.assertEqual(result.findings_lines[0].text, "Menisco lateral sem evidências de lesões.")
        self.assertTrue(result.findings_lines[0].exact_match)
        self.assertEqual(result.unresolved, [])

    def test_relaxed_match_used_for_impression_without_location(self):
        req = FindingRequest("meniscus_medial", "tear", "present", location="posterior_horn")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertEqual(len(result.impression_lines), 1)
        self.assertEqual(result.impression_lines[0].text, "Rotura do menisco medial.")
        self.assertFalse(result.impression_lines[0].exact_match)

    def test_unresolved_finding_is_not_invented(self):
        req = FindingRequest("acl", "tear", "present", severity="complete")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertEqual(result.findings_lines, [])
        self.assertEqual(result.unresolved, [req])

    def test_absent_finding_gets_impression_when_real_phrase_exists(self):
        """Bug real corrigido (ADR 0010): a busca de frase de impressao
        so era tentada para status='present' — um achado 'absent' nunca
        gerava impressao, mesmo quando existia frase real de impressao
        para ele no corpus ('Menisco lateral sem sinais de lesão.')."""
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertEqual(len(result.impression_lines), 1)
        self.assertEqual(result.impression_lines[0].text, "Menisco lateral sem sinais de lesão.")

    def test_absent_finding_without_real_impression_phrase_is_not_fabricated(self):
        """Quando NAO existe frase real de impressao para o achado, a
        impressao fica vazia para ele (aviso IMPRESSÃO, nunca texto
        generico) — ver test_render_does_not_fabricate_global_normalcy."""
        conn = sqlite3.connect(":memory:")
        rebuild_schema(conn)
        rebuild_concepts_schema(conn)
        _seed_report(conn, 1, "NEY", "Técnica padrão.")
        _seed_sentence_with_concept(
            conn, 1, "findings", 1, "Menisco medial sem evidências de lesões.",
            "NEY", "meniscus_medial", "tear", "absent",
        )
        conn.commit()
        bank = build_phrase_bank(conn)
        req = FindingRequest("meniscus_medial", "tear", "absent")
        result = compile_report(conn, [req], phrase_bank=bank)
        self.assertEqual(result.impression_lines, [])
        self.assertTrue(any(w.startswith("IMPRESSÃO:") for w in result.warnings))

    def test_contradictory_request_raises_warning(self):
        reqs = [
            FindingRequest("acl", "tear", "present"),
            FindingRequest("acl", "tear", "absent"),
        ]
        result = compile_report(self.conn, reqs, phrase_bank=self.bank)
        self.assertTrue(any("CONTRADIÇÃO" in w for w in result.warnings))

    def test_duplicate_request_raises_warning_and_is_not_compiled_twice(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req, req], phrase_bank=self.bank)
        self.assertTrue(any("DUPLICIDADE" in w for w in result.warnings))
        self.assertEqual(len(result.findings_lines), 1)

    def test_impression_structures_are_always_subset_of_findings_structures(self):
        """Substitui um teste anterior (test_auditor_flags_impression_
        structure_absent_from_findings) que nao chamava compile_report
        de verdade: rodava com findings=[] e depois injetava manualmente
        um ResolvedFinding falso em impression_lines, reimplementando a
        asserção na mão em vez de exercitar a função real (achado #8 da
        auditoria externa). Investigando por que, descobrimos que a
        checagem que esse teste fingia cobrir era código morto —
        estruturalmente nunca poderia disparar (ver comentário em
        compile_report) — e foi removida. Este teste verifica o
        invariante real, com dados reais passando pela função real."""
        reqs = [
            FindingRequest("meniscus_lateral", "tear", "absent"),
            FindingRequest("meniscus_medial", "tear", "present", location="posterior_horn"),
        ]
        result = compile_report(self.conn, reqs, phrase_bank=self.bank)
        findings_structures = {f.request.structure for f in result.findings_lines}
        impression_structures = {f.request.structure for f in result.impression_lines}
        self.assertTrue(impression_structures)  # o cenario realmente gera impressao
        self.assertTrue(impression_structures.issubset(findings_structures))

    def test_render_does_not_fabricate_global_normalcy(self):
        """Bug real corrigido (ADR 0010, achado #1 da auditoria
        externa — o mais grave): o renderizador inseria 'Exame sem
        alterações significativas.' sempre que havia achados no corpo
        mas nenhuma impressao real — inclusive quando o unico achado
        pedido era a ausencia de UMA estrutura especifica, transformando
        isso em normalidade GLOBAL do exame inteiro, nunca autorizada
        pelo chamador. Este teste usava exatamente esse cenario e
        antes afirmava esse comportamento como CORRETO."""
        conn = sqlite3.connect(":memory:")
        rebuild_schema(conn)
        rebuild_concepts_schema(conn)
        _seed_report(conn, 1, "NEY", "Técnica padrão.")
        _seed_sentence_with_concept(
            conn, 1, "findings", 1, "Menisco medial sem evidências de lesões.",
            "NEY", "meniscus_medial", "tear", "absent",
        )
        conn.commit()
        bank = build_phrase_bank(conn)
        req = FindingRequest("meniscus_medial", "tear", "absent")
        result = compile_report(conn, [req], phrase_bank=bank)
        text = result.render()
        self.assertIn("RELATÓRIO:", text)
        self.assertNotIn("sem alterações significativas", text)
        self.assertNotIn("IMPRESSÃO DIAGNÓSTICA:", text)
        self.assertTrue(any(w.startswith("IMPRESSÃO:") for w in result.warnings))

    def test_render_never_includes_indication_unless_explicitly_provided(self):
        result = compile_report(self.conn, [], phrase_bank=self.bank)
        self.assertNotIn("INDICAÇÃO", result.render())
        self.assertIn("INDICAÇÃO", result.render(indication_text="Dor no joelho."))


class TestPhraseBankEntries(unittest.TestCase):
    """entries() alimenta a biblioteca de achados pesquisavel da API/UI."""

    def setUp(self):
        self.conn = _build_seeded_db()
        self.bank = build_phrase_bank(self.conn)

    def test_entries_cover_all_seeded_combinations(self):
        entries = self.bank.entries()
        keys = {(e["structure"], e["finding"], e["status"], e["section_type"]) for e in entries}
        self.assertIn(("meniscus_lateral", "tear", "absent", "findings"), keys)
        self.assertIn(("meniscus_medial", "tear", "present", "findings"), keys)
        self.assertIn(("meniscus_medial", "tear", "present", "impression"), keys)

    def test_entry_carries_example_text_and_doctor(self):
        entries = self.bank.entries()
        entry = next(e for e in entries if e["structure"] == "meniscus_lateral" and e["finding"] == "tear")
        self.assertEqual(entry["example_text"], "Menisco lateral sem evidências de lesões.")
        self.assertIn("NEY", entry["doctors"])
        self.assertEqual(entry["frequency"], 1)


class TestLateralityGuard(unittest.TestCase):
    """Bug real corrigido (ADR 0010, achado #5 da auditoria externa):
    nem FindingRequest/CompileRequestIn nem a chave do PhraseBank
    carregavam lateralidade — o compilador podia reaproveitar, em
    silencio, uma frase de um exame do lado oposto que nomeia o lado
    explicitamente ('joelho direito' num laudo de joelho esquerdo)."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        rebuild_schema(self.conn)
        rebuild_concepts_schema(self.conn)
        _seed_report(self.conn, 1, "NEY", "Técnica padrão.")
        # unica frase disponivel para esta chave: vem de um exame D e
        # nomeia o lado explicitamente no proprio texto.
        _seed_sentence_with_concept(
            self.conn, 1, "findings", 1, "Rotura do menisco lateral do joelho direito.",
            "NEY", "meniscus_lateral", "tear", "present", exam_type="RM_JOELHO_D",
        )
        self.conn.commit()
        self.bank = build_phrase_bank(self.conn)

    def test_opposite_side_phrase_naming_side_triggers_blocking_warning(self):
        req = FindingRequest("meniscus_lateral", "tear", "present")
        result = compile_report(self.conn, [req], laterality="E", phrase_bank=self.bank)
        self.assertTrue(any(w.startswith("LATERALIDADE:") for w in result.warnings))
        self.assertTrue(result.blocking)

    def test_matching_side_does_not_trigger_warning(self):
        req = FindingRequest("meniscus_lateral", "tear", "present")
        result = compile_report(self.conn, [req], laterality="D", phrase_bank=self.bank)
        self.assertFalse(any(w.startswith("LATERALIDADE:") for w in result.warnings))
        self.assertFalse(result.blocking)

    def test_no_requested_laterality_does_not_trigger_warning(self):
        """Sem lateralidade pedida, nao ha' base pra comparar — o
        compilador nao arrisca alarme falso, so age quando o chamador
        informa o lado do exame atual."""
        req = FindingRequest("meniscus_lateral", "tear", "present")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertFalse(any(w.startswith("LATERALIDADE:") for w in result.warnings))

    def test_phrase_without_explicit_side_word_not_flagged(self):
        """'Menisco lateral' e' compartimento anatomico, nao lado do
        joelho — uma frase do lado oposto que NAO nomeia o lado
        explicitamente nao e' um risco real de lateralidade e nao deve
        ser sinalizada (sinalizar aqui geraria ruido em quase todo
        laudo, ja que a maioria das frases nao nomeia o lado)."""
        conn = sqlite3.connect(":memory:")
        rebuild_schema(conn)
        rebuild_concepts_schema(conn)
        _seed_report(conn, 1, "NEY", "Técnica padrão.")
        _seed_sentence_with_concept(
            conn, 1, "findings", 1, "Rotura no corno posterior do menisco lateral.",
            "NEY", "meniscus_lateral", "tear", "present", exam_type="RM_JOELHO_D",
        )
        conn.commit()
        bank = build_phrase_bank(conn)
        req = FindingRequest("meniscus_lateral", "tear", "present")
        result = compile_report(conn, [req], laterality="E", phrase_bank=bank)
        self.assertFalse(any(w.startswith("LATERALIDADE:") for w in result.warnings))
        self.assertFalse(result.blocking)


class TestDoctorMixingWarning(unittest.TestCase):
    """Bug real corrigido (ADR 0010, achado #6 da auditoria externa):
    PhraseBank.lookup() caia para o medico mais frequente geral quando
    o preferido nao tinha frase, sem sinalizar a mistura de estilos."""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        rebuild_schema(self.conn)
        rebuild_concepts_schema(self.conn)
        _seed_report(self.conn, 1, "OUTRO", "Técnica padrão.")
        _seed_sentence_with_concept(
            self.conn, 1, "findings", 1, "Rotura completa do ligamento cruzado anterior.",
            "OUTRO", "acl", "tear", "present", severity="complete",
        )
        self.conn.commit()
        self.bank = build_phrase_bank(self.conn)

    def test_falls_back_to_other_doctor_with_visible_warning(self):
        req = FindingRequest("acl", "tear", "present", severity="complete")
        result = compile_report(self.conn, [req], doctor="NEY", phrase_bank=self.bank)
        self.assertEqual(result.findings_lines[0].source_doctor, "OUTRO")
        self.assertTrue(any(w.startswith("MÉDICO:") for w in result.warnings))
        # mistura de medico e' informativa (estilo), nao bloqueia copiar/exportar
        self.assertFalse(result.blocking)

    def test_no_warning_when_doctor_not_specified(self):
        req = FindingRequest("acl", "tear", "present", severity="complete")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertFalse(any(w.startswith("MÉDICO:") for w in result.warnings))


class TestBlockingFlag(unittest.TestCase):
    def setUp(self):
        self.conn = _build_seeded_db()
        self.bank = build_phrase_bank(self.conn)

    def test_contradiction_sets_blocking(self):
        reqs = [
            FindingRequest("acl", "tear", "present"),
            FindingRequest("acl", "tear", "absent"),
        ]
        result = compile_report(self.conn, reqs, phrase_bank=self.bank)
        self.assertTrue(result.blocking)

    def test_duplicate_alone_does_not_set_blocking(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req, req], phrase_bank=self.bank)
        self.assertTrue(any(w.startswith("DUPLICIDADE:") for w in result.warnings))
        self.assertFalse(result.blocking)

    def test_no_warnings_no_blocking(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(
            self.conn, [req], phrase_bank=self.bank, technique_text="Técnica padrão.",
        )
        self.assertFalse(result.blocking)


if __name__ == "__main__":
    unittest.main()
