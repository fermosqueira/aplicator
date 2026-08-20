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

    def test_reconoce_al_proveedor_aunque_el_dominio_este_mal(self):
        # Caso real: un mail a "@gmail.co" quedo etiquetado como empresa "Gmail".
        # Se compara la primera etiqueta del dominio, no el dominio entero.
        for email in ("a@gmail.co", "a@gmail.com.ar", "a@googlemail.com", "a@yahoo.com.ar"):
            with self.subTest(email=email):
                self.assertEqual(plantillas.detectar_empresa(email), "")


class DominiosSospechosos(unittest.TestCase):
    """Un dominio mal escrito por una letra es invisible al revisar el borrador, el mail
    rebota y la postulacion se pierde sin que nadie se entere. Paso de verdad."""

    def test_detecta_el_caso_que_costo_una_postulacion(self):
        self.assertEqual(
            plantillas.dominio_sospechoso("stackotechsolutions.career@gmail.co"), "gmail.com"
        )

    def test_detecta_otras_variantes_de_una_letra(self):
        casos = {
            "a@gmial.com": "gmail.com",
            "a@hotmai.com": "hotmail.com",
            "a@outlok.com": "outlook.com",
            "a@yahooo.com": "yahoo.com",
        }
        for email, esperado in casos.items():
            with self.subTest(email=email):
                self.assertEqual(plantillas.dominio_sospechoso(email), esperado)

    def test_no_molesta_con_los_dominios_correctos(self):
        for email in ("a@gmail.com", "a@hotmail.com", "a@proton.me"):
            with self.subTest(email=email):
                self.assertEqual(plantillas.dominio_sospechoso(email), "")

    def test_no_molesta_con_dominios_de_empresa(self):
        # Lo importante: que no cante falsos positivos sobre direcciones legitimas, o se
        # vuelve ruido y se ignora justo cuando importa.
        for email in ("rrhh@acme.com", "jobs@globex.io", "renuka.m@spiceorb.com",
                      "seleccion@mercadolibre.com", "a@gmx.com"):
            with self.subTest(email=email):
                self.assertEqual(plantillas.dominio_sospechoso(email), "")

    def test_entrada_invalida(self):
        self.assertEqual(plantillas.dominio_sospechoso("sin-arroba"), "")
        self.assertEqual(plantillas.dominio_sospechoso(""), "")

    def test_casi_igual(self):
        self.assertTrue(plantillas._casi_igual("gmail.co", "gmail.com"))   # falta una
        self.assertTrue(plantillas._casi_igual("gmial.com", "gmail.com"))  # cambiada
        self.assertFalse(plantillas._casi_igual("gmail.com", "gmail.com")) # identicas
        self.assertFalse(plantillas._casi_igual("acme.com", "gmail.com"))  # lejanas


class ConfigVieja(unittest.TestCase):
    """Las versiones anteriores tenian `plantilla` y `asunto` sueltos por idioma. Nadie
    tiene que reescribir su config.json para que le siga andando lo de siempre."""

    def test_convierte_la_forma_vieja_en_el_tipo_directa(self):
        cfg = {"idiomas": {"es": {"plantilla": "cuerpo.txt", "asunto": "Hola {puesto}"}}}
        plantillas.normalizar(cfg)

        self.assertEqual(
            cfg["idiomas"]["es"]["plantillas"],
            {"directa": {"archivo": "cuerpo.txt", "asunto": "Hola {puesto}"}},
        )

    def test_no_pisa_una_config_que_ya_esta_al_dia(self):
        ya = {"directa": {"archivo": "a.txt", "asunto": "A"},
              "espontanea": {"archivo": "b.txt", "asunto": "B"}}
        cfg = {"idiomas": {"es": {"plantilla": "viejo.txt", "plantillas": ya}}}
        plantillas.normalizar(cfg)
        self.assertEqual(cfg["idiomas"]["es"]["plantillas"], ya)

    def test_pedir_espontanea_sobre_una_config_vieja_explica_que_falta(self):
        cfg = {"idiomas": {"es": {"plantilla": "cuerpo.txt", "asunto": "Hola"}}}
        plantillas.normalizar(cfg)

        with self.assertRaises(ValueError) as caso:
            plantillas.elegir_plantilla(cfg, "es", "espontanea")
        self.assertIn("espontanea", str(caso.exception))
        self.assertIn("directa", str(caso.exception))   # dice cual si tiene

    def test_es_idempotente(self):
        cfg = {"idiomas": {"es": {"plantilla": "cuerpo.txt", "asunto": "Hola"}}}
        plantillas.normalizar(plantillas.normalizar(cfg))
        self.assertEqual(len(cfg["idiomas"]["es"]["plantillas"]), 1)


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
        # Un "{empresa}" crudo llegando a un recruiter seria bochornoso. Las cuatro
        # combinaciones de idioma y tipo, con y sin datos.
        for idioma in ("es", "en"):
            for tipo in plantillas.TIPOS:
                for datos in (("", "", ""), ("Ana", "Acme", "QA")):
                    with self.subTest(idioma=idioma, tipo=tipo, datos=datos):
                        asunto, cuerpo = plantillas.armar(self.cfg, idioma, *datos, tipo)
                        for texto in (asunto, cuerpo):
                            self.assertNotIn("{", texto)
                            self.assertNotIn("}", texto)

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

    def test_el_tipo_elige_otro_cuerpo_y_otro_asunto(self):
        directa, cuerpo_directa = plantillas.armar(self.cfg, "es", "Ana", "Acme", "QA")
        esp, cuerpo_esp = plantillas.armar(
            self.cfg, "es", "Ana", "Acme", "QA", "espontanea"
        )

        self.assertIn("Postulación QA", directa)
        self.assertEqual(esp, "CV QA - Nombre Apellido")
        self.assertIn("Me postulo", cuerpo_directa)
        self.assertIn("Les acerco mi CV", cuerpo_esp)

    def test_el_cuerpo_espontaneo_no_nombra_el_puesto(self):
        # Es la razon de que exista: el aviso no es de QA, asi que decir "me postulo a
        # {puesto}" seria mentira. Que la plantilla no use el hueco no puede romper armar().
        _, cuerpo = plantillas.armar(
            self.cfg, "es", "Ana", "Acme", "Backend Developer", "espontanea"
        )
        self.assertNotIn("Backend Developer", cuerpo)
        self.assertIn("Acme", cuerpo)

    def test_el_cv_es_el_mismo_en_los_dos_tipos(self):
        # El tipo cambia el texto, no el adjunto: el CV de QA es el mismo.
        self.assertEqual(plantillas.ruta_cv(self.cfg, "es").name, "cv-es.pdf")

    def test_tipo_desconocido_falla_temprano(self):
        with self.assertRaises(ValueError) as caso:
            plantillas.armar(self.cfg, "es", "", "", "", "inventado")
        # El mensaje tiene que decir como arreglarlo: termina en la pantalla del usuario.
        self.assertIn("config.json", str(caso.exception))

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
