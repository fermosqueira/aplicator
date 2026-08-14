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
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import almacen
import nucleo
import panel
import plantillas

LIMITE_CUERPO = 256 * 1024
ARRANQUE = datetime.now().strftime("%d/%m %H:%M")
RUTA_LOG = Path(__file__).resolve().parent / "servidor.log"

# La primera revision no arranca junto con el servidor: si esto se levanto con Windows, la
# red todavia puede no estar lista. Un minuto y medio alcanza y no se nota.
ESPERA_INICIAL = 90
CADA_POR_DEFECTO = 30  # minutos

# El detector no puede correr dos veces a la vez. Si el revisor automatico y el boton del
# panel se cruzan, las dos pasadas verian la misma postulacion como pendiente y le pegarian
# la etiqueta dos veces.
_candado = threading.Lock()
ULTIMA_REVISION = {"cuando": "", "resultado": "todavía no revisó"}


def _log(mensaje: str) -> None:
    """Con la hora adelante. Un log sin hora no sirve para reconstruir en que orden paso
    algo, que es lo unico para lo que uno lo abre."""
    print(f"  [{datetime.now():%H:%M:%S}] {mensaje}")


def revisar(ruta_db=None) -> dict:
    """Una pasada del detector. La comparten el boton del panel y el revisor automatico."""
    with _candado:
        cfg = plantillas.cargar_config()  # necesita credenciales: habla con Gmail
        with almacen.sesion(ruta_db) as con:
            resultado = nucleo.detectar_respuestas(cfg, con)

        ULTIMA_REVISION["cuando"] = datetime.now().strftime("%d/%m %H:%M")
        ULTIMA_REVISION["resultado"] = (
            f"{len(resultado['nuevas'])} respuesta(s), {len(resultado['rebotes'])} rebote(s)"
            f" sobre {resultado['revisadas']} pendiente(s)"
        )
        return resultado


