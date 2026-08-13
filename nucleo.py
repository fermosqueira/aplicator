"""Orquestacion: junta plantillas, correo y almacen.

Lo usan tanto la linea de comandos como el servidor local, para que las dos puertas de
entrada se comporten exactamente igual.
"""

from __future__ import annotations

import sqlite3

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
    )

    try:
        etiquetada = correo.etiquetar(cfg, marca, destino, vista["etiqueta"])
    except Exception:
        etiquetada = False
    almacen.marcar_etiquetada(con, id_fila, etiquetada)

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
