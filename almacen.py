"""Registro de postulaciones en SQLite.

Guarda el post entero, no solo la empresa y el puesto: dentro de un mes, "QA Automation en
Trustpeople" no alcanza para recordar de que oferta se trataba. El detalle real —el cliente,
el stack, la modalidad— estaba en la publicacion.
"""

from __future__ import annotations

import sqlite3
import unicodedata
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

# Columnas agregadas despues de la primera version. Se aplican sobre bases existentes con
# ALTER TABLE, que en SQLite conserva las filas: nadie pierde su historial por actualizar.
COLUMNAS_NUEVAS = {
    "texto_post": "TEXT NOT NULL DEFAULT ''",
    "url_post": "TEXT NOT NULL DEFAULT ''",
    "autor_post": "TEXT NOT NULL DEFAULT ''",
    "hilo": "TEXT NOT NULL DEFAULT ''",
    "respondida": "INTEGER NOT NULL DEFAULT 0",
    "respondida_en": "TEXT NOT NULL DEFAULT ''",
}

# Donde busca el buscador del panel. El texto del post es la razon de ser de todo esto:
# permite encontrar una postulacion por una palabra que solo estaba en la publicacion.
CAMPOS_BUSCABLES = (
    "email", "empresa", "puesto", "recruiter", "autor_post", "asunto", "texto_post",
)


def _migrar(con: sqlite3.Connection) -> list[str]:
    """Agrega las columnas que falten. Devuelve cuales agrego, para poder loguearlo."""
    existentes = {fila[1] for fila in con.execute("PRAGMA table_info(postulaciones)")}
    agregadas = []
    for columna, tipo in COLUMNAS_NUEVAS.items():
        if columna not in existentes:
            con.execute(f"ALTER TABLE postulaciones ADD COLUMN {columna} {tipo}")
            agregadas.append(columna)
    if agregadas:
        con.commit()
    return agregadas


def conectar(ruta: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(ruta or RUTA_DB)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    _migrar(con)
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
        "texto_post": "", "url_post": "", "autor_post": "", "hilo": "",
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


def guardar_hilo(con: sqlite3.Connection, id_fila: int, hilo: str) -> None:
    """El id de conversacion de Gmail. Es con lo que despues se encuentra la respuesta."""
    con.execute("UPDATE postulaciones SET hilo = ? WHERE id = ?", (hilo or "", id_fila))
    con.commit()


def marcar_respondida(con: sqlite3.Connection, id_fila: int, cuando: str = "") -> None:
    con.execute(
        "UPDATE postulaciones SET respondida = 1, respondida_en = ? WHERE id = ?",
        (cuando or datetime.now().isoformat(timespec="seconds"), id_fila),
    )
    con.commit()


def buscar_por_email(con: sqlite3.Connection, email: str) -> list[sqlite3.Row]:
    """Todas las postulaciones enviadas a esa direccion, de la mas nueva a la mas vieja."""
    return con.execute(
        "SELECT * FROM postulaciones WHERE email = ? ORDER BY enviada_en DESC",
        (email.strip().lower(),),
    ).fetchall()


def _sin_acentos(texto: str) -> str:
    desarmado = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in desarmado if unicodedata.category(c) != "Mn")


def buscar(con: sqlite3.Connection, consulta: str = "", limite: int = 200) -> list[sqlite3.Row]:
    """Busca el texto en cualquier campo util, incluido el cuerpo del post.

    El filtrado de acentos se hace en Python y no en SQL: el LIKE de SQLite no los ignora,
    asi que buscar "postulacion" no encontraria "postulación". Con este volumen de filas
    traer todo y filtrar en memoria es de sobra.
    """
    filas = con.execute(
        "SELECT * FROM postulaciones ORDER BY enviada_en DESC LIMIT ?", (limite,)
    ).fetchall()

    consulta = _sin_acentos(consulta).lower().strip()
    if not consulta:
        return filas

    terminos = consulta.split()
    resultado = []
    for fila in filas:
        heno = _sin_acentos(" ".join(str(fila[c] or "") for c in CAMPOS_BUSCABLES)).lower()
        if all(termino in heno for termino in terminos):
            resultado.append(fila)
    return resultado


def sin_responder(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Las que todavia esperan respuesta: lo que recorre el detector."""
    return con.execute(
        "SELECT * FROM postulaciones WHERE respondida = 0 ORDER BY enviada_en DESC"
    ).fetchall()


def listar(con: sqlite3.Connection, limite: int = 50) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM postulaciones ORDER BY enviada_en DESC LIMIT ?", (limite,)
    ).fetchall()
