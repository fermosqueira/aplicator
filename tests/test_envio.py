"""El envio: la guarda contra el duplicado y el etiquetado que quedo aparte.

Ninguna prueba manda un mail. La guarda de duplicados corta antes de `correo.enviar`, y
donde hace falta llegar mas lejos se reemplaza esa funcion por un doble: si el reemplazo
fallara, la config de prueba apunta a `smtp.invalido` y no hay a donde mandar nada.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from comun import armar_config

import almacen
import correo
import nucleo
import plantillas


class VentanaDeDuplicados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = almacen.conectar(Path(self.tmp.name) / "envio.db")
        self.addCleanup(self.con.close)

    def test_la_misma_recien_mandada_cuenta(self):
        almacen.guardar(self.con, email="rrhh@acme.com", asunto="Postulación QA - Yo")
        self.assertTrue(
            almacen.enviada_hace_poco(self.con, "rrhh@acme.com", "Postulación QA - Yo", 120)
        )

    def test_la_misma_de_hace_rato_no_cuenta(self):
        vieja = (datetime.now() - timedelta(hours=3)).isoformat(timespec="seconds")
        almacen.guardar(
            self.con, email="rrhh@acme.com", asunto="Postulación QA - Yo", enviada_en=vieja
        )
        self.assertFalse(
            almacen.enviada_hace_poco(self.con, "rrhh@acme.com", "Postulación QA - Yo", 120)
        )

    def test_otro_puesto_a_la_misma_empresa_pasa(self):
        # El asunto lleva el puesto: postularse a dos busquedas distintas el mismo dia es
        # normal y no tiene por que esperar.
        almacen.guardar(self.con, email="rrhh@acme.com", asunto="Postulación QA - Yo")
        self.assertFalse(
            almacen.enviada_hace_poco(self.con, "rrhh@acme.com", "Postulación SDET - Yo", 120)
        )

    def test_otro_destinatario_pasa(self):
        almacen.guardar(self.con, email="rrhh@acme.com", asunto="Postulación QA - Yo")
        self.assertFalse(
            almacen.enviada_hace_poco(self.con, "otra@acme.com", "Postulación QA - Yo", 120)
        )

    def test_no_distingue_mayusculas_en_el_mail(self):
        almacen.guardar(self.con, email="RRHH@Acme.com", asunto="Postulación QA - Yo")
        self.assertTrue(
            almacen.enviada_hace_poco(self.con, "rrhh@acme.com", "Postulación QA - Yo", 120)
        )


class Postular(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = armar_config(Path(self.tmp.name))
        self.con = almacen.conectar(Path(self.tmp.name) / "envio.db")
        self.addCleanup(self.con.close)

    def asunto_de(self, puesto="QA Automation"):
        return plantillas.armar(self.cfg, "es", "", "Acme", puesto)[0]

    def test_rechaza_el_reenvio_inmediato(self):
        # El caso que motivo todo esto: dos mails identicos seguidos al mismo recruiter.
        almacen.guardar(self.con, email="rrhh@acme.com", asunto=self.asunto_de())

        with self.assertRaises(ValueError) as caso:
            nucleo.postular(
                self.cfg, self.con, "rrhh@acme.com", empresa="Acme", puesto="QA Automation"
            )

        self.assertIn("2 minutos", str(caso.exception))
        # Y sobre todo: no quedo una segunda fila.
        self.assertEqual(len(almacen.buscar_por_email(self.con, "rrhh@acme.com")), 1)

    def test_la_guarda_corta_antes_de_tocar_la_red(self):
        # Si llegara a llamar a correo.enviar, el test lo delata en vez de dejarlo pasar.
        almacen.guardar(self.con, email="rrhh@acme.com", asunto=self.asunto_de())
        with mock.patch.object(correo, "enviar") as enviar:
            with self.assertRaises(ValueError):
                nucleo.postular(
                    self.cfg, self.con, "rrhh@acme.com", empresa="Acme", puesto="QA Automation"
                )
        enviar.assert_not_called()

    def test_sin_etiquetar_no_toca_imap(self):
        # Es lo que le permite al servidor contestar rapido: el etiquetado va despues, en
        # otro hilo, y el drawer no espera por el.
        with mock.patch.object(correo, "enviar"), \
             mock.patch.object(correo, "etiquetar") as etiquetar:
            resultado = nucleo.postular(
                self.cfg, self.con, "rrhh@acme.com", empresa="Acme", puesto="QA",
                etiquetar_ahora=False,
            )

        etiquetar.assert_not_called()
        self.assertTrue(resultado["ok"])
        self.assertNotIn("etiquetada", resultado)   # todavia no paso: no se afirma nada
        self.assertTrue(resultado["marca"])         # lo que necesita el hilo de fondo
        self.assertEqual(resultado["etiqueta"], "Postulaciones/Acme")

    def test_la_cli_si_etiqueta_en_el_momento(self):
        with mock.patch.object(correo, "enviar"), \
             mock.patch.object(correo, "etiquetar", return_value=(True, "777")) as etiquetar:
            resultado = nucleo.postular(
                self.cfg, self.con, "rrhh@acme.com", empresa="Acme", puesto="QA"
            )

        etiquetar.assert_called_once()
        self.assertTrue(resultado["etiquetada"])


class EtiquetadoAparte(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = armar_config(Path(self.tmp.name))
        self.con = almacen.conectar(Path(self.tmp.name) / "envio.db")
        self.addCleanup(self.con.close)
        self.id = almacen.guardar(self.con, email="rrhh@acme.com", empresa="Acme")

    def fila(self):
        return almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]

    def test_guarda_la_etiqueta_y_el_hilo(self):
        with mock.patch.object(correo, "etiquetar", return_value=(True, "12345")):
            ok = nucleo.etiquetar_pendiente(
                self.cfg, self.con, self.id, "marca", "rrhh@acme.com", "Postulaciones/Acme"
            )

        self.assertTrue(ok)
        self.assertEqual(self.fila()["etiquetada"], 1)
        self.assertEqual(self.fila()["hilo"], "12345")

    def test_si_falla_la_postulacion_igual_queda_registrada(self):
        # El mail ya salio: que Gmail no deje etiquetarlo no puede perder el registro.
        with mock.patch.object(correo, "etiquetar", side_effect=OSError("IMAP caido")):
            ok = nucleo.etiquetar_pendiente(
                self.cfg, self.con, self.id, "marca", "rrhh@acme.com", "Postulaciones/Acme"
            )

        self.assertFalse(ok)
        self.assertEqual(self.fila()["etiquetada"], 0)
        self.assertEqual(self.fila()["hilo"], "")   # y el detector cae a buscar por remitente


if __name__ == "__main__":
    unittest.main()
