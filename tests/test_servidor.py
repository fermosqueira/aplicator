"""El servidor local y sus dos defensas.

IMPORTANTE: ninguna prueba llama a /enviar ni a /respuestas con un token valido. La primera
manda un mail de verdad; la segunda lee la configuracion real y le escribe etiquetas a la
casilla. De las dos solo se prueba que rechacen a quien no corresponde.
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from comun import armar_config

import servidor


class ServidorLevantado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = armar_config(Path(cls.tmp.name))
        cls.servidor = servidor.crear_servidor(
            cls.cfg, puerto=0, ruta_db=Path(cls.tmp.name) / "test.db"
        )
        cls.puerto = cls.servidor.server_address[1]
        # El servidor loguea cada pedido; util al usarlo, ruido al testear.
        cls.servidor.RequestHandlerClass.log_message = lambda *a, **k: None
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.hilo.join(timeout=5)
        cls.tmp.cleanup()

    def pedir(self, ruta, datos=None, token="token-de-prueba",
              origen="https://www.linkedin.com", metodo=None):
        url = f"http://127.0.0.1:{self.puerto}{ruta}"
        cuerpo = json.dumps(datos).encode() if datos is not None else None
        req = urllib.request.Request(url, data=cuerpo, method=metodo)
        req.add_header("Content-Type", "application/json")
        if token is not None:
            req.add_header("X-Aplicador-Token", token)
        if origen is not None:
            req.add_header("Origin", origen)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                crudo = e.read().decode()
                try:
                    return e.code, json.loads(crudo)
                except json.JSONDecodeError:
                    return e.code, crudo
            finally:
                e.close()  # sin esto quedan ResourceWarning ensuciando la salida


class Seguridad(ServidorLevantado):
    """Sin estas dos defensas, cualquier pagina que visite el usuario podria hacerle
    mandar mails desde su propia cuenta."""

    def test_sin_token_no_pasa(self):
        codigo, cuerpo = self.pedir("/sugerir", {"email": "a@x.com"}, token=None)
        self.assertEqual(codigo, 403)
        self.assertFalse(cuerpo["ok"])

    def test_token_equivocado_no_pasa(self):
        codigo, _ = self.pedir("/sugerir", {"email": "a@x.com"}, token="otro")
        self.assertEqual(codigo, 403)

    def test_origen_ajeno_no_pasa(self):
        codigo, cuerpo = self.pedir(
            "/sugerir", {"email": "a@x.com"}, origen="https://sitio-cualquiera.com"
        )
        self.assertEqual(codigo, 403)
        self.assertEqual(cuerpo["error"], "origen no permitido")

    def test_enviar_tambien_esta_protegido(self):
        # La ruta peligrosa se rechaza antes de mirar el cuerpo del pedido.
        codigo, _ = self.pedir("/enviar", {"email": "a@x.com"}, token=None)
        self.assertEqual(codigo, 403)

    def test_respuestas_tambien_esta_protegido(self):
        # Toca la casilla real: se verifica el rechazo, nunca el camino feliz.
        self.assertEqual(self.pedir("/respuestas", {}, token=None)[0], 403)
        self.assertEqual(
            self.pedir("/respuestas", {}, origen="https://malicioso.com")[0], 403
        )

    def test_buscar_tambien_esta_protegido(self):
        # El historial tiene datos de recruiters: no puede quedar abierto.
        self.assertEqual(self.pedir("/buscar", {"q": ""}, token=None)[0], 403)

    def test_la_extension_si_pasa(self):
        codigo, _ = self.pedir(
            "/sugerir", {"email": "a@x.com"}, origen="chrome-extension://loquesea"
        )
        self.assertEqual(codigo, 200)

    def test_sin_origen_pasa_con_token(self):
        # Un pedido sin Origin no puede venir de una pagina: los navegadores siempre lo
        # mandan en un POST cross-origin. Es la CLI o un test, y ahi el token alcanza.
        codigo, _ = self.pedir("/sugerir", {"email": "a@x.com"}, origen=None)
        self.assertEqual(codigo, 200)

    def test_el_preflight_rechaza_origenes_ajenos(self):
        codigo, _ = self.pedir("/sugerir", metodo="OPTIONS", origen="https://malicioso.com")
        self.assertEqual(codigo, 403)


class Rutas(ServidorLevantado):
    def test_ping(self):
        codigo, cuerpo = self.pedir("/ping", metodo="GET")
        self.assertEqual(codigo, 200)
        self.assertTrue(cuerpo["ok"])

    def test_ruta_inexistente(self):
        codigo, _ = self.pedir("/no-existe", {})
        self.assertEqual(codigo, 404)

    def test_el_panel_se_sirve_y_trae_el_token_adentro(self):
        # La pagina la servimos nosotros, asi que sus pedidos son same-origin y el token
        # puede viajar embebido sin exponerlo a nadie mas.
        url = f"http://127.0.0.1:{self.puerto}/historial"
        with urllib.request.urlopen(url, timeout=10) as r:
            html = r.read().decode()
            self.assertEqual(r.status, 200)
            self.assertIn("text/html", r.headers["Content-Type"])
        self.assertIn("token-de-prueba", html)
        self.assertIn("Postulaciones", html)
        self.assertNotIn("__TOKEN__", html)  # el placeholder tiene que haberse reemplazado

    def test_buscar_devuelve_las_filas(self):
        codigo, cuerpo = self.pedir("/buscar", {"q": ""})
        self.assertEqual(codigo, 200)
        self.assertTrue(cuerpo["ok"])
        self.assertIsInstance(cuerpo["filas"], list)

    def test_el_panel_es_same_origin(self):
        # Un pedido con el Origin del propio servidor tiene que pasar: es el del panel.
        codigo, _ = self.pedir(
            "/buscar", {"q": ""}, origen=f"http://127.0.0.1:{self.puerto}"
        )
        self.assertEqual(codigo, 200)

    def test_sugerir_devuelve_las_tres_pistas(self):
        codigo, cuerpo = self.pedir("/sugerir", {
            "email": "rrhh@acme.com",
            "texto": "Buscamos QA Automation con experiencia en pruebas para el equipo",
        })
        self.assertEqual(codigo, 200)
        self.assertEqual(cuerpo["empresa"], "Acme")
        self.assertEqual(cuerpo["puesto"], "QA Automation")
        self.assertEqual(cuerpo["idioma"], "es")
        self.assertEqual(cuerpo["duplicados"], [])

    def test_previsualizar_arma_el_mail_sin_enviarlo(self):
        codigo, cuerpo = self.pedir("/previsualizar", {
            "email": "rrhh@acme.com", "empresa": "Acme",
            "puesto": "QA Engineer", "recruiter": "Ana", "idioma": "en",
        })
        self.assertEqual(codigo, 200)
        self.assertEqual(cuerpo["asunto"], "Application for QA Engineer - Nombre Apellido")
        self.assertEqual(cuerpo["etiqueta"], "Postulaciones/Acme")
        self.assertIn("Hi Ana!", cuerpo["cuerpo"])
        self.assertNotIn("{", cuerpo["cuerpo"])

    def test_idioma_invalido_cae_a_espanol(self):
        _, cuerpo = self.pedir("/previsualizar", {"email": "a@x.com", "idioma": "klingon"})
        self.assertIn("Postulación", cuerpo["asunto"])

    def test_mail_invalido_da_error_de_pedido_no_de_servidor(self):
        codigo, cuerpo = self.pedir("/previsualizar", {"email": "esto-no-es-un-mail"})
        # previsualizar tolera cualquier texto; el rechazo duro es al enviar.
        self.assertIn(codigo, (200, 400))
        if codigo == 400:
            self.assertFalse(cuerpo["ok"])


if __name__ == "__main__":
    unittest.main()
