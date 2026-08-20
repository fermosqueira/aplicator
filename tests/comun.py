"""Fixtures compartidos.

Los tests no tocan ni config.json ni los CV reales: arman su propia carpeta temporal
con plantillas y PDF de mentira. Asi corren igual en esta maquina que en CI, donde
esos archivos no existen porque son datos personales y no viajan al repositorio.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

PLANTILLA_ES = "Hola {recruiter}! Me postulo a {puesto} en {empresa}.\nPortfolio: {portfolio}\n"
PLANTILLA_EN = "Hi {recruiter}! I apply for {puesto} at {empresa}.\nPortfolio: {portfolio}\n"

# El segundo tipo de mail: no nombra el puesto, a proposito. Sirve para verificar que
# armar() tolera una plantilla que no usa todos los huecos.
ESPONTANEA_ES = "Hola {recruiter}! Les acerco mi CV para {empresa}.\nPortfolio: {portfolio}\n"
ESPONTANEA_EN = "Hi {recruiter}! Sharing my CV with {empresa}.\nPortfolio: {portfolio}\n"

# Un PDF valido minimo: alcanza para que el codigo lo lea y lo adjunte.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def armar_config(carpeta: Path) -> dict:
    """Escribe las plantillas y los CV falsos, y devuelve una config que apunta ahi."""
    (carpeta / "es.txt").write_text(PLANTILLA_ES, encoding="utf-8")
    (carpeta / "en.txt").write_text(PLANTILLA_EN, encoding="utf-8")
    (carpeta / "es-esp.txt").write_text(ESPONTANEA_ES, encoding="utf-8")
    (carpeta / "en-esp.txt").write_text(ESPONTANEA_EN, encoding="utf-8")
    (carpeta / "cv-es.pdf").write_bytes(PDF)
    (carpeta / "cv-en.pdf").write_bytes(PDF)

    return {
        "_base": str(carpeta),
        "remitente": {
            "email": "prueba@ejemplo.com",
            "nombre": "Nombre Apellido",
            "rol": "QA Analyst",
            "app_password": "clave-de-mentira",
        },
        "smtp": {"host": "smtp.invalido", "puerto": 465},
        "imap": {"host": "imap.invalido", "puerto": 993},
        "portfolio": {"base": "https://ejemplo.test", "sufijos": {"es": "/es", "en": "/en"}},
        "linkedin": "https://www.linkedin.com/in/ejemplo",
        "etiqueta_padre": "Postulaciones",
        "idiomas": {
            "es": {
                "cv": "cv-es.pdf",
                "sin_puesto": "QA", "sin_empresa": "la empresa",
                "plantillas": {
                    "directa": {"archivo": "es.txt",
                                "asunto": "Postulación {puesto} - {remitente}"},
                    "espontanea": {"archivo": "es-esp.txt",
                                   "asunto": "CV QA - {remitente}"},
                },
            },
            "en": {
                "cv": "cv-en.pdf",
                "sin_puesto": "QA", "sin_empresa": "your company",
                "plantillas": {
                    "directa": {"archivo": "en.txt",
                                "asunto": "Application for {puesto} - {remitente}"},
                    "espontanea": {"archivo": "en-esp.txt",
                                   "asunto": "QA CV - {remitente}"},
                },
            },
        },
        "servidor": {
            "puerto": 0,
            "token": "token-de-prueba",
            "origenes": ["https://www.linkedin.com"],
        },
    }
