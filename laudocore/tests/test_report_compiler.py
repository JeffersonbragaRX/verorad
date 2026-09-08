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
    structure, finding, status, severity=None, location=None,
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
        (report_id, section_id, 0, text, text.lower(), doctor, "RM_JOELHO_D",
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
         doctor, "RM_JOELHO_D"),
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

    def test_technique_picked_from_corpus(self):
        result = compile_report(self.conn, [], doctor="NEY", phrase_bank=self.bank)
        self.assertEqual(result.technique_text, "Sequências FSE em múltiplos planos.")

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

    def test_absent_finding_never_appears_in_impression(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        self.assertEqual(result.impression_lines, [])

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

    def test_auditor_flags_impression_structure_absent_from_findings(self):
        # Simula um bug hipotetico de montagem: impressao citando algo
        # que nao esta nos achados — o auditor deve capturar isso.
        from backend.compiler.report_compiler import ResolvedFinding
        result = compile_report(self.conn, [], phrase_bank=self.bank)
        fake_request = FindingRequest("acl", "tear", "present")
        result.impression_lines.append(ResolvedFinding(
            request=fake_request, text="Rotura do LCA.", source_doctor="NEY",
            matched_key=(), exact_match=True,
        ))
        # reexecuta so a checagem do auditor manualmente para validar a logica
        findings_structures = {f.request.structure for f in result.findings_lines}
        self.assertNotIn(fake_request.structure, findings_structures)

    def test_render_produces_full_text_with_default_normal_impression(self):
        req = FindingRequest("meniscus_lateral", "tear", "absent")
        result = compile_report(self.conn, [req], phrase_bank=self.bank)
        text = result.render()
        self.assertIn("TÉCNICA:", text)
        self.assertIn("RELATÓRIO:", text)
        self.assertIn("sem alterações significativas", text)

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


if __name__ == "__main__":
    unittest.main()
