"""El registro de postulaciones: es lo que evita el doble envio y lo que responde,
meses despues, de que empresa era esa casilla."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import comun  # noqa: F401  (agrega la raiz del proyecto al sys.path)

import almacen


class Registro(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = Path(self.tmp.name) / "prueba.db"
        self.con = almacen.conectar(self.ruta)
        self.addCleanup(self.con.close)

    def test_guarda_y_devuelve_lo_guardado(self):
        almacen.guardar(
            self.con, email="rrhh@acme.com", empresa="Acme", puesto="QA", idioma="es"
        )
        filas = almacen.buscar_por_email(self.con, "rrhh@acme.com")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["empresa"], "Acme")

    def test_la_busqueda_no_distingue_mayusculas(self):
        # El mismo recruiter escrito distinto sigue siendo el mismo recruiter.
        almacen.guardar(self.con, email="RRHH@Acme.COM", empresa="Acme")
        self.assertEqual(len(almacen.buscar_por_email(self.con, "rrhh@acme.com")), 1)

    def test_ignora_espacios_al_costado(self):
        almacen.guardar(self.con, email="  rrhh@acme.com  ")
        self.assertEqual(len(almacen.buscar_por_email(self.con, "rrhh@acme.com")), 1)

    def test_direccion_nueva_no_trae_antecedentes(self):
        almacen.guardar(self.con, email="rrhh@acme.com")
        self.assertEqual(almacen.buscar_por_email(self.con, "otro@acme.com"), [])

    def test_varias_postulaciones_al_mismo_mail(self):
        almacen.guardar(self.con, email="rrhh@acme.com", puesto="QA Manual")
        almacen.guardar(self.con, email="rrhh@acme.com", puesto="QA Automation")
        self.assertEqual(len(almacen.buscar_por_email(self.con, "rrhh@acme.com")), 2)

    def test_lo_mas_nuevo_va_primero(self):
        # Fechas explicitas: dos inserciones en el mismo segundo empatarian y el orden
        # quedaria librado al azar.
        almacen.guardar(self.con, email="a@x.com", empresa="Vieja", enviada_en="2026-01-01T10:00:00")
        almacen.guardar(self.con, email="a@x.com", empresa="Nueva", enviada_en="2026-06-01T10:00:00")
        filas = almacen.buscar_por_email(self.con, "a@x.com")
        self.assertEqual([f["empresa"] for f in filas], ["Nueva", "Vieja"])

    def test_marca_de_etiquetado(self):
        # Un envio sin etiquetar no es un error, pero tiene que quedar registrado como tal.
        id_fila = almacen.guardar(self.con, email="a@x.com")
        self.assertEqual(almacen.buscar_por_email(self.con, "a@x.com")[0]["etiquetada"], 0)
        almacen.marcar_etiquetada(self.con, id_fila, True)
        self.assertEqual(almacen.buscar_por_email(self.con, "a@x.com")[0]["etiquetada"], 1)

    def test_los_campos_no_provistos_tienen_valor_por_defecto(self):
        almacen.guardar(self.con, email="a@x.com")
        fila = almacen.buscar_por_email(self.con, "a@x.com")[0]
        self.assertEqual(fila["empresa"], "")
        self.assertEqual(fila["puesto"], "")
        self.assertTrue(fila["enviada_en"])

    def test_listar_respeta_el_limite(self):
        for i in range(5):
            almacen.guardar(self.con, email=f"a{i}@x.com")
        self.assertEqual(len(almacen.listar(self.con, limite=3)), 3)


class Sesion(unittest.TestCase):
    def test_la_sesion_cierra_la_conexion(self):
        # `with sqlite3.connect(...)` NO cierra: maneja la transaccion. Por eso existe
        # almacen.sesion(), y por eso conviene tener el test que lo demuestra.
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "s.db"
            with almacen.sesion(ruta) as con:
                almacen.guardar(con, email="a@x.com")
            with self.assertRaises(Exception):
                con.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
