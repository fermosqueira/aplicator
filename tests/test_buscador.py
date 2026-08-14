"""El buscador del historial.

La razon de ser de guardar el post entero: poder encontrar una postulacion por una palabra
que solo aparecia en la publicacion, cuando el titulo del puesto ya no alcanza para recordar
de que se trataba.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import comun  # noqa: F401  (agrega la raiz del proyecto al sys.path)

import almacen

POST = """¡VACANTE QA | CDMX!
Nuestro cliente Mercado Pago incorpora un QA Automation Engineer para el equipo de pagos.
Requisitos: Playwright o Selenium, APIs REST, SQL Server.
Modalidad: 100% presencial en CDMX."""


class Buscador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = almacen.conectar(Path(self.tmp.name) / "b.db")
        self.addCleanup(self.con.close)

        almacen.guardar(
            self.con, email="busquedas@talentorh.com.ar", empresa="Talentorh",
            puesto="QA Automation", recruiter="Alejandra", autor_post="TalentoRH Consultora",
            texto_post=POST, url_post="https://www.linkedin.com/feed/update/urn:li:activity:1/",
            enviada_en="2026-08-14T10:00:00",
        )
        almacen.guardar(
            self.con, email="jobs@globex.io", empresa="Globex", puesto="Manual Tester",
            texto_post="We are hiring a tester for our London office.",
            enviada_en="2026-08-13T10:00:00",
        )

    def buscar(self, consulta):
        return [f["empresa"] for f in almacen.buscar(self.con, consulta)]

    def test_sin_consulta_trae_todo(self):
        self.assertEqual(len(almacen.buscar(self.con, "")), 2)

    def test_por_empresa(self):
        self.assertEqual(self.buscar("globex"), ["Globex"])

    def test_por_mail(self):
        self.assertEqual(self.buscar("talentorh.com.ar"), ["Talentorh"])

    def test_por_una_palabra_que_solo_esta_en_el_post(self):
        # "Mercado Pago" y "CDMX" no estan en ningun campo del formulario: solo en el post.
        # Este es el caso que justifica toda la funcionalidad.
        self.assertEqual(self.buscar("mercado pago"), ["Talentorh"])
        self.assertEqual(self.buscar("cdmx"), ["Talentorh"])

    def test_por_autor_de_la_publicacion(self):
        self.assertEqual(self.buscar("consultora"), ["Talentorh"])

    def test_no_distingue_mayusculas(self):
        self.assertEqual(self.buscar("GLOBEX"), ["Globex"])

    def test_no_distingue_acentos(self):
        # El LIKE de SQLite no ignora acentos, por eso el filtrado se hace en Python.
        self.assertEqual(self.buscar("busquedas"), ["Talentorh"])
        self.assertEqual(self.buscar("búsquedas"), ["Talentorh"])

    def test_varios_terminos_tienen_que_estar_todos(self):
        self.assertEqual(self.buscar("globex tester"), ["Globex"])
        self.assertEqual(self.buscar("globex mercado"), [])

    def test_sin_coincidencias(self):
        self.assertEqual(self.buscar("cocinero"), [])

    def test_ordenado_por_fecha_descendente(self):
        self.assertEqual(self.buscar(""), ["Talentorh", "Globex"])


class PostGuardado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = almacen.conectar(Path(self.tmp.name) / "p.db")
        self.addCleanup(self.con.close)

    def test_guarda_y_devuelve_el_post_completo(self):
        almacen.guardar(self.con, email="a@x.com", texto_post=POST,
                        url_post="https://linkedin.com/x", autor_post="Alguien")
        fila = almacen.buscar_por_email(self.con, "a@x.com")[0]
        self.assertEqual(fila["texto_post"], POST)
        self.assertEqual(fila["url_post"], "https://linkedin.com/x")
        self.assertEqual(fila["autor_post"], "Alguien")

    def test_sin_post_no_rompe(self):
        # La CLI no tiene de donde sacar el post: la fila igual tiene que ser valida.
        almacen.guardar(self.con, email="a@x.com")
        self.assertEqual(almacen.buscar_por_email(self.con, "a@x.com")[0]["texto_post"], "")

    def test_hilo_y_respondida(self):
        id_fila = almacen.guardar(self.con, email="a@x.com")
        almacen.guardar_hilo(self.con, id_fila, "1873451593153483637")
        almacen.marcar_respondida(self.con, id_fila, "2026-08-20T09:00:00")
        fila = almacen.buscar_por_email(self.con, "a@x.com")[0]
        self.assertEqual(fila["hilo"], "1873451593153483637")
        self.assertEqual(fila["respondida"], 1)
        self.assertEqual(fila["respondida_en"], "2026-08-20T09:00:00")

    def test_sin_responder_excluye_las_ya_respondidas(self):
        a = almacen.guardar(self.con, email="a@x.com")
        almacen.guardar(self.con, email="b@x.com")
        almacen.marcar_respondida(self.con, a)
        pendientes = [f["email"] for f in almacen.sin_responder(self.con)]
        self.assertEqual(pendientes, ["b@x.com"])


if __name__ == "__main__":
    unittest.main()
