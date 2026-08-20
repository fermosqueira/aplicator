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


# Ventana del anti-duplicado. Dos mails identicos seguidos al mismo recruiter se leen como
# spam del otro lado. La extension ya no puede mandarlos dos veces, pero esta guarda no
# depende de que el navegador se porte bien: paso una vez y costo dos mails a la misma
# direccion con 75 segundos de diferencia.
SEGUNDOS_ANTIDUPLICADO = 120


def sugerir(cfg: dict, email: str, texto_post: str = "") -> dict:
    """Adivina idioma, puesto y empresa a partir del post y del mail. Todo es editable
    despues: son sugerencias para ahorrar tipeo, no verdades."""
    puesto = plantillas.detectar_puesto(texto_post)
    return {
        "idioma": plantillas.detectar_idioma(texto_post),
        "puesto": puesto,
        "empresa": plantillas.detectar_empresa(email),
        # Si el post no nombra ningun titulo de QA, la busqueda no es para este perfil: lo
        # que corresponde es acercar el CV para futuras aperturas, no postularse a esa
        # vacante. Se sugiere nomas; el usuario confirma antes de mandar.
        "tipo": "directa" if puesto else "espontanea",
    }


def previsualizar(
    cfg: dict,
    con: sqlite3.Connection,
    destino: str,
    recruiter: str = "",
    empresa: str = "",
    puesto: str = "",
    idioma: str = "es",
    tipo: str = "directa",
) -> dict:
    """Arma todo lo que se enviaria, sin enviar nada. Es lo que ve el modal antes del boton."""
    asunto, cuerpo = plantillas.armar(cfg, idioma, recruiter, empresa, puesto, tipo)
    ruta_cv = plantillas.ruta_cv(cfg, idioma)

    avisos = []
    parecido = plantillas.dominio_sospechoso(destino)
    if parecido:
        avisos.append(
            f"El dominio de <b>{destino}</b> se parece a <b>{parecido}</b> por una sola letra. "
            f"Si está mal, el mail rebota y la postulación se pierde sin que te enteres."
        )

    previos = almacen.buscar_por_email(con, destino)
    return {
        "destino": destino,
        "asunto": asunto,
        "cuerpo": cuerpo,
        "cv": ruta_cv.name,
        "etiqueta": plantillas.etiqueta(cfg, empresa),
        "tipo": tipo,
        "avisos": avisos,
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
    tipo: str = "directa",
    texto_post: str = "",
    url_post: str = "",
    autor_post: str = "",
    etiquetar_ahora: bool = True,
) -> dict:
    """Envia, registra y (si se pide) etiqueta. Devuelve el detalle de lo que paso.

    Con etiquetar_ahora=False vuelve apenas el mail salio y quedo registrado, sin tocar IMAP.
    Etiquetar abre una segunda conexion y reintenta buscar la copia en Enviados con esperas
    crecientes: son entre 5 y 20 segundos de contabilidad, despues de que el mail ya se fue.
    El servidor la deja para un hilo de fondo y contesta antes; la CLI la hace en el momento
    porque su salida informa si la etiqueta se aplico.
    """
    destino = (destino or "").strip()
    if "@" not in destino:
        raise ValueError(f"'{destino}' no parece una direccion de mail")

    vista = previsualizar(cfg, con, destino, recruiter, empresa, puesto, idioma, tipo)

    # Antes de mandar nada: si es el mismo mail al mismo destinatario hace un rato, no sale.
    if almacen.enviada_hace_poco(con, destino, vista["asunto"], SEGUNDOS_ANTIDUPLICADO):
        raise ValueError(
            f"Ya le mandaste esta misma postulación a {destino} hace menos de "
            f"{SEGUNDOS_ANTIDUPLICADO // 60} minutos. No se envió de nuevo."
        )

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
        tipo=tipo,
        asunto=vista["asunto"],
        marca=marca,
        etiqueta=vista["etiqueta"],
        # El post entero: es lo que dentro de un mes va a decir de que era esta oferta.
        texto_post=texto_post,
        url_post=url_post,
        autor_post=autor_post,
    )

    respuesta = {
        "ok": True,
        "id": id_fila,
        "destino": destino,
        "asunto": vista["asunto"],
        "cv": vista["cv"],
        "etiqueta": vista["etiqueta"],
        "tipo": tipo,
        "marca": marca,
        "duplicados": vista["duplicados"],
    }

    if etiquetar_ahora:
        respuesta["etiquetada"] = etiquetar_pendiente(
            cfg, con, id_fila, marca, destino, vista["etiqueta"]
        )
    return respuesta


