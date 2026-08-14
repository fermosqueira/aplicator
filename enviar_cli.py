"""Envio de postulaciones desde la consola.

Sirve para probar el motor sin la extension, y como respaldo si Chrome no esta a mano.

    python enviar_cli.py --probar
    python enviar_cli.py --ver    rrhh@acme.com --empresa Acme --puesto "QA Automation"
    python enviar_cli.py --enviar rrhh@acme.com --empresa Acme --puesto "QA Automation" \
                         --recruiter Ana --idioma es
    python enviar_cli.py --historial
"""

from __future__ import annotations

import argparse
import sys

import almacen
import correo
import nucleo
import plantillas


def _consola_utf8() -> None:
    """La consola de Windows viene en cp1252 y destroza los acentos del preview. Como el
    preview existe para confiar en lo que se va a mandar, tiene que verse igual que el mail."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _rotulo(texto: str) -> None:
    print(f"\n{texto}\n{'-' * len(texto)}")


def cmd_probar() -> int:
    cfg = plantillas.cargar_config()
    _rotulo("Conexion con Gmail")
    for linea in correo.probar_conexion(cfg):
        print(" ", linea)
    return 0


def cmd_historial(limite: int) -> int:
    con = almacen.conectar()
    filas = almacen.listar(con, limite)
    if not filas:
        print("Todavia no hay postulaciones registradas.")
        return 0

    _rotulo(f"Ultimas {len(filas)} postulaciones")
    for f in filas:
        estado = "respondida" if f["respondida"] else ("enviada" if f["etiquetada"] else "sin etiquetar")
        print(f"  {f['enviada_en'][:16]}  {f['email']:<34} {f['empresa']:<20} "
              f"{f['puesto']:<24} [{estado}]")
    return 0


def cmd_buscar(consulta: str) -> int:
    con = almacen.conectar()
    filas = almacen.buscar(con, consulta)
    if not filas:
        print(f"Nada coincide con {consulta!r}.")
        return 0

    _rotulo(f"{len(filas)} coincidencia(s) con {consulta!r}")
    for f in filas:
        print(f"\n  {f['enviada_en'][:10]}  {f['empresa'] or '—'} · {f['puesto'] or '—'}")
        print(f"    {f['email']}" + (f"  ({f['recruiter']})" if f["recruiter"] else ""))
        if f["autor_post"]:
            print(f"    publicado por {f['autor_post']}")
        if f["url_post"]:
            print(f"    {f['url_post']}")
        if f["texto_post"]:
            recorte = " ".join(f["texto_post"].split())[:220]
            print(f"    {recorte}…")
    print("\n  (el texto completo se lee mejor en http://127.0.0.1:8765/historial)")
    return 0


def cmd_respuestas() -> int:
    cfg = plantillas.cargar_config()
    con = almacen.conectar()
    resultado = nucleo.detectar_respuestas(cfg, con)

    _rotulo(f"Revisadas {resultado['revisadas']} postulaciones pendientes")
    if not resultado["nuevas"]:
        print("  Sin respuestas nuevas.")
        return 0
    for n in resultado["nuevas"]:
        print(f"  {n['empresa'] or n['email']} · {n['puesto'] or '—'}")
        print(f"    respondio {n['de']} el {n['cuando'][:10]}")
    return 0


def cmd_ver(args) -> int:
    # Previsualizar no manda nada, asi que no exigimos tener el app_password cargado.
    cfg = plantillas.cargar_config(exigir_clave=False)
    con = almacen.conectar()
    vista = nucleo.previsualizar(
        cfg, con, args.destino, args.recruiter, args.empresa, args.puesto, args.idioma
    )

    _rotulo("Asi saldria el mail")
    print(f"  Para:     {vista['destino']}")
    print(f"  Asunto:   {vista['asunto']}")
    print(f"  Adjunto:  {vista['cv']}")
    print(f"  Etiqueta: {vista['etiqueta']}")
    print()
    print(vista["cuerpo"])

    if vista["duplicados"]:
        _rotulo("Ojo: ya le escribiste a esta direccion")
        for d in vista["duplicados"]:
            print(f"  {d['fecha']}  {d['empresa']} - {d['puesto']}")
    return 0


def cmd_enviar(args) -> int:
    cfg = plantillas.cargar_config()
    con = almacen.conectar()

    vista = nucleo.previsualizar(
        cfg, con, args.destino, args.recruiter, args.empresa, args.puesto, args.idioma
    )
    if vista["duplicados"] and not args.igual:
        _rotulo("Ya le escribiste a esta direccion")
        for d in vista["duplicados"]:
            print(f"  {d['fecha']}  {d['empresa']} - {d['puesto']}")
        print("\nSi igual queres enviar, agregá --igual.")
        return 1

    resultado = nucleo.postular(
        cfg, con, args.destino, args.recruiter, args.empresa, args.puesto, args.idioma
    )

    _rotulo("Enviado")
    print(f"  Para:     {resultado['destino']}")
    print(f"  Asunto:   {resultado['asunto']}")
    print(f"  Adjunto:  {resultado['cv']}")
    if resultado["etiquetada"]:
        print(f"  Etiqueta: {resultado['etiqueta']}")
    else:
        print(f"  Etiqueta: NO se pudo aplicar '{resultado['etiqueta']}' "
              f"(el mail salio igual; queda registrado en la base)")
    return 0


def main(argv: list[str] | None = None) -> int:
    _consola_utf8()
    p = argparse.ArgumentParser(description="Postularse por mail desde la consola.")
    p.add_argument("destino", nargs="?", help="direccion de mail del recruiter")
    p.add_argument("--empresa", default="", help="nombre de la empresa")
    p.add_argument("--puesto", default="", help="titulo del puesto")
    p.add_argument("--recruiter", default="", help="nombre de pila de quien recibe")
    p.add_argument("--idioma", default="es", choices=["es", "en"])
    p.add_argument("--igual", action="store_true", help="enviar aunque sea repetido")

    p.add_argument("--ver", action="store_true", help="mostrar el mail sin enviarlo")
    p.add_argument("--enviar", action="store_true", help="enviar de verdad")
    p.add_argument("--probar", action="store_true", help="chequear credenciales de Gmail")
    p.add_argument("--historial", action="store_true", help="listar lo ya enviado")
    p.add_argument("--buscar", metavar="TEXTO", help="buscar en el historial, incluido el post")
    p.add_argument("--respuestas", action="store_true", help="revisar Gmail por respuestas nuevas")

    args = p.parse_args(argv)

    if args.probar:
        return cmd_probar()
    if args.historial:
        return cmd_historial(50)
    if args.buscar:
        return cmd_buscar(args.buscar)
    if args.respuestas:
        return cmd_respuestas()
    if not args.destino:
        p.print_help()
        return 1
    if args.enviar:
        return cmd_enviar(args)
    return cmd_ver(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, FileNotFoundError) as e:
        print(f"\nError: {e}\n", file=sys.stderr)
        sys.exit(2)
