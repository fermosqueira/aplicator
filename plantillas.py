"""Carga de configuracion, deteccion de idioma y armado del asunto y el cuerpo del mail."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUTA_CONFIG = BASE / "config.json"

# Palabras funcionales frecuentes en avisos de trabajo. Sirven para adivinar el idioma
# del post: no hace falta nada mas sofisticado para elegir entre dos opciones.
PISTAS = {
    "es": {
        "de", "la", "el", "que", "en", "para", "con", "los", "las", "una", "por", "del",
        "se", "su", "como", "mas", "buscamos", "trabajo", "experiencia", "empresa",
        "busqueda", "conocimientos", "requisitos", "puesto", "sumate", "somos", "anos",
    },
    "en": {
        "the", "and", "of", "to", "for", "with", "you", "we", "our", "in", "is", "are",
        "will", "experience", "team", "role", "position", "requirements", "skills",
        "looking", "join", "years", "hiring",
    },
}

# Titulos de QA que solemos ver en los avisos, de mas especifico a menos: el orden importa
# porque gana la primera coincidencia y "QA Automation" es mejor dato que "QA" a secas.
PUESTOS = [
    "QA Automation Engineer", "QA Automation", "Automation Engineer", "SDET",
    "Analista de QA", "Analista QA", "QA Analyst", "QA Engineer", "QA Manual",
    "Manual Tester", "Automation Tester", "Test Engineer", "Quality Assurance",
    "Tester", "QA",
]


# Los dos cuerpos de mail. "directa" es postularse a la busqueda publicada; "espontanea" es
# acercar el CV a una empresa cuya busqueda no es de QA, para quedar en su base de datos. El
# tipo es un eje aparte del idioma: el CV adjunto es el mismo de QA en los dos casos.
TIPOS = ("directa", "espontanea")


def normalizar(cfg: dict) -> dict:
    """Lleva la config a la forma con `plantillas` por tipo, venga como venga.

    Las versiones anteriores tenian `plantilla` y `asunto` sueltos en cada idioma. Se
    convierten en el tipo "directa", que es lo que efectivamente eran, asi nadie tiene que
    reescribir su config.json para seguir usando lo de siempre.

    Vive aparte de cargar_config porque los tests arman su config a mano sin pasar por ahi:
    los dos caminos tienen que normalizar igual, o estarian probando formas distintas.
    """
    for ajustes in cfg.get("idiomas", {}).values():
        if "plantillas" not in ajustes and "plantilla" in ajustes:
            ajustes["plantillas"] = {
                "directa": {
                    "archivo": ajustes["plantilla"],
                    "asunto": ajustes.get("asunto", ""),
                }
            }
    return cfg


def cargar_config(ruta: Path | None = None, exigir_clave: bool = True) -> dict:
    """Lee config.json y valida que este completo antes de que algo falle mas adelante.

    Con exigir_clave=False se puede previsualizar un mail sin tener credenciales cargadas:
    armar el texto no necesita hablar con Gmail.
    """
    ruta = ruta or RUTA_CONFIG
    if not ruta.exists():
        raise FileNotFoundError(f"Falta {ruta.name} en {ruta.parent}.")

    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    # Las plantillas y los CV se buscan al lado del config, no al lado de este archivo.
    # Asi los tests pueden armar una carpeta propia con fixtures y no dependen de que
    # existan los PDF reales, que no viajan al repositorio.
    cfg["_base"] = str(ruta.parent)

    clave = cfg.get("remitente", {}).get("app_password", "")
    if exigir_clave and (not clave or clave.startswith("PEGA_ACA")):
        raise ValueError(
            "El app_password de config.json todavia esta sin completar.\n"
            "Generá uno en https://myaccount.google.com/apppasswords y pegalo ahi."
        )
    return normalizar(cfg)


def carpeta(cfg: dict) -> Path:
    """Donde viven las plantillas y los CV de esta configuracion."""
    return Path(cfg.get("_base", BASE))


def sin_acentos(texto: str) -> str:
    """'Telefónica' -> 'Telefonica'. Necesario para las etiquetas IMAP, que sufren con UTF-8."""
    desarmado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in desarmado if unicodedata.category(c) != "Mn")


def detectar_idioma(texto: str) -> str:
    """Cuenta palabras funcionales de cada idioma. Ante la duda, español."""
    palabras = set(re.findall(r"[a-záéíóúñü]+", sin_acentos(texto or "").lower()))
    puntajes = {idioma: len(palabras & pistas) for idioma, pistas in PISTAS.items()}
    return "en" if puntajes["en"] > puntajes["es"] else "es"


def detectar_puesto(texto: str) -> str:
    """Busca un titulo de QA conocido dentro del texto del post. Devuelve '' si no encuentra."""
    plano = sin_acentos(texto or "").lower()
    for puesto in PUESTOS:
        if sin_acentos(puesto).lower() in plano:
            return puesto
    return ""


# Proveedores de correo gratuito. Se comparan por la primera etiqueta del dominio y no por
# el dominio completo, asi 'gmail.com', 'gmail.com.ar' y el erroneo 'gmail.co' caen todos.
PROVEEDORES = {
    "gmail", "googlemail", "hotmail", "outlook", "yahoo", "live", "icloud", "proton",
    "protonmail", "aol", "gmx", "zoho", "yandex", "msn", "me", "mail",
}

# Dominios de proveedores bien escritos. Sirven de referencia para detectar los que se
# les parecen por una sola letra: 'gmail.co' en vez de 'gmail.com'.
DOMINIOS_CONOCIDOS = (
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "yahoo.com",
    "live.com", "icloud.com", "protonmail.com", "proton.me", "aol.com",
)


def detectar_empresa(email: str) -> str:
    """Deriva un nombre de empresa del dominio del mail. 'rrhh@acme-corp.com' -> 'Acme Corp'."""
    if "@" not in (email or ""):
        return ""
    dominio = email.split("@", 1)[1].lower()

    # Un correo gratuito no dice nada sobre la empresa: mejor vacio que un "Gmail" de etiqueta.
    partes = [p for p in dominio.split(".") if p != "www"]
    if not partes or partes[0] in PROVEEDORES:
        return ""

    utiles = [p for p in partes if p not in {"com", "ar", "net", "org", "io", "co"}]
    if not utiles:
        return ""
    return utiles[0].replace("-", " ").replace("_", " ").title()


def _casi_igual(a: str, b: str) -> bool:
    """True si se pasa de a a b con un solo error de tipeo.

    Cuenta como un error agregar, sacar o cambiar un caracter, y tambien intercambiar dos
    contiguos: 'gmial' por 'gmail' es el typo mas comun de todos y en distancia de edicion
    clasica figura como dos operaciones, asi que hay que contemplarlo aparte.
    """
    if a == b:
        return False
    if abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        distintos = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(distintos) == 1:
            return True
        # Transposicion: dos posiciones contiguas, cruzadas entre si.
        if len(distintos) == 2:
            i, j = distintos
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]
        return False

    corta, larga = (a, b) if len(a) < len(b) else (b, a)
    return any(larga[:i] + larga[i + 1:] == corta for i in range(len(larga)))


def dominio_sospechoso(email: str) -> str:
    """Si el dominio se parece por una letra a un proveedor conocido, devuelve el correcto.

    Nace de un caso real: un mail salio a '@gmail.co' y reboto con Null MX. La postulacion
    se dio por enviada y nunca la leyo nadie. Un error de una letra en una direccion es
    invisible al revisar el borrador, pero cuesta una oportunidad entera.
    """
    if "@" not in (email or ""):
        return ""
    dominio = email.split("@", 1)[1].lower().strip()
    if dominio in DOMINIOS_CONOCIDOS:
        return ""
    for conocido in DOMINIOS_CONOCIDOS:
        if _casi_igual(dominio, conocido):
            return conocido
    return ""


def url_portfolio(cfg: dict, idioma: str) -> str:
    """El portfolio es bilingue: mandamos el link en el mismo idioma que el mail."""
    portfolio = cfg["portfolio"]
    return portfolio["base"] + portfolio["sufijos"].get(idioma, "")


def firma(cfg: dict, idioma: str) -> str:
    """Bloque al pie. Viaja en todos los mensajes del hilo, tambien en las respuestas."""
    remitente = cfg["remitente"]
    return "\n".join([
        "--",
        f"{remitente['nombre']} · {remitente['rol']}",
        f"Portfolio: {url_portfolio(cfg, idioma)}",
        f"LinkedIn: {cfg['linkedin']}",
        remitente["email"],
    ])


def _prolijo(texto: str) -> str:
    """Repara los huecos que deja un placeholder vacio: 'Hola !' -> 'Hola!'."""
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" +([,.!?;:])", r"\1", texto)
    return re.sub(r"[ \t]+\n", "\n", texto)


def elegir_plantilla(cfg: dict, idioma: str, tipo: str) -> dict:
    """El {archivo, asunto} de esa combinacion de idioma y tipo, o un error que dice como
    arreglarlo. ValueError y no KeyError: el servidor lo convierte en un 400 con el texto
    adentro, asi que el mensaje termina en la pantalla del usuario."""
    if idioma not in cfg["idiomas"]:
        raise ValueError(f"Idioma '{idioma}' desconocido. Usá 'es' o 'en'.")

    disponibles = cfg["idiomas"][idioma].get("plantillas") or {}
    if tipo not in disponibles:
        tiene = ", ".join(sorted(disponibles)) or "ninguna"
        raise ValueError(
            f"No hay plantilla '{tipo}' para el idioma '{idioma}' (hay: {tiene}). "
            f"Agregala en config.json bajo idiomas.{idioma}.plantillas, con 'archivo' y 'asunto'."
        )
    return disponibles[tipo]


def armar(
    cfg: dict,
    idioma: str,
    recruiter: str,
    empresa: str,
    puesto: str,
    tipo: str = "directa",
) -> tuple[str, str]:
    """Devuelve (asunto, cuerpo) ya rellenados y listos para enviar."""
    eleccion = elegir_plantilla(cfg, idioma, tipo)
    ajustes = cfg["idiomas"][idioma]

    puesto = (puesto or "").strip() or ajustes["sin_puesto"]
    empresa = (empresa or "").strip() or ajustes["sin_empresa"]
    recruiter = (recruiter or "").strip()

    plantilla = (carpeta(cfg) / eleccion["archivo"]).read_text(encoding="utf-8")
    # Se pasan siempre los cuatro huecos aunque la plantilla no los use: el cuerpo espontaneo
    # no nombra el puesto, y format() ignora sin quejarse lo que le sobra.
    cuerpo = plantilla.format(
        recruiter=recruiter,
        puesto=puesto,
        empresa=empresa,
        portfolio=url_portfolio(cfg, idioma),
    )
    cuerpo = _prolijo(cuerpo).rstrip() + "\n\n" + firma(cfg, idioma)

    asunto = eleccion["asunto"].format(puesto=puesto, remitente=cfg["remitente"]["nombre"])
    return asunto, cuerpo


def etiqueta(cfg: dict, empresa: str) -> str:
    """'Postulaciones/Acme'. Sin acentos ni barras: IMAP usa la barra para anidar."""
    limpia = sin_acentos((empresa or "").strip()) or "Sin empresa"
    limpia = re.sub(r"[/\\\"]", " ", limpia)
    limpia = re.sub(r"\s+", " ", limpia).strip()
    return f"{cfg['etiqueta_padre']}/{limpia}"


def ruta_cv(cfg: dict, idioma: str) -> Path:
    ruta = carpeta(cfg) / cfg["idiomas"][idioma]["cv"]
    if not ruta.exists():
        raise FileNotFoundError(f"No encuentro el CV: {ruta}")
    return ruta
