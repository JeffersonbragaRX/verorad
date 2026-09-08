"""Conexao com o banco local (mesma laudocore.db usada pelos scripts).

Uma conexao nova por request (SQLite lida bem com multiplos leitores;
o unico escritor concorrente esperado e a acao de resolver um item da
fila de revisao, que e rara e de usuario unico)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "processed" / "laudocore.db"


def get_connection() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"{DB_PATH} não existe. Rode scripts/ingest_vertical.py e "
            "scripts/extract_concepts.py antes de iniciar a API."
        )
    # check_same_thread=False: FastAPI roda dependencias sync (como esta)
    # em uma threadpool, e o setup/teardown de um generator-dependency
    # pode ser despachado em threads diferentes entre si (bug real
    # encontrado testando a UI: 'SQLite objects created in a thread can
    # only be used in that same thread' ao fechar a conexao). Seguro aqui
    # porque cada request tem sua PROPRIA conexao, nunca compartilhada
    # entre requests/threads simultaneamente.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
