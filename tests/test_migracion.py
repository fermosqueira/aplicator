"""La migracion del esquema.

Es el test que mas importa de esta tanda: si falla, alguien pierde su historial de
postulaciones por el solo hecho de actualizar.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import comun  # noqa: F401  (agrega la raiz del proyecto al sys.path)

import almacen

# El esquema tal como era antes de guardar el post: sin texto_post, url_post, autor_post,
# hilo, respondida ni respondida_en.
ESQUEMA_VIEJO = """
CREATE TABLE postulaciones (
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
"""


# El esquema de la version siguiente: ya guardaba el post y el hilo, pero todavia trataba
# un rebote como si fuera una respuesta. Va escrito a mano y no derivado del actual: un
# test de migracion tiene que fijar como era el pasado, no seguirlo.
ESQUEMA_INTERMEDIO = """
CREATE TABLE postulaciones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    enviada_en    TEXT    NOT NULL,
    email         TEXT    NOT NULL,
    recruiter     TEXT    NOT NULL DEFAULT '',
    empresa       TEXT    NOT NULL DEFAULT '',
    puesto        TEXT    NOT NULL DEFAULT '',
    idioma        TEXT    NOT NULL DEFAULT 'es',
    asunto        TEXT    NOT NULL DEFAULT '',
    marca         TEXT    NOT NULL DEFAULT '',
    etiqueta      TEXT    NOT NULL DEFAULT '',
    etiquetada    INTEGER NOT NULL DEFAULT 0,
    texto_post    TEXT    NOT NULL DEFAULT '',
    url_post      TEXT    NOT NULL DEFAULT '',
    autor_post    TEXT    NOT NULL DEFAULT '',
    hilo          TEXT    NOT NULL DEFAULT '',
    respondida    INTEGER NOT NULL DEFAULT 0,
    respondida_en TEXT    NOT NULL DEFAULT ''
);
"""


class MigracionDesdeElEsquemaViejo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / "vieja.db"

        # Una base como la que ya tiene alguien usando la version anterior, con datos.
        vieja = sqlite3.connect(self.ruta)
        vieja.executescript(ESQUEMA_VIEJO)
        vieja.execute(
            "INSERT INTO postulaciones (enviada_en, email, empresa, puesto, etiquetada) "
            "VALUES ('2026-08-01T10:00:00', 'rrhh@acme.com', 'Acme', 'QA Manual', 1)"
        )
        vieja.commit()
        vieja.close()

    def test_agrega_las_columnas_nuevas(self):
        con = almacen.conectar(self.ruta)
        self.addCleanup(con.close)
        columnas = {f[1] for f in con.execute("PRAGMA table_info(postulaciones)")}
        for nueva in almacen.COLUMNAS_NUEVAS:
            self.assertIn(nueva, columnas)

    def test_no_pierde_las_filas_que_ya_estaban(self):
        con = almacen.conectar(self.ruta)
        self.addCleanup(con.close)
        filas = almacen.buscar_por_email(con, "rrhh@acme.com")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["empresa"], "Acme")
        self.assertEqual(filas[0]["puesto"], "QA Manual")
        self.assertEqual(filas[0]["etiquetada"], 1)

    def test_las_filas_viejas_quedan_con_valores_vacios_no_con_null(self):
        # Si quedaran en NULL, el buscador y el panel tendrian que andar esquivandolos.
        con = almacen.conectar(self.ruta)
        self.addCleanup(con.close)
        fila = almacen.buscar_por_email(con, "rrhh@acme.com")[0]
        self.assertEqual(fila["texto_post"], "")
        self.assertEqual(fila["hilo"], "")
        self.assertEqual(fila["respondida"], 0)

    def test_las_filas_viejas_quedan_como_postulacion_directa(self):
        # Todo lo enviado antes de que existiera el tipo fue una postulacion directa: ese
        # es el default correcto, no una eleccion arbitraria.
        con = almacen.conectar(self.ruta)
        self.addCleanup(con.close)
        self.assertEqual(almacen.buscar_por_email(con, "rrhh@acme.com")[0]["tipo"], "directa")

    def test_es_idempotente(self):
        # Conectarse mil veces no puede fallar ni duplicar columnas.
        for _ in range(3):
            con = almacen.conectar(self.ruta)
            con.close()
        con = almacen.conectar(self.ruta)
        self.addCleanup(con.close)
        columnas = [f[1] for f in con.execute("PRAGMA table_info(postulaciones)")]
        self.assertEqual(len(columnas), len(set(columnas)))

    def test_migra_desde_un_esquema_intermedio(self):
        # El caso real de esta actualizacion: una base que ya guardaba el post y el hilo
        # pero todavia no sabia distinguir un rebote. Las columnas se agregan de a una
        # segun falten, asi que se tiene que poder venir desde cualquier version.
        ruta = Path(self.tmp.name) / "intermedia.db"
        intermedia = sqlite3.connect(ruta)
        intermedia.executescript(ESQUEMA_INTERMEDIO)
        intermedia.execute(
            "INSERT INTO postulaciones (enviada_en, email, empresa, hilo, texto_post) "
            "VALUES ('2026-08-01T10:00:00', 'rrhh@acme.com', 'Acme', '123', 'Buscamos QA')"
        )
        intermedia.commit()
        intermedia.close()

        con = almacen.conectar(ruta)
        self.addCleanup(con.close)
        fila = almacen.buscar_por_email(con, "rrhh@acme.com")[0]
        self.assertEqual(fila["rebotada"], 0)
        self.assertEqual(fila["rebotada_en"], "")
        self.assertEqual(fila["hilo"], "123")          # lo que ya estaba sigue estando
        self.assertEqual(fila["texto_post"], "Buscamos QA")
        self.assertEqual(len(almacen.sin_responder(con)), 1)

    def test_una_base_nueva_ya_nace_completa(self):
        ruta = Path(self.tmp.name) / "nueva.db"
        con = almacen.conectar(ruta)
        self.addCleanup(con.close)
        columnas = {f[1] for f in con.execute("PRAGMA table_info(postulaciones)")}
        for nueva in almacen.COLUMNAS_NUEVAS:
            self.assertIn(nueva, columnas)


if __name__ == "__main__":
    unittest.main()