def _revisor(ruta_db=None, cada_minutos: int = CADA_POR_DEFECTO) -> None:
    """Bucle de fondo. Sin esto el detector es una funcion que hay que acordarse de correr,
    para algo que pasa semanas despues: o sea, una funcion que en la practica no existe."""
    time.sleep(ESPERA_INICIAL)
    while True:
        try:
            resultado = revisar(ruta_db)
            # Una linea por pasada aunque no haya novedades: esto corre sin ventana y sin
            # avisar, y un proceso invisible que no deja rastro no se distingue de uno
            # muerto. Son 48 lineas por dia.
            _log(ULTIMA_REVISION["resultado"])
            for r in resultado["nuevas"]:
                _log(f"respuesta de {r['empresa'] or r['email']}")
            for r in resultado["rebotes"]:
                _log(f"REBOTE en {r['email']} - el mail nunca llego")
        except Exception as e:
            # Que falle una revision no puede tumbar el servidor: el envio tiene que seguir
            # andando aunque Gmail este caido o falte la clave.
            _log(f"revision fallida: {type(e).__name__}: {e}")
        time.sleep(max(60, cada_minutos * 60))


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
        if origen.startswith("chrome-extension://"):
            return True
        # El panel del historial lo servimos nosotros: sus pedidos son same-origin.
        puerto = self.server.server_address[1]
        propios = {f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"}
        return origen in propios or origen in self.ajustes["origenes"]

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
        _log(f"{self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    # --- rutas -------------------------------------------------------------------

    def do_OPTIONS(self):  # noqa: N802
        permitido = self._origen_ok()
        self.send_response(204 if permitido else 403)
        if permitido:
            self._cors(self.headers.get("Origin"))
        self.end_headers()

    def do_GET(self):  # noqa: N802
        ruta = self.path.split("?")[0].rstrip("/") or "/"
        if ruta == "/ping":
            self._responder(200, {
                "ok": True, "servicio": "aplicador", "desde": ARRANQUE,
                "ultima_revision": ULTIMA_REVISION["cuando"],
                "resultado_revision": ULTIMA_REVISION["resultado"],
            })
        elif ruta in ("/", "/historial"):
            cuerpo = panel.render(self.ajustes["token"], ARRANQUE)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
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
            "/buscar": self._buscar,
            "/respuestas": self._respuestas,
        }
        accion = rutas.get(ruta)
        if accion is None:
            self._responder(404, {"ok": False, "error": "ruta desconocida"})
            return

        try:
            self._responder(200, accion(self._leer_json()))
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # El navegador se cansó de esperar y cortó. Revisar respuestas puede tardar
            # bastante contra Gmail. El trabajo del servidor ya se hizo; lo unico que se
            # perdio es el aviso. Intentar contestar un 500 aca solo suma otro traceback.
            _log(f"{self.path}: el cliente corto antes de la respuesta (el trabajo se hizo)")
        except (ValueError, FileNotFoundError) as e:
            self._responder(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self._responder(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    # --- acciones ----------------------------------------------------------------

    @staticmethod
    def _campos(datos: dict, con_post: bool = False) -> dict:
        campos = {
            "destino": (datos.get("email") or "").strip(),
            "recruiter": (datos.get("recruiter") or "").strip(),
            "empresa": (datos.get("empresa") or "").strip(),
            "puesto": (datos.get("puesto") or "").strip(),
            "idioma": datos.get("idioma") if datos.get("idioma") in ("es", "en") else "es",
        }
        if con_post:
            # Solo al enviar: previsualizar no necesita el post y no tiene donde guardarlo.
            campos["texto_post"] = (datos.get("texto") or "").strip()
            campos["url_post"] = (datos.get("url") or "").strip()
            campos["autor_post"] = (datos.get("autor") or "").strip()
        return campos

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

    def _buscar(self, datos: dict) -> dict:
        with almacen.sesion(self.ruta_db) as con:
            filas = almacen.buscar(con, datos.get("q") or "")

        salida = []
        for fila in filas:
            item = dict(fila)
            # Solo para las que rebotaron: si el dominio se parece a uno conocido, decirlo.
            # Es la diferencia entre "no llego" y "no llego, y mira que te falto una letra".
            if item.get("rebotada"):
                item["sugerencia_dominio"] = plantillas.dominio_sospechoso(item["email"])
            salida.append(item)
        return {"ok": True, "filas": salida}

    def _respuestas(self, datos: dict) -> dict:
        return revisar(self.ruta_db)

    def _enviar(self, datos: dict) -> dict:
        # El envio si necesita credenciales: las releemos por si acabas de cargarlas.
        cfg = plantillas.cargar_config()
        with almacen.sesion(self.ruta_db) as con:
            return nucleo.postular(cfg, con, **self._campos(datos, con_post=True))


def crear_servidor(cfg: dict, puerto: int | None = None, ruta_db=None) -> ThreadingHTTPServer:
    """Arma el servidor con una configuracion dada. Puerto 0 = que el sistema elija uno
    libre, que es lo que usan los tests para no chocar con el servidor de verdad."""
    manejador = type("ManejadorConfigurado", (Manejador,), {"cfg": cfg, "ruta_db": ruta_db})
    if puerto is None:
        puerto = cfg["servidor"]["puerto"]
    return ThreadingHTTPServer(("127.0.0.1", puerto), manejador)


def _salida_a_archivo() -> None:
    """Bajo pythonw.exe no hay consola y sys.stdout es None: cualquier print reventaria y,
    peor, no habria forma de saber que esta pasando. Se manda todo a servidor.log."""
    if sys.stdout is not None:
        return
    log = open(RUTA_LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log


def main() -> int:
    _salida_a_archivo()
    cfg = plantillas.cargar_config(exigir_clave=False)
    servidor = crear_servidor(cfg)
    puerto = servidor.server_address[1]

    # El revisor se lanza aca y no en crear_servidor() a proposito: asi los tests, que usan
    # la fabrica, nunca levantan un hilo que se conectaria a Gmail de verdad.
    cada = int(cfg["servidor"].get("revisar_cada_minutos", CADA_POR_DEFECTO))
    if cada > 0:
        threading.Thread(target=_revisor, args=(None, cada), daemon=True).start()

    # Sin acentos ni simbolos: el log se lee con herramientas que asumen ANSI y los
    # destrozan. Un log no necesita adornos.
    print(f"[{ARRANQUE}] Aplicador escuchando en http://127.0.0.1:{puerto}"
          f" - historial: http://127.0.0.1:{puerto}/historial")
    print(f"  revisando respuestas cada {cada} min" if cada > 0 else "  revision automatica apagada")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCortado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