def etiquetar_pendiente(
    cfg: dict,
    con: sqlite3.Connection,
    id_fila: int,
    marca: str,
    destino: str,
    etiqueta: str,
) -> bool:
    """Le pone la etiqueta al mensaje enviado y guarda el id de hilo.

    Es lo lento del envio y lo que menos urge: el mail ya salio. Si falla, la postulacion
    igual quedo registrada, y el detector de respuestas sabe caer a buscar por remitente
    cuando no hay hilo guardado.
    """
    try:
        etiquetada, hilo = correo.etiquetar(cfg, marca, destino, etiqueta)
    except Exception:
        etiquetada, hilo = False, ""
    almacen.marcar_etiquetada(con, id_fila, etiquetada)
    if hilo:
        almacen.guardar_hilo(con, id_fila, hilo)
    return etiquetada


def detectar_respuestas(cfg: dict, con: sqlite3.Connection, buzon=None) -> dict:
    """Busca respuestas a las postulaciones pendientes, las marca y las etiqueta.

    El `buzon` se puede inyectar: los tests le pasan un doble y asi el emparejamiento se
    prueba sin tocar la casilla real.
    """
    # Sin pendientes no hay nada que mirar, y conviene saberlo antes de abrir la conexion:
    # esto ahora corre solo cada media hora, y no tiene sentido loguearse a Gmail para
    # descubrir que no habia trabajo.
    if not almacen.sin_responder(con):
        return {"ok": True, "revisadas": 0, "nuevas": [], "rebotes": []}

    if buzon is not None:
        return _emparejar(cfg, con, buzon)
    with correo.Buzon(cfg) as bz:
        return _emparejar(cfg, con, bz)


def _clasificar(buzon, uids, propio) -> tuple[tuple | None, tuple | None]:
    """Separa lo que hay en el hilo en (respuesta de una persona, rebote del servidor).

    Se recorre todo antes de decidir en vez de cortar en el primer mensaje ajeno: un hilo
    puede tener un rebote de un intento y despues una respuesta de verdad, y ahi manda la
    respuesta.
    """
    respuesta = rebote = None
    for uid in uids:
        cabeceras = buzon.cabeceras(uid)
        de = (cabeceras.get("from") or "").lower()
        if propio in de:
            continue  # es nuestro propio mensaje dentro del hilo
        if correo.es_rebote(de):
            rebote = rebote or (uid, cabeceras)
            continue
        respuesta = (uid, cabeceras)
        break
    return respuesta, rebote


def _emparejar(cfg: dict, con: sqlite3.Connection, buzon) -> dict:
    pendientes = almacen.sin_responder(con)
    propio = cfg["remitente"]["email"].strip().lower()
    nuevas, rebotes = [], []

    if pendientes:
        buzon.abrir(buzon.carpeta_todos())

    for fila in pendientes:
        # Por hilo es lo preciso: encuentra la respuesta aunque conteste otra persona de la
        # empresa desde otra direccion. Sin hilo guardado, caemos al remitente original.
        uids = buzon.uids_del_hilo(fila["hilo"]) if fila["hilo"] else []
        if not uids:
            uids = buzon.uids_de(fila["email"], _fecha_de(fila["enviada_en"]))

        respuesta, rebote = _clasificar(buzon, uids, propio)
        if not respuesta and not rebote:
            continue

        uid, cabeceras = respuesta or rebote
        cuando = _fecha_del_mensaje(cabeceras.get("date"))
        buzon.crear_etiqueta(fila["etiqueta"])
        # Etiquetar tambien el mensaje que llego: asi el dato se ve en la bandeja sin
        # depender de como Gmail agrupe las conversaciones. Tambien el rebote, que es
        # justo el mensaje que uno quiere encontrar despues.
        buzon.copiar(uid, fila["etiqueta"])

        detalle = {
            "id": fila["id"],
            "email": fila["email"],
            "empresa": fila["empresa"],
            "puesto": fila["puesto"],
            "de": cabeceras.get("from", ""),
            "cuando": cuando,
        }
        if respuesta:
            almacen.marcar_respondida(con, fila["id"], cuando)
            nuevas.append(detalle)
        else:
            almacen.marcar_rebotada(con, fila["id"], cuando)
            rebotes.append(detalle)

    return {"ok": True, "revisadas": len(pendientes), "nuevas": nuevas, "rebotes": rebotes}


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
