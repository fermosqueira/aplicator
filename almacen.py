"""Registro de postulaciones en SQLite. Es lo que permite saber, meses despues, quien escribio."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUTA_DB = BASE / "postulaciones.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS postulaciones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    enviada_en  TEXT    NOT NULL,
    email       TEXT    NOT NULL,
    recruiter   TEXT    NOT NULL DEFAULT '',
    empresa     TEXT    NOT NULL DEFAULT '',
    puesto      TEXT    NOT NULL DEFAULT '',
    idioma      TEXT    NOT NULL DEFAULT 'es',
    asunto      TEXT    NOT NULL DEFAULT '',
    marca       TEXT    NOT NULL DEFAULT '',
    etiqueta    TEXT    NOT NULL DEFAULT '',
    etiquetada  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_email ON postulaciones (email);
"""


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(ruta or RUTA_DB)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


@contextmanager
def sesion(ruta: Path | None = None):
    """Conexion que se cierra sola.

    Ojo: `with sqlite3.connect(...)` NO cierra la conexion, solo maneja la transaccion.
    Como el servidor abre una por pedido, sin esto se irian acumulando.
    """
    con = conectar(ruta)
    try:
        yield con
    finally:
        con.close()


def guardar(con: sqlite3.Connection, **datos) -> int:
    """Deja constancia del envio. Devuelve el id de la fila."""
    campos = {
        "enviada_en": datetime.now().isoformat(timespec="seconds"),
        "email": "", "recruiter": "", "empresa": "", "puesto": "",
        "idioma": "es", "asunto": "", "marca": "", "etiqueta": "", "etiquetada": 0,
    }
    campos.update(datos)
    campos["email"] = campos["email"].strip().lower()

    columnas = ", ".join(campos)
    huecos = ", ".join("?" * len(campos))
    cur = con.execute(
        f"INSERT INTO postulaciones ({columnas}) VALUES ({huecos})", list(campos.values())
    )
    con.commit()
    return cur.lastrowid


def marcar_etiquetada(con: sqlite3.Connection, id_fila: int, ok: bool) -> None:
    con.execute("UPDATE postulaciones SET etiquetada = ? WHERE id = ?", (int(ok), id_fila))
    con.commit()


def buscar_por_email(con: sqlite3.Connection, email: str) -> list[sqlite3.Row]:
    """Todas las postulaciones enviadas a esa direccion, de la mas nueva a la mas vieja."""
    return con.execute(
        "SELECT * FROM postulaciones WHERE email = ? ORDER BY enviada_en DESC",
        (email.strip().lower(),),
    ).fetchall()


def listar(con: sqlite3.Connection, limite: int = 50) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM postulaciones ORDER BY enviada_en DESC LIMIT ?", (limite,)
    ).fetchall()
