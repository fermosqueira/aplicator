"""Orquestacion: junta plantillas, correo y almacen.

Lo usan tanto la linea de comandos como el servidor local, para que las dos puertas de
entrada se comporten exactamente igual.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import almacen
import correo
import plantillas


def sugerir(cfg: dict, email: str, texto_post: str = "") -> dict:
    """Adivina idioma, puesto y empresa a partir del post y del mail. Todo es editable
    despues: son sugerencias para ahorrar tipeo, no verdades."""
    return {
        "idioma": plantillas.detectar_idioma(texto_post),
        "puesto": plantillas.detectar_puesto(texto_post),
        "empresa": plantillas.detectar_empresa(email),
    }


def previsualizar(
    cfg: dict,
    con: sqlite3.Connection,
    destino: str,
    recruiter: str = "",
    empresa: str = "",
    puesto: str = "",
    idioma: str = "es",
) -> dict:
    """Arma todo lo que se enviaria, sin enviar nada. Es lo que ve el modal antes del boton."""
    asunto, cuerpo = plantillas.armar(cfg, idioma, recruiter, empresa, puesto)
    ruta_cv = plantillas.ruta_cv(cfg, idioma)

    previos = almacen.buscar_por_email(con, destino)
    return {
        "destino": destino,
        "asunto": asunto,
        "cuerpo": cuerpo,
        "cv": ruta_cv.name,
        "etiqueta": plantillas.etiqueta(cfg, empresa),
        "duplicados": [
            {
                "fecha": p["enviada_en"][:10],
                "empresa": p["empresa"],
                "puesto": p["puesto"],
            }
            for p in previos
        ],
    }


def postular(
    cfg: dict,
    con: sqlite3.Connection,
    destino: str,
    recruiter: str = "",
    empresa: str = "",
    puesto: str = "",
    idioma: str = "es",
    texto_post: str = "",
    url_post: str = "",
    autor_post: str = "",
) -> dict:
    """Envia, registra y etiqueta. Devuelve el detalle de lo que efectivamente paso."""
    destino = (destino or "").strip()
    if "@" not in destino:
        raise ValueError(f"'{destino}' no parece una direccion de mail")

    vista = previsualizar(cfg, con, destino, recruiter, empresa, puesto, idioma)
    marca = correo.nueva_marca()

    mensaje = correo.armar_mensaje(
        cfg,
        destino=destino,
        asunto=vista["asunto"],
        cuerpo=vista["cuerpo"],
        ruta_cv=plantillas.ruta_cv(cfg, idioma),
        marca=marca,
    )
    correo.enviar(cfg, mensaje)

    # A partir de aca el mail ya salio: nada de lo que siga puede considerarse un fracaso
    # del envio. Registramos primero, por si el etiquetado se cuelga.
    id_fila = almacen.guardar(
        con,
        email=destino,
        recruiter=recruiter,
        empresa=empresa,
        puesto=puesto,
        idioma=idioma,
        asunto=vista["asunto"],
        marca=marca,
        etiqueta=vista["etiqueta"],
        # El post entero: es lo que dentro de un mes va a decir de que era esta oferta.
        texto_post=texto_post,
        url_post=url_post,
        autor_post=autor_post,
    )

    try:
        etiquetada, hilo = correo.etiquetar(cfg, marca, destino, vista["etiqueta"])
    except Exception:
        etiquetada, hilo = False, ""
    almacen.marcar_etiquetada(con, id_fila, etiquetada)
    if hilo:
        almacen.guardar_hilo(con, id_fila, hilo)

    return {
        "ok": True,
        "id": id_fila,
        "destino": destino,
        "asunto": vista["asunto"],
        "cv": vista["cv"],
        "etiqueta": vista["etiqueta"],
        "etiquetada": etiquetada,
        "duplicados": vista["duplicados"],
    }


def detectar_respuestas(cfg: dict, con: sqlite3.Connection, buzon=None) -> dict:
    """Busca respuestas a las postulaciones pendientes, las marca y las etiqueta.

    El `buzon` se puede inyectar: los tests le pasan un doble y asi el emparejamiento se
    prueba sin tocar la casilla real.
    """
    if buzon is not None:
        return _emparejar(cfg, con, buzon)
    with correo.Buzon(cfg) as bz:
        return _emparejar(cfg, con, bz)


def _emparejar(cfg: dict, con: sqlite3.Connection, buzon) -> dict:
    pendientes = almacen.sin_responder(con)
    propio = cfg["remitente"]["email"].strip().lower()
    nuevas = []

    if pendientes:
        buzon.abrir(buzon.carpeta_todos())

    for fila in pendientes:
        # Por hilo es lo preciso: encuentra la respuesta aunque conteste otra persona de la
        # empresa desde otra direccion. Sin hilo guardado, caemos al remitente original.
        uids = buzon.uids_del_hilo(fila["hilo"]) if fila["hilo"] else []
        if not uids:
            uids = buzon.uids_de(fila["email"], _fecha_de(fila["enviada_en"]))

        for uid in uids:
            cabeceras = buzon.cabeceras(uid)
            if propio in (cabeceras.get("from") or "").lower():
                continue  # es nuestro propio mensaje dentro del hilo

            cuando = _fecha_del_mensaje(cabeceras.get("date"))
            buzon.crear_etiqueta(fila["etiqueta"])
            # Etiquetar tambien la respuesta: asi el dato se ve en la bandeja sin depender
            # de como Gmail agrupe las conversaciones.
            buzon.copiar(uid, fila["etiqueta"])
            almacen.marcar_respondida(con, fila["id"], cuando)
            nuevas.append({
                "id": fila["id"],
                "email": fila["email"],
                "empresa": fila["empresa"],
                "puesto": fila["puesto"],
                "de": cabeceras.get("from", ""),
                "cuando": cuando,
            })
            break

    return {"ok": True, "revisadas": len(pendientes), "nuevas": nuevas}


def _fecha_de(iso: str) -> datetime:
    try:
        return datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return datetime.now() - timedelta(days=365)


def _fecha_del_mensaje(cabecera: str | None) -> str:
    """La fecha del mail que llego. Si no se puede leer, la de ahora: perder el dato exacto
    no justifica perder el registro de que hubo respuesta."""
    if cabecera:
        try:
            return parsedate_to_datetime(cabecera).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    return datetime.now().isoformat(timespec="seconds")
