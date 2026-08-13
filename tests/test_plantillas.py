"""Deteccion de idioma, puesto y empresa, y armado del mail."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comun import armar_config

import plantillas


class DeteccionDeIdioma(unittest.TestCase):
    def test_aviso_en_espanol(self):
        texto = "Buscamos un analista con experiencia en pruebas para sumarse al equipo"
        self.assertEqual(plantillas.detectar_idioma(texto), "es")

    def test_aviso_en_ingles(self):
        texto = "We are looking for a tester to join our team with experience in the role"
        self.assertEqual(plantillas.detectar_idioma(texto), "en")

    def test_sin_texto_cae_a_espanol(self):
        # Es el idioma mas probable en su feed; ante la duda, no arriesgamos ingles.
        self.assertEqual(plantillas.detectar_idioma(""), "es")
        self.assertEqual(plantillas.detectar_idioma(None), "es")

    def test_los_acentos_no_estorban(self):
        self.assertEqual(plantillas.detectar_idioma("Búsqueda de QA para más de un puesto"), "es")


class DeteccionDePuesto(unittest.TestCase):
    def test_gana_el_titulo_mas_especifico(self):
        # "QA Automation Engineer" contiene "QA": el orden de la lista tiene que ganar.
        texto = "Buscamos QA Automation Engineer semi senior"
        self.assertEqual(plantillas.detectar_puesto(texto), "QA Automation Engineer")

    def test_reconoce_variantes(self):
        casos = {
            "Se busca Analista QA para fintech": "Analista QA",
            "Hiring a Manual Tester": "Manual Tester",
            "Vacante SDET": "SDET",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(plantillas.detectar_puesto(texto), esperado)

    def test_sin_coincidencia_devuelve_vacio(self):
        self.assertEqual(plantillas.detectar_puesto("Buscamos un cocinero"), "")


class DeteccionDeEmpresa(unittest.TestCase):
    def test_saca_el_nombre_del_dominio(self):
        self.assertEqual(plantillas.detectar_empresa("rrhh@acme.com"), "Acme")

    def test_los_guiones_se_vuelven_espacios(self):
        self.assertEqual(plantillas.detectar_empresa("jobs@acme-corp.com"), "Acme Corp")

    def test_ignora_dominios_genericos(self):
        # Un @gmail no dice nada de la empresa: mejor vacio que un "Gmail" al mail.
        for email in ("ana@gmail.com", "juan@hotmail.com", "x@outlook.com"):
            with self.subTest(email=email):
                self.assertEqual(plantillas.detectar_empresa(email), "")

    def test_entrada_invalida(self):
        self.assertEqual(plantillas.detectar_empresa("no-es-un-mail"), "")
        self.assertEqual(plantillas.detectar_empresa(""), "")


class Etiquetas(unittest.TestCase):
    def setUp(self):
        self.cfg = {"etiqueta_padre": "Postulaciones"}

    def test_cuelga_de_la_etiqueta_padre(self):
        self.assertEqual(plantillas.etiqueta(self.cfg, "Acme"), "Postulaciones/Acme")

    def test_saca_acentos(self):
        # IMAP sufre con UTF-8 en nombres de carpeta; el cuerpo del mail si los conserva.
        self.assertEqual(
            plantillas.etiqueta(self.cfg, "Telefónica"), "Postulaciones/Telefonica"
        )

    def test_saca_barras_para_no_anidar_de_mas(self):
        # Una barra en el nombre crearia una subetiqueta no deseada.
        self.assertNotIn("/", plantillas.etiqueta(self.cfg, "A/B").split("/", 1)[1])

    def test_empresa_vacia_no_deja_la_etiqueta_colgada(self):
        self.assertEqual(plantillas.etiqueta(self.cfg, ""), "Postulaciones/Sin empresa")


class ArmadoDelMail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = armar_config(Path(self.tmp.name))

    def test_completa_todos_los_huecos(self):
        asunto, cuerpo = plantillas.armar(self.cfg, "es", "Ana", "Acme", "QA Automation")
        self.assertEqual(asunto, "Postulación QA Automation - Nombre Apellido")
        self.assertIn("Hola Ana!", cuerpo)
        self.assertIn("QA Automation", cuerpo)
        self.assertIn("Acme", cuerpo)

    def test_nunca_queda_un_placeholder_sin_reemplazar(self):
        # Un "{empresa}" crudo llegando a un recruiter seria bochornoso.
        for idioma in ("es", "en"):
            for datos in (("", "", ""), ("Ana", "Acme", "QA")):
                with self.subTest(idioma=idioma, datos=datos):
                    _, cuerpo = plantillas.armar(self.cfg, idioma, *datos)
                    self.assertNotIn("{", cuerpo)
                    self.assertNotIn("}", cuerpo)

    def test_sin_recruiter_el_saludo_no_queda_cojo(self):
        _, cuerpo = plantillas.armar(self.cfg, "es", "", "Acme", "QA")
        self.assertIn("Hola!", cuerpo)
        self.assertNotIn("Hola !", cuerpo)

    def test_valores_de_reserva(self):
        _, cuerpo = plantillas.armar(self.cfg, "es", "Ana", "", "")
        self.assertIn("QA", cuerpo)
        self.assertIn("la empresa", cuerpo)

    def test_el_portfolio_va_en_el_idioma_del_mail(self):
        _, es = plantillas.armar(self.cfg, "es", "", "Acme", "QA")
        _, en = plantillas.armar(self.cfg, "en", "", "Acme", "QA")
        self.assertIn("https://ejemplo.test/es", es)
        self.assertNotIn("/en", es)
        self.assertIn("https://ejemplo.test/en", en)

    def test_la_firma_va_siempre(self):
        _, cuerpo = plantillas.armar(self.cfg, "es", "Ana", "Acme", "QA")
        self.assertIn("Nombre Apellido · QA Analyst", cuerpo)
        self.assertIn("linkedin.com/in/ejemplo", cuerpo)

    def test_idioma_desconocido_falla_temprano(self):
        with self.assertRaises(ValueError):
            plantillas.armar(self.cfg, "fr", "", "", "")

    def test_cv_por_idioma(self):
        self.assertEqual(plantillas.ruta_cv(self.cfg, "es").name, "cv-es.pdf")
        self.assertEqual(plantillas.ruta_cv(self.cfg, "en").name, "cv-en.pdf")

    def test_cv_faltante_avisa_con_claridad(self):
        self.cfg["idiomas"]["es"]["cv"] = "no-existe.pdf"
        with self.assertRaises(FileNotFoundError):
            plantillas.ruta_cv(self.cfg, "es")


if __name__ == "__main__":
    unittest.main()
