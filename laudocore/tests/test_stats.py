"""Testes da estatistica de associacao (stdlib puro, sem scipy).

Valores de referencia conferidos contra resultados publicados/canonicos
de Fisher exato — a implementacao nao pode ser validada 'por parecer
razoavel'.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.analysis.stats import (  # noqa: E402
    association, benjamini_hochberg, fisher_exact_two_sided,
)


class TestFisherExact(unittest.TestCase):
    def test_tea_tasting_lady(self):
        """Experimento classico de Fisher (lady tasting tea), 4x4 acertos:
        p bicaudal conhecido = 1/35 ≈ 0.02857."""
        self.assertAlmostEqual(fisher_exact_two_sided(4, 0, 0, 4), 2 / 70, places=6)

    def test_independent_table_gives_p_one(self):
        self.assertAlmostEqual(fisher_exact_two_sided(5, 5, 5, 5), 1.0, places=6)

    def test_symmetry(self):
        self.assertAlmostEqual(fisher_exact_two_sided(3, 7, 8, 2),
                               fisher_exact_two_sided(7, 3, 2, 8), places=9)

    def test_empty_table(self):
        self.assertEqual(fisher_exact_two_sided(0, 0, 0, 0), 1.0)

    def test_strong_association_is_significant(self):
        self.assertLess(fisher_exact_two_sided(50, 2, 3, 45), 1e-10)


class TestAssociation(unittest.TestCase):
    def test_no_association_ratios_are_one(self):
        r = association(25, 25, 25, 25)
        self.assertAlmostEqual(r.odds_ratio, 1.0, places=6)
        self.assertAlmostEqual(r.prevalence_ratio, 1.0, places=6)
        self.assertAlmostEqual(r.absolute_difference, 0.0, places=6)
        self.assertAlmostEqual(r.lift, 1.0, places=6)

    def test_denominator_and_conditional_probabilities(self):
        r = association(30, 70, 10, 90)
        self.assertEqual(r.eligible_denominator, 200)
        self.assertAlmostEqual(r.p_b_given_a, 0.30)
        self.assertAlmostEqual(r.p_b_without_a, 0.10)
        self.assertAlmostEqual(r.absolute_difference, 0.20)
        self.assertAlmostEqual(r.prevalence_ratio, 3.0)

    def test_confidence_interval_excludes_one_when_strong(self):
        r = association(60, 40, 10, 90)
        lo, hi = r.odds_ratio_ci
        self.assertGreater(lo, 1.0)
        self.assertLess(lo, r.odds_ratio)
        self.assertGreater(hi, r.odds_ratio)

    def test_zero_cell_does_not_break_ci(self):
        """Correcao de Haldane-Anscombe: sem ela o IC seria indefinido."""
        r = association(10, 0, 0, 10)
        self.assertTrue(all(x == x for x in r.odds_ratio_ci))  # nao e' NaN
        self.assertGreater(r.odds_ratio, 1.0)

    def test_low_support_flagged(self):
        self.assertTrue(association(3, 10, 5, 100, min_support=10).low_support)
        self.assertFalse(association(30, 10, 5, 100, min_support=10).low_support)

    def test_interpretation_never_claims_causality(self):
        r = association(60, 40, 10, 90)
        r.q_value = 0.001
        text = r.interpretation_allowed().lower()
        self.assertIn("nao implica causalidade", text)

    def test_small_effect_is_flagged_as_weakly_actionable(self):
        r = association(52, 48, 50, 50)
        r.q_value = 0.01
        self.assertIn("efeito", r.interpretation_allowed().lower())


class TestBenjaminiHochberg(unittest.TestCase):
    def test_preserves_input_order(self):
        q = benjamini_hochberg([0.04, 0.01, 0.03])
        self.assertEqual(len(q), 3)
        self.assertLessEqual(q[1], q[2])

    def test_monotone_and_bounded(self):
        ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
        q = benjamini_hochberg(ps)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in q))
        ordered = [q[i] for i in sorted(range(len(ps)), key=lambda i: ps[i])]
        self.assertEqual(ordered, sorted(ordered))

    def test_single_pvalue_unchanged(self):
        self.assertAlmostEqual(benjamini_hochberg([0.03])[0], 0.03)

    def test_empty(self):
        self.assertEqual(benjamini_hochberg([]), [])

    def test_correction_raises_q_above_p(self):
        ps = [0.02] * 10
        q = benjamini_hochberg(ps)
        self.assertTrue(all(x > 0.02 - 1e-12 for x in q))
