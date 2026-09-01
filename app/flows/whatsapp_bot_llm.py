"""Construcción del system prompt del bot y parseo de la salida del LLM.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — acá vive
todo lo que es puramente "texto que entra/sale del LLM", sin tocar CRM,
Waha ni el `ConversationStore`. `whatsapp_bot.py` reexporta lo que sus tests
importan directo (`_parse_llm_output`, `LlmTurn`) para no romper esos paths.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.crm.protocol import PropertyListing
from app.forms.models import PROPERTY_TYPES

AFFIRMATION_RE = re.compile(
    r"^(s[ií]|correcto|exacto|as[ií] es|as[ií] mismo|eso es|confirmo|claro que s[ií])\W*$",
    re.IGNORECASE,
)

_OUTPUT_FORMAT_INSTRUCTIONS = (
    "\n\nFormato de salida (obligatorio, sin excepción): responda ÚNICAMENTE "
    "con un objeto JSON válido, sin texto antes ni después, con esta forma "
    'exacta:\n{"reply": "<el mensaje que se le manda a la persona por '
    'WhatsApp>", "fields": {"property_type": <uno de ' + repr(list(PROPERTY_TYPES)) + " o null>, "
    '"address": <string o null>, "sector_zone_city": <string o null>, '
    '"expected_sale_price": <número entero o null>, "registration_number": '
    '<string o null>}, "client_full_name": <nombre y apellido de la persona, '
    'string o null>, "client_phone": <teléfono de la persona, string o '
    'null>, "proposed_full_name": <string o null>, "proposed_phone": '
    '<string o null>, "handoff_requested": <true o false>}\n'
    'En "fields" solo van los datos que la persona haya mencionado o '
    'confirmado en ESTE turno — todo lo demás va en null, aunque ya lo '
    "sepamos de antes. No repita en \"fields\" un dato que ya aparece en la "
    'lista de "Datos que ya tenemos" salvo que la persona lo esté '
    "corrigiendo. Lo mismo aplica a \"client_full_name\" y \"client_phone\": "
    "solo van si la persona los dijo/confirmó en ESTE turno, null en "
    "cualquier otro caso — incluyendo cuando ya están confirmados.\n"
    '"proposed_full_name" y "proposed_phone" van cuando, en "reply", usted '
    "le está preguntando a la persona si un nombre o teléfono es correcto "
    "(sea porque la persona lo acaba de escribir, o porque usted se lo "
    "propuso a partir del perfil de WhatsApp o el número del chat) — van "
    "con el valor exacto que usted está proponiéndole confirmar, en "
    "cualquier otro turno van en null.\n"
    '"handoff_requested" es true únicamente cuando "reply" es el mensaje en '
    "el que usted le avisa a la persona que la va a conectar con un asesor "
    '(según las condiciones ya indicadas) — en cualquier otro caso, false.'
)


def _known_fields_block(listing: PropertyListing) -> str:
    def fmt(value: Any) -> str:
        return str(value) if value not in (None, "") else "(vacío)"

    return (
        "Datos que ya tenemos del inmueble (no vuelva a preguntar por lo "
        "que ya está lleno, solo confírmelo si la persona lo corrige):\n"
        f"- Tipo de inmueble: {fmt(listing.property_type)}\n"
        f"- Dirección: {fmt(listing.address)}\n"
        f"- Sector/zona/ciudad: {fmt(listing.sector_zone_city)}\n"
        f"- Precio de venta esperado: {fmt(listing.expected_sale_price)}\n"
        f"- Matrícula inmobiliaria: {fmt(listing.registration_number)}"
    )


def _identity_block(
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    def fmt(value: str | None) -> str:
        return value if value else "(no confirmado)"

    lines = [
        "Datos de contacto de la persona:",
        f"- Nombre completo: {fmt(confirmed_name)}",
        f"- Teléfono: {fmt(confirmed_phone)}",
    ]
    if confirmed_name is None and candidate_name:
        lines.append(
            f"- Nombre de perfil de WhatsApp (sin confirmar, pregúntele si es el suyo): {candidate_name}"
        )
    if confirmed_phone is None and candidate_phone:
        lines.append(
            f"- Teléfono detectado del chat (sin confirmar, pregúntele si es correcto): {candidate_phone}"
        )
    return "\n".join(lines)


def _build_system_prompt(
    base_prompt: str,
    listing: PropertyListing,
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    return (
        f"{base_prompt}\n\n{_identity_block(confirmed_name, confirmed_phone, candidate_name, candidate_phone)}"
        f"\n\n{_known_fields_block(listing)}{_OUTPUT_FORMAT_INSTRUCTIONS}"
    )


def _awaiting_acceptance_note() -> str:
    return (
        "\n\nYa se le explicó el proceso a la persona (mensaje + nota de voz) y se le "
        "preguntó si desea continuar. Si su mensaje no es una confirmación clara, "
        "respóndale su duda u objeción y termine reafirmando esa misma pregunta — no le "
        "pida todavía los datos del inmueble."
    )


def _as_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_property_listing(data: dict[str, Any]) -> PropertyListing:
    property_type = data.get("property_type")
    if property_type not in PROPERTY_TYPES:
        property_type = None

    expected_sale_price = data.get("expected_sale_price")
    try:
        expected_sale_price = int(expected_sale_price) if expected_sale_price not in (None, "") else None
    except (TypeError, ValueError):
        expected_sale_price = None

    return PropertyListing(
        property_type=property_type,
        address=_as_text(data.get("address")),
        sector_zone_city=_as_text(data.get("sector_zone_city")),
        expected_sale_price=expected_sale_price,
        registration_number=_as_text(data.get("registration_number")),
    )


@dataclass(frozen=True)
class LlmTurn:
    """Resultado de parsear un turno de respuesta del LLM."""

    reply: str
    listing: PropertyListing
    handoff_requested: bool = False
    client_full_name: str | None = None
    client_phone: str | None = None
    proposed_full_name: str | None = None
    proposed_phone: str | None = None


def _parse_llm_output(raw: str) -> LlmTurn:
    """Parsea la salida del LLM (JSON `{"reply": ..., "fields": ..., "handoff_requested": ...,
    "client_full_name": ..., "client_phone": ...}`).

    Si el LLM no devolvió JSON válido (algún proveedor puede ignorar la
    instrucción), se trata todo el texto como la respuesta a mandar, no se
    actualiza ningún campo y no se pide handoff ni identidad — nunca se
    rompe la conversación por esto.
    """
    data: Any = None
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
            except ValueError:
                data = None

    if not isinstance(data, dict):
        return LlmTurn(reply=raw.strip(), listing=PropertyListing())

    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return LlmTurn(reply=raw.strip(), listing=PropertyListing())

    fields_data = data.get("fields")
    fields_data = fields_data if isinstance(fields_data, dict) else {}

    return LlmTurn(
        reply=reply.strip(),
        listing=_to_property_listing(fields_data),
        handoff_requested=data.get("handoff_requested") is True,
        client_full_name=_as_text(data.get("client_full_name")),
        client_phone=_as_text(data.get("client_phone")),
        proposed_full_name=_as_text(data.get("proposed_full_name")),
        proposed_phone=_as_text(data.get("proposed_phone")),
    )
