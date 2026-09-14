"""Resolucao do caminho do banco — ponto unico.

Existe por causa de um bug real: a suite de testes rodava os scripts de
ingestao por subprocess contra o banco de PRODUCAO, reconstruindo o
schema e apagando a ingestao global (8.402 laudos viravam os 911 do
vertical de joelho), alem de deixar clinical_concepts_universal
orfao. Teste nao pode escrever no banco de producao.

Com LAUDOCORE_DB o chamador escolhe o destino; os testes apontam para
um arquivo temporario.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "processed" / "laudocore.db"


def db_path() -> Path:
    override = os.environ.get("LAUDOCORE_DB")
    return Path(override) if override else DEFAULT_DB


def derived_dir() -> Path:
    """Onde vao QA e artefatos. Segue o banco: com LAUDOCORE_DB
    apontando para um temporario, os derivados tambem vao para la.

    Sem isso o vazamento so mudava de lugar — o teste do vertical
    sobrescrevia o QA_REPORT_FASE1.json de producao com numeros do
    joelho, mesmo escrevendo o banco no lugar certo."""
    override = os.environ.get("LAUDOCORE_DB")
    if override:
        return Path(override).parent / "derived"
    return DEFAULT_DB.parents[1] / "derived"
