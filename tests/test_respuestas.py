"""El detector de respuestas, contra un buzon de mentira.

Nada de esto toca Gmail. La logica de emparejar respuestas con postulaciones vive en
nucleo.py y habla contra la interfaz de correo.Buzon, asi que se puede probar entera con
un doble — que es la razon por la que esa clase existe.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comun import armar_config

import almacen
import nucleo


class BuzonFalso:
    """Imita a correo.Buzon. Registra lo que le piden para poder verificarlo despues."""

    def __init__(self, mensajes: dict[str, list[dict]]):
        # {hilo o mail: [{"from": ..., "date": ...}, ...]}
        self.mensajes = mensajes
        self.copiados = []      # (uid, etiqueta) de lo que se etiqueto
        self.etiquetas_creadas = []
        self.carpeta_abierta = None

    def carpeta_todos(self):
        return '"[Gmail]/All Mail"'

    def abrir(self, carpeta):
        self.carpeta_abierta = carpeta
        return True

    def crear_etiqueta(self, etiqueta):
        self.etiquetas_creadas.append(etiqueta)

    def uids_del_hilo(self, hilo):
        return [f"{hilo}:{i}".encode() for i in range(len(self.mensajes.get(hilo, [])))]

    def uids_de(self, remitente, desde):
        return [f"{remitente}:{i}".encode() for i in range(len(self.mensajes.get(remitente, [])))]

    def cabeceras(self, uid):
        clave, indice = uid.decode().rsplit(":", 1)
        return self.mensajes[clave][int(indice)]

    def copiar(self, uid, etiqueta):
        self.copiados.append((uid.decode(), etiqueta))
        return True


class Deteccion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = armar_config(Path(self.tmp.name))
        self.con = almacen.conectar(Path(self.tmp.name) / "r.db")
        self.addCleanup(self.con.close)

    def postular(self, **datos):
        base = {
            "email": "rrhh@acme.com", "empresa": "Acme", "puesto": "QA",
            "etiqueta": "Postulaciones/Acme", "enviada_en": "2026-08-01T10:00:00",
        }
        base.update(datos)
        return almacen.guardar(self.con, **base)

    def test_encuentra_la_respuesta_por_hilo(self):
        id_fila = self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "Nombre Apellido <prueba@ejemplo.com>", "date": "Fri, 1 Aug 2026 10:00:00 -0300"},
            {"from": "Ana <rrhh@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)
        self.assertEqual(resultado["nuevas"][0]["empresa"], "Acme")
        fila = almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]
        self.assertEqual(fila["respondida"], 1)
        self.assertTrue(fila["respondida_en"].startswith("2026-08-04"))
        self.assertEqual(id_fila, resultado["nuevas"][0]["id"])

    def test_ignora_los_mensajes_propios(self):
        # El hilo siempre contiene el mail que enviamos: no puede contar como respuesta.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "Nombre Apellido <prueba@ejemplo.com>", "date": "Fri, 1 Aug 2026 10:00:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(resultado["nuevas"], [])
        self.assertEqual(almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]["respondida"], 0)

    def test_etiqueta_el_mensaje_de_respuesta(self):
        # Es lo que hace que el dato se vea en la bandeja sin depender de como Gmail
        # agrupe las conversaciones.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "Ana <rrhh@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(buzon.copiados, [("123:0", "Postulaciones/Acme")])
        self.assertIn("Postulaciones/Acme", buzon.etiquetas_creadas)

    def test_responde_otra_persona_de_la_empresa(self):
        # Contesta alguien distinto del destinatario original: buscar por hilo lo encuentra
        # igual, y por eso el hilo es mejor criterio que el remitente.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "Otro <otro@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)
        self.assertIn("otro@acme.com", resultado["nuevas"][0]["de"])

    def test_sin_hilo_cae_a_buscar_por_remitente(self):
        self.postular(hilo="")
        buzon = BuzonFalso({"rrhh@acme.com": [
            {"from": "Ana <rrhh@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)

    def test_no_revisa_las_que_ya_estaban_respondidas(self):
        id_fila = self.postular(hilo="123")
        almacen.marcar_respondida(self.con, id_fila)
        buzon = BuzonFalso({"123": [
            {"from": "Ana <rrhh@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(resultado["revisadas"], 0)
        self.assertEqual(buzon.copiados, [])

    def test_sin_pendientes_no_toca_el_buzon(self):
        resultado = nucleo.detectar_respuestas(self.cfg, self.con, BuzonFalso({}))
        self.assertEqual(resultado["revisadas"], 0)
        self.assertEqual(resultado["nuevas"], [])

    def test_una_fecha_ilegible_no_pierde_la_respuesta(self):
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [{"from": "Ana <rrhh@acme.com>", "date": "no es una fecha"}]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)
        self.assertEqual(almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]["respondida"], 1)


if __name__ == "__main__":
    unittest.main()
