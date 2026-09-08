"""Parsea el correo de notificación del formulario web ("Quiero Vender/Comprar/Arrendar").

Formato fijo del cuerpo (texto plano, ver ejemplo real en
`app/flows/graph_lead_intake.py`): pares `Etiqueta` / `Valor` en líneas
consecutivas, terminados por una línea `ID de Seguimiento: <uuid>`. El
parser solo extrae y sanitiza — no decide qué tipo de servicio se procesa,
eso es responsabilidad de quien lo llama (`app.flows.graph_lead_intake`).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from app.forms.models import PROPERTY_TYPES
from app.shared.phone import normalize_phone_digits

logger = logging.getLogger(__name__)

_LABELS = {
    "nombre completo": "nombre",
    "correo electronico": "correo",
    "telefono": "telefono",
    "zona / sector / barrio": "zona",
    "tipo de inmueble": "tipo_inmueble",
    "valor estimado": "valor_estimado",
    "mensaje": "mensaje",
}

_TRACKING_ID_RE = re.compile(r"ID de Seguimiento:\s*(\S+)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SERVICE_TYPE_KEYWORDS = {
    "vender": "vender",
    "comprar": "comprar",
    "arrendar": "arrendar",
}

def _normalize(text: str) -> str:
    """Minúsculas, sin tildes, espacios colapsados — para comparar sin importar formato."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip().lower()


_PROPERTY_TYPE_BY_NORMALIZED = {_normalize(name): name for name in PROPERTY_TYPES}


@dataclass(frozen=True)
class ParsedLead:
    """Datos ya sanitizados de un lead extraído del correo del formulario web."""

    service_type: str | None
    nombre: str | None
    correo: str | None
    telefono: str | None
    zona: str | None
    tipo_inmueble: str | None
    valor_estimado: int | None
    mensaje: str | None
    tracking_id: str | None


def parse_lead_email(subject: str, body_text: str) -> ParsedLead:
    """Extrae y sanitiza los campos del correo. No filtra por tipo de servicio."""
    return ParsedLead(
        service_type=_detect_service_type(subject),
        tracking_id=_extract_tracking_id(body_text),
        **_extract_fields(body_text),
    )


def _detect_service_type(subject: str) -> str | None:
    normalized = _normalize(subject)
    for keyword, service_type in _SERVICE_TYPE_KEYWORDS.items():
        if keyword in normalized:
            return service_type
    return None


def _extract_tracking_id(body_text: str) -> str | None:
    match = _TRACKING_ID_RE.search(body_text)
    return match.group(1).strip() if match else None


def _extract_fields(body_text: str) -> dict[str, str | int | None]:
    raw: dict[str, str] = {}
    lines = [line.strip() for line in body_text.splitlines()]

    i = 0
    while i < len(lines) - 1:
        label = _normalize(lines[i])
        key = _LABELS.get(label)
        if key is not None:
            value = lines[i + 1].strip()
            if value:
                raw[key] = value
            i += 2
        else:
            i += 1

    return {
        "nombre": _sanitize_text(raw.get("nombre")),
        "correo": _sanitize_email(raw.get("correo")),
        "telefono": _sanitize_phone(raw.get("telefono")),
        "zona": _sanitize_text(raw.get("zona")),
        "tipo_inmueble": _sanitize_property_type(raw.get("tipo_inmueble")),
        "valor_estimado": _sanitize_price(raw.get("valor_estimado")),
        "mensaje": _sanitize_text(raw.get("mensaje")),
    }


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _sanitize_email(value: str | None) -> str | None:
    cleaned = _sanitize_text(value)
    if cleaned is None:
        return None
    if not _EMAIL_RE.match(cleaned):
        logger.warning("Correo con formato dudoso en lead de formulario web: %r", cleaned)
    return cleaned


def _sanitize_phone(value: str | None) -> str | None:
    cleaned = _sanitize_text(value)
    if cleaned is None:
        return None
    return normalize_phone_digits(cleaned)


def _sanitize_price(value: str | None) -> int | None:
    cleaned = _sanitize_text(value)
    if cleaned is None:
        return None
    digits = re.sub(r"\D", "", cleaned)
    return int(digits) if digits else None


def _sanitize_property_type(value: str | None) -> str | None:
    cleaned = _sanitize_text(value)
    if cleaned is None:
        return None
    matched = _PROPERTY_TYPE_BY_NORMALIZED.get(_normalize(cleaned))
    if matched is not None:
        return matched
    logger.warning("Tipo de inmueble %r no matchea ningún valor de PROPERTY_TYPES, se conserva tal cual", cleaned)
    return cleaned.capitalize()
