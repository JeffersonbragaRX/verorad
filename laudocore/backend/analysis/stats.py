"""Estatistica de associacao — stdlib puro (sem scipy no ambiente).

Implementa o minimo exigido pela secao 10 do PROMPT MESTRE V2:
Fisher exato bicaudal, razao de chances e razao de prevalencias com
intervalo de confianca, lift, e correcao de multiplas comparacoes por
Benjamini-Hochberg (FDR).

Decisao explicita: p-valor NUNCA e' reportado sozinho. Toda associacao
sai com tamanho de efeito, intervalo de confianca, denominador e n —
porque um p pequeno num corpus de 8.402 laudos diz quase nada sobre
relevancia clinica, e a especificacao proibe apresentar associacao sem
tamanho de efeito e limitacao.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Correcao de Haldane-Anscombe: soma 0,5 a todas as celulas quando
# alguma e' zero. Sem isso, razao de chances com celula zero e'
# infinita/indefinida e o IC nao existe.
_HALDANE = 0.5


def _log_binom(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Fisher exato bicaudal para a tabela 2x2:

            B presente   B ausente
        A+      a            b
        A-      c            d

    Soma a probabilidade hipergeometrica de todas as tabelas com as
    mesmas marginais cuja probabilidade nao excede a da observada."""
    n = a + b + c + d
    if n == 0:
        return 1.0
    row1, col1 = a + b, a + c
    log_denom = _log_binom(n, col1)

    def log_p(x: int) -> float:
        return _log_binom(row1, x) + _log_binom(n - row1, col1 - x) - log_denom

    p_obs = log_p(a)
    lo = max(0, col1 - (n - row1))
    hi = min(row1, col1)
    total = 0.0
    # tolerancia relativa para comparar probabilidades em log
    for x in range(lo, hi + 1):
        lp = log_p(x)
        if lp <= p_obs + 1e-9:
            total += math.exp(lp)
    return min(1.0, total)


@dataclass
class AssociationResult:
    a: int              # A+ e B+
    b: int              # A+ e B-
    c: int              # A- e B+
    d: int              # A- e B-
    support: int        # = a
    eligible_denominator: int   # n total elegivel
    p_b_given_a: float
    p_b_without_a: float
    absolute_difference: float
    prevalence_ratio: float
    prevalence_ratio_ci: tuple[float, float]
    odds_ratio: float
    odds_ratio_ci: tuple[float, float]
    lift: float
    p_value: float
    q_value: float | None = None      # preenchido apos correcao FDR
    low_support: bool = False

    @property
    def p_a_given_b(self) -> float:
        return self.a / (self.a + self.c) if (self.a + self.c) else 0.0

    @property
    def mutually_locked(self) -> bool:
        """A e B praticamente NUNCA aparecem um sem o outro nos dois
        sentidos. Isso nao e' associacao clinica: e' bloco de texto fixo
        (legenda, tabela de referencia) ou estrutura do laudo (um exame
        que descreve varios vasos/niveis sempre cita todos os graus).
        A especificacao exige separar isso de associacao entre achados
        (secao 10, controle de vieses)."""
        return (self.a >= 20 and self.p_b_given_a >= 0.98
                and self.p_a_given_b >= 0.98)

    def interpretation_allowed(self) -> str:
        """O que se pode DIZER a partir deste numero. Deliberadamente
        conservador: o corpus mostra coocorrencia documentada, nunca
        causalidade nem conduta."""
        if self.mutually_locked:
            return ("artefato estrutural/template — os dois termos sempre "
                     "aparecem juntos, nao ha' informacao discriminante; "
                     "NAO interpretar como associacao clinica")
        if self.low_support:
            return ("suporte insuficiente — descrever, nao generalizar")
        if self.q_value is not None and self.q_value > 0.05:
            return ("nao distinguivel de acaso apos correcao de multiplas "
                     "comparacoes — nao interpretar")
        if abs(self.absolute_difference) < 0.05:
            return ("associacao estatisticamente detectavel mas de efeito "
                     "pequeno neste corpus — pouco acionavel")
        return ("coocorrencia documentada neste corpus; NAO implica causalidade "
                 "nem conduta — requer validacao clinica")


def association(a: int, b: int, c: int, d: int,
                 min_support: int = 10) -> AssociationResult:
    """Calcula a associacao entre A e B a partir da tabela 2x2."""
    n = a + b + c + d
    n_a = a + b
    n_not_a = c + d

    p_b_given_a = a / n_a if n_a else 0.0
    p_b_without_a = c / n_not_a if n_not_a else 0.0

    aa, bb, cc, dd = a, b, c, d
    if min(a, b, c, d) == 0:
        aa, bb, cc, dd = a + _HALDANE, b + _HALDANE, c + _HALDANE, d + _HALDANE

    # razao de prevalencias (risco relativo) + IC log
    p1 = aa / (aa + bb)
    p0 = cc / (cc + dd)
    pr = p1 / p0 if p0 else float("inf")
    if p0 and p1:
        se_log_pr = math.sqrt(bb / (aa * (aa + bb)) + dd / (cc * (cc + dd)))
        pr_ci = (math.exp(math.log(pr) - 1.96 * se_log_pr),
                  math.exp(math.log(pr) + 1.96 * se_log_pr))
    else:
        pr_ci = (float("nan"), float("nan"))

    # razao de chances + IC de Woolf
    orv = (aa * dd) / (bb * cc) if bb and cc else float("inf")
    se_log_or = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    or_ci = (math.exp(math.log(orv) - 1.96 * se_log_or),
              math.exp(math.log(orv) + 1.96 * se_log_or))

    p_b_overall = (a + c) / n if n else 0.0
    lift = (p_b_given_a / p_b_overall) if p_b_overall else float("nan")

    return AssociationResult(
        a=a, b=b, c=c, d=d, support=a, eligible_denominator=n,
        p_b_given_a=p_b_given_a, p_b_without_a=p_b_without_a,
        absolute_difference=p_b_given_a - p_b_without_a,
        prevalence_ratio=pr, prevalence_ratio_ci=pr_ci,
        odds_ratio=orv, odds_ratio_ci=or_ci, lift=lift,
        p_value=fisher_exact_two_sided(a, b, c, d),
        low_support=(a < min_support),
    )


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """q-valores (FDR) de Benjamini-Hochberg, preservando a ordem de
    entrada. Obrigatorio aqui: sao milhares de pares testados, e sem
    correcao ~5% deles pareceriam 'significativos' so por acaso."""
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(enumerate(p_values), key=lambda kv: kv[1])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        idx, p = indexed[rank - 1]
        value = min(prev, p * m / rank)
        q[idx] = value
        prev = value
    return q
