"""Servidor local que le da acceso al motor a la extension de Chrome.

Escucha unicamente en 127.0.0.1, asi que nada fuera de esta maquina lo alcanza. Pero
"local" no es lo mismo que "seguro": cualquier pagina web que visites puede intentar
hacerle un POST a localhost desde tu propio navegador. Por eso toda ruta que haga algo
exige la cabecera X-Aplicador-Token. Al ser una cabecera propia, el navegador obliga a
un preflight que solo aprobamos para los origenes de la lista, y una pagina cualquiera
no puede pasar ese filtro.

    python servidor.py
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import almacen
import nucleo
import plantillas

LIMITE_CUERPO = 256 * 1024


class Manejador(BaseHTTPRequestHandler):
    """La configuracion se inyecta con crear_servidor() en vez de leerse al importar:
    de otro modo el modulo no se puede ni importar sin un config.json al lado, y los
    tests quedarian atados a las credenciales reales de la maquina."""

    server_version = "Aplicador/1.0"
    cfg: dict = {}
    ruta_db = None  # None = la base de siempre; los tests apuntan a una temporal

    @property
    def ajustes(self) -> dict:
        return self.cfg["servidor"]

    # --- plomeria HTTP -----------------------------------------------------------

    def _origen_ok(self) -> bool:
        """Un pedido sin Origin no puede venir de otra pagina: los navegadores siempre lo
        mandan en un POST cross-origin. Puede ser la CLI o un test, y ahi el token alcanza."""
        origen = self.headers.get("Origin")
        if origen is None:
            return True
        return origen.startswith("chrome-extension://") or origen in self.ajustes["origenes"]

    def _cors(self, origen: str | None) -> None:
        self.send_header("Access-Control-Allow-Origin", origen or "null")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Aplicador-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")

    def _responder(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cors(self.headers.get("Origin"))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer_json(self) -> dict:
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0:
            return {}
        if largo > LIMITE_CUERPO:
            raise ValueError("El cuerpo del pedido es demasiado grande")
        return json.loads(self.rfile.read(largo).decode("utf-8"))

    def log_message(self, formato, *args):  # noqa: N802  (lo pide BaseHTTPRequestHandler)
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    # --- rutas -------------------------------------------------------------------

    def do_OPTIONS(self):  # noqa: N802
        permitido = self._origen_ok()
        self.send_response(204 if permitido else 403)
        if permitido:
            self._cors(self.headers.get("Origin"))
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/ping":
            self._responder(200, {"ok": True, "servicio": "aplicador"})
        else:
            self._responder(404, {"ok": False, "error": "ruta desconocida"})

    def do_POST(self):  # noqa: N802
        if self.headers.get("X-Aplicador-Token") != self.ajustes["token"]:
            self._responder(403, {"ok": False, "error": "token invalido"})
            return
        if not self._origen_ok():
            self._responder(403, {"ok": False, "error": "origen no permitido"})
            return

        ruta = self.path.rstrip("/") or "/"
        rutas = {
            "/sugerir": self._sugerir,
            "/previsualizar": self._previsualizar,
            "/enviar": self._enviar,
        }
        accion = rutas.get(ruta)
        if accion is None:
            self._responder(404, {"ok": False, "error": "ruta desconocida"})
            return

        try:
            self._responder(200, accion(self._leer_json()))
        except (ValueError, FileNotFoundError) as e:
            self._responder(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._responder(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    # --- acciones ----------------------------------------------------------------

    @staticmethod
    def _campos(datos: dict) -> dict:
        return {
            "destino": (datos.get("email") or "").strip(),
            "recruiter": (datos.get("recruiter") or "").strip(),
            "empresa": (datos.get("empresa") or "").strip(),
            "puesto": (datos.get("puesto") or "").strip(),
            "idioma": datos.get("idioma") if datos.get("idioma") in ("es", "en") else "es",
        }

    def _sugerir(self, datos: dict) -> dict:
        email = (datos.get("email") or "").strip()
        sugerencias = nucleo.sugerir(self.cfg, email, datos.get("texto") or "")
        with almacen.sesion(self.ruta_db) as con:
            previos = almacen.buscar_por_email(con, email)
        sugerencias["duplicados"] = [
            {"fecha": p["enviada_en"][:10], "empresa": p["empresa"], "puesto": p["puesto"]}
            for p in previos
        ]
        sugerencias["ok"] = True
        return sugerencias

    def _previsualizar(self, datos: dict) -> dict:
        with almacen.sesion(self.ruta_db) as con:
            vista = nucleo.previsualizar(self.cfg, con, **self._campos(datos))
        vista["ok"] = True
        return vista

    def _enviar(self, datos: dict) -> dict:
        # El envio si necesita credenciales: las releemos por si acabas de cargarlas.
        cfg = plantillas.cargar_config()
        with almacen.sesion(self.ruta_db) as con:
            return nucleo.postular(cfg, con, **self._campos(datos))


def crear_servidor(cfg: dict, puerto: int | None = None, ruta_db=None) -> ThreadingHTTPServer:
    """Arma el servidor con una configuracion dada. Puerto 0 = que el sistema elija uno
    libre, que es lo que usan los tests para no chocar con el servidor de verdad."""
    manejador = type("ManejadorConfigurado", (Manejador,), {"cfg": cfg, "ruta_db": ruta_db})
    if puerto is None:
        puerto = cfg["servidor"]["puerto"]
    return ThreadingHTTPServer(("127.0.0.1", puerto), manejador)


def main() -> int:
    cfg = plantillas.cargar_config(exigir_clave=False)
    servidor = crear_servidor(cfg)
    puerto = servidor.server_address[1]
    print(f"Aplicador escuchando en http://127.0.0.1:{puerto}  (Ctrl+C para cortar)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCortado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
