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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
