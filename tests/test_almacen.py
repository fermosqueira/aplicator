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


class EstadoDeLaPostulacion(unittest.TestCase):
    """Respondida y rebotada se excluyen. Una fila con las dos marcas afirma dos cosas
    contrarias sobre la misma postulacion, y el panel muestra una de ellas al azar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = almacen.conectar(Path(self.tmp.name) / "estado.db")
        self.addCleanup(self.con.close)
        self.id = almacen.guardar(self.con, email="rrhh@acme.com", empresa="Acme")

    def fila(self):
        return almacen.buscar_por_email(self.con, "rrhh@acme.com")[0]

    def test_marcar_rebotada_limpia_respondida(self):
        # Paso de verdad: una version vieja del detector, corriendo en paralelo, tomo un
        # rebote por una respuesta y dejo la fila con las dos marcas puestas.
        almacen.marcar_respondida(self.con, self.id, "2026-08-14T10:00:00")
        almacen.marcar_rebotada(self.con, self.id, "2026-08-14T10:00:12")

        fila = self.fila()
        self.assertEqual(fila["rebotada"], 1)
        self.assertEqual(fila["respondida"], 0)
        self.assertEqual(fila["respondida_en"], "")

    def test_marcar_respondida_limpia_rebotada(self):
        # Al reves tambien: si despues del rebote contesta alguien, gana la respuesta.
        almacen.marcar_rebotada(self.con, self.id, "2026-08-14T10:00:12")
        almacen.marcar_respondida(self.con, self.id, "2026-08-15T09:00:00")

        fila = self.fila()
        self.assertEqual(fila["respondida"], 1)
        self.assertEqual(fila["rebotada"], 0)
        self.assertEqual(fila["rebotada_en"], "")

    def test_las_dos_sacan_la_fila_de_pendientes(self):
        self.assertEqual(len(almacen.sin_responder(self.con)), 1)
        almacen.marcar_rebotada(self.con, self.id)
        self.assertEqual(almacen.sin_responder(self.con), [])

    def test_descartar_a_mano(self):
        almacen.marcar_descartada(self.con, self.id)
        fila = self.fila()
        self.assertEqual(fila["descartada"], 1)
        self.assertTrue(fila["descartada_en"])
        self.assertEqual(almacen.sin_responder(self.con), [])

    def test_descartar_se_puede_deshacer(self):
        # Marcar por error una postulacion que seguia viva no puede costar la postulacion.
        almacen.marcar_descartada(self.con, self.id)
        almacen.marcar_descartada(self.con, self.id, descartada=False)

        fila = self.fila()
        self.assertEqual(fila["descartada"], 0)
        self.assertEqual(fila["descartada_en"], "")   # sin fecha colgada de antes
        self.assertEqual(len(almacen.sin_responder(self.con)), 1)

    def test_las_descartadas_van_al_fondo_pero_siguen_estando(self):
        # Al fondo para que no hagan ruido; presentes porque son historial: dentro de tres
        # meses sirve saber que a esta empresa ya le escribiste.
        # Acme es de hoy; Vieja es de 2020. Por fecha Acme iria primera.
        almacen.guardar(self.con, email="hola@vieja.com", empresa="Vieja",
                        enviada_en="2020-01-01T10:00:00")
        almacen.marcar_descartada(self.con, self.id)

        empresas = [f["empresa"] for f in almacen.buscar(self.con)]
        self.assertEqual(empresas, ["Vieja", "Acme"])  # descartada al fondo aunque sea la mas nueva
        self.assertEqual(len(almacen.listar(self.con)), 2)

    def test_descartar_no_pisa_la_respuesta(self):
        # Son datos distintos: "contestaron" y "lo que contestaron fue que no".
        almacen.marcar_respondida(self.con, self.id, "2026-08-14T10:00:00")
        almacen.marcar_descartada(self.con, self.id)

        fila = self.fila()
        self.assertEqual(fila["respondida"], 1)
        self.assertEqual(fila["descartada"], 1)


class BusquedaPorTipo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = almacen.conectar(Path(self.tmp.name) / "tipos.db")
        self.addCleanup(self.con.close)
        almacen.guardar(self.con, email="a@acme.com", empresa="Acme")
        almacen.guardar(self.con, email="b@globex.com", empresa="Globex", tipo="espontanea")

    def test_se_pueden_filtrar_las_espontaneas(self):
        filas = almacen.buscar(self.con, "espontanea")
        self.assertEqual([f["empresa"] for f in filas], ["Globex"])

    def test_el_tipo_queda_guardado(self):
        self.assertEqual(almacen.buscar_por_email(self.con, "a@acme.com")[0]["tipo"], "directa")
        self.assertEqual(
            almacen.buscar_por_email(self.con, "b@globex.com")[0]["tipo"], "espontanea"
        )


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
