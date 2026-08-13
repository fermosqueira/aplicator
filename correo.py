"""Armado del mail, envio por SMTP y etiquetado de la copia en Enviados por IMAP."""

from __future__ import annotations

import imaplib
import re
import smtplib
import ssl
import time
import uuid
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

# Gmail reescribe el Message-ID de los mensajes que salen por su SMTP, asi que no sirve
# para reencontrar la copia en Enviados. Las cabeceras X- si las respeta.
CABECERA_MARCA = "X-Aplicador-Id"

# strftime("%b") depende del locale del sistema: en una Windows en español devolveria
# "ago" y el servidor IMAP rechazaria la fecha. Por eso la armamos a mano.
MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def nueva_marca() -> str:
    return uuid.uuid4().hex


def _fecha_imap(fecha: datetime) -> str:
    return f"{fecha.day:02d}-{MESES[fecha.month - 1]}-{fecha.year}"


def armar_mensaje(
    cfg: dict, destino: str, asunto: str, cuerpo: str, ruta_cv: Path, marca: str
) -> EmailMessage:
    """Mail de texto plano con el CV adjunto. Texto plano a proposito: llega mejor y no
    hay forma de que se vea roto en el cliente del otro lado."""
    remitente = cfg["remitente"]

    msg = EmailMessage()
    msg["From"] = formataddr((remitente["nombre"], remitente["email"]))
    msg["To"] = destino
    msg["Subject"] = asunto
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg[CABECERA_MARCA] = marca
    msg.set_content(cuerpo)

    # El recruiter no tiene por que ver el "(es) " con el que ordenamos los archivos aca.
    nombre_visible = re.sub(r"^\((?:es|en)\)\s*", "", ruta_cv.name)
    msg.add_attachment(
        ruta_cv.read_bytes(), maintype="application", subtype="pdf", filename=nombre_visible
    )
    return msg


def enviar(cfg: dict, msg: EmailMessage) -> None:
    """Envia por SMTP. Gmail deja solo la copia en Enviados, no hay que hacer nada extra."""
    remitente = cfg["remitente"]
    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL(cfg["smtp"]["host"], cfg["smtp"]["puerto"], context=contexto) as smtp:
        smtp.login(remitente["email"], remitente["app_password"])
        smtp.send_message(msg)


def _carpeta_enviados(imap: imaplib.IMAP4_SSL) -> str:
    """Ubica Enviados por su flag \\Sent y no por nombre: la cuenta puede estar en español
    ('[Gmail]/Enviados') o en ingles ('[Gmail]/Sent Mail')."""
    ok, lineas = imap.list()
    if ok == "OK":
        for linea in lineas or []:
            texto = linea.decode("utf-8", "replace") if isinstance(linea, bytes) else str(linea)
            if "\\Sent" in texto:
                comillas = re.findall(r'"([^"]*)"', texto)
                if comillas:
                    return f'"{comillas[-1]}"'
    return '"[Gmail]/Sent Mail"'


def _buscar_uid(imap: imaplib.IMAP4_SSL, marca: str, destino: str, intentos: int = 5) -> bytes | None:
    """La copia en Enviados tarda unos segundos en aparecer, asi que reintentamos.

    Primero por nuestra marca; si Gmail no la indexo (su IMAP no siempre busca por
    cabeceras arbitrarias), caemos al destinatario y nos quedamos con el UID mas alto,
    que es el mensaje mas reciente: justo el que acabamos de mandar.
    """
    desde = _fecha_imap(datetime.now() - timedelta(days=1))

    for intento in range(intentos):
        for criterio in (
            ("HEADER", CABECERA_MARCA, f'"{marca}"'),
            ("TO", f'"{destino}"', "SINCE", desde),
        ):
            ok, datos = imap.uid("SEARCH", None, *criterio)
            if ok == "OK" and datos and datos[0].split():
                return datos[0].split()[-1]
        time.sleep(1 + intento)
    return None


def etiquetar(cfg: dict, marca: str, destino: str, etiqueta: str) -> bool:
    """Agrega la etiqueta al mensaje enviado. En Gmail, copiar a una carpeta = etiquetar.

    Devuelve True/False en vez de tirar excepcion: si esto falla el mail ya salio igual,
    y tratarlo como error seria mentir sobre lo que paso.
    """
    remitente = cfg["remitente"]
    contexto = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(cfg["imap"]["host"], cfg["imap"]["puerto"], ssl_context=contexto)
    try:
        imap.login(remitente["email"], remitente["app_password"])

        try:
            imap.create(f'"{etiqueta}"')  # devuelve NO si ya existe, y esta bien
        except imaplib.IMAP4.error:
            pass

        if imap.select(_carpeta_enviados(imap))[0] != "OK":
            return False

        uid = _buscar_uid(imap, marca, destino)
        if not uid:
            return False

        return imap.uid("COPY", uid, f'"{etiqueta}"')[0] == "OK"
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def probar_conexion(cfg: dict) -> list[str]:
    """Chequea SMTP e IMAP sin enviar nada. Para validar el app_password en el setup."""
    remitente = cfg["remitente"]
    contexto = ssl.create_default_context()
    resultados = []

    try:
        with smtplib.SMTP_SSL(cfg["smtp"]["host"], cfg["smtp"]["puerto"], context=contexto) as s:
            s.login(remitente["email"], remitente["app_password"])
        resultados.append("SMTP: OK")
    except Exception as e:
        resultados.append(f"SMTP: FALLA -> {e}")

    try:
        imap = imaplib.IMAP4_SSL(cfg["imap"]["host"], cfg["imap"]["puerto"], ssl_context=contexto)
        imap.login(remitente["email"], remitente["app_password"])
        carpeta = _carpeta_enviados(imap)
        imap.logout()
        resultados.append(f"IMAP: OK (carpeta de enviados: {carpeta})")
    except Exception as e:
        resultados.append(f"IMAP: FALLA -> {e}")

    return resultados
