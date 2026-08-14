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
import correo
import nucleo


class Rebotes(unittest.TestCase):
    """Quien escribio el mensaje: una persona o un servidor avisando que algo fallo."""

    def test_reconoce_los_avisos_de_sistema(self):
        for de in (
            "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
            "MAILER-DAEMON@acme.com",
            "postmaster@outlook.com",
        ):
            with self.subTest(de=de):
                self.assertTrue(correo.es_rebote(de))

    def test_no_confunde_a_una_persona_con_un_rebote(self):
        # El falso positivo es el error caro: daria por perdida una postulacion que si llego.
        for de in (
            "Ana <ana@acme.com>",
            "Contacto Pepiln <contacto@pepiln.com>",
            "no-reply@recluit.com",          # automatico, pero es una respuesta de verdad
            "daniel.mailer@acme.com",        # el apellido no lo convierte en un daemon
        ):
            with self.subTest(de=de):
                self.assertFalse(correo.es_rebote(de))

    def test_entrada_vacia(self):
        self.assertFalse(correo.es_rebote(""))
        self.assertFalse(correo.es_rebote(None))


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
        # Importa mas ahora que antes: esto corre solo cada media hora, y no tiene sentido
        # loguearse a Gmail para descubrir que no habia trabajo.
        buzon = BuzonFalso({})
        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)
        self.assertEqual(resultado["revisadas"], 0)
        self.assertEqual(resultado["nuevas"], [])
        self.assertIsNone(buzon.carpeta_abierta)

    def test_un_rebote_no_es_una_respuesta(self):
        # Caso real: la postulacion a "@gmail.co" (sin la m) reboto, y el mailer-daemon
        # contesta por el mismo hilo desde una direccion ajena. Sin distinguirlo, la
        # postulacion figuraba como contestada cuando en realidad nunca llego a nadie.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "Nombre Apellido <prueba@ejemplo.com>", "date": "Fri, 1 Aug 2026 10:00:00 -0300"},
            {"from": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
             "date": "Fri, 1 Aug 2026 10:00:12 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(resultado["nuevas"], [])
        self.assertEqual(len(resultado["rebotes"]), 1)
        fila = almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]
        self.assertEqual(fila["respondida"], 0)
        self.assertEqual(fila["rebotada"], 1)
        self.assertTrue(fila["rebotada_en"].startswith("2026-08-01"))

    def test_el_rebote_igual_se_etiqueta(self):
        # Es justo el mensaje que uno quiere encontrar despues en la bandeja.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "mailer-daemon@googlemail.com", "date": "Fri, 1 Aug 2026 10:00:12 -0300"},
        ]})

        nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(buzon.copiados, [("123:0", "Postulaciones/Acme")])

    def test_si_hay_rebote_y_respuesta_manda_la_respuesta(self):
        # El rebote viene primero en el hilo. Cortar en el primer mensaje ajeno daria
        # "rebotada" a una postulacion que si fue contestada.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "postmaster@acme.com", "date": "Fri, 1 Aug 2026 10:00:12 -0300"},
            {"from": "Ana <rrhh@acme.com>", "date": "Mon, 4 Aug 2026 09:30:00 -0300"},
        ]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)
        self.assertEqual(resultado["rebotes"], [])
        fila = almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]
        self.assertEqual(fila["respondida"], 1)
        self.assertEqual(fila["rebotada"], 0)

    def test_una_rebotada_no_se_revisa_de_nuevo(self):
        # Si siguiera en la lista de pendientes, cada media hora volveria a etiquetar el
        # mismo rebote, para siempre.
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [
            {"from": "mailer-daemon@googlemail.com", "date": "Fri, 1 Aug 2026 10:00:12 -0300"},
        ]})
        nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        segunda = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(segunda["revisadas"], 0)
        self.assertEqual(len(buzon.copiados), 1)

    def test_una_fecha_ilegible_no_pierde_la_respuesta(self):
        self.postular(hilo="123")
        buzon = BuzonFalso({"123": [{"from": "Ana <rrhh@acme.com>", "date": "no es una fecha"}]})

        resultado = nucleo.detectar_respuestas(self.cfg, self.con, buzon)

        self.assertEqual(len(resultado["nuevas"]), 1)
        self.assertEqual(almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]["respondida"], 1)


if __name__ == "__main__":
    unittest.main()
