"""Construcción del system prompt del bot y parseo de la salida del LLM.

Separado de `whatsapp_bot.py` (límite de 500 líneas del repo) — acá vive
todo lo que es puramente "texto que entra/sale del LLM", sin tocar CRM,
Waha ni el `ConversationStore`. `whatsapp_bot.py` reexporta lo que sus tests
importan directo (`_parse_llm_output`, `LlmTurn`) para no romper esos paths.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.crm.protocol import PropertyListing
from app.forms.models import PROPERTY_TYPES
from app.message_templates import store as templates_store

logger = logging.getLogger(__name__)

AFFIRMATION_RE = re.compile(
    r"^(s[ií]|correcto|exacto|as[ií] es|as[ií] mismo|eso es|confirmo|claro(?: que s[ií])?|"
    r"est[aá] bien|de acuerdo|dale|listo|vale|va|h[aá]gale|perfecto|bueno|ok(?:ay)?)\W*$",
    re.IGNORECASE,
)

NEGATION_RE = re.compile(
    r"^(no(?: gracias| quiero| es necesario| hace falta)?|ahora no|despu[eé]s|luego|m[aá]s tarde)\W*$",
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
    'null>, "handoff_requested": <true o false>, "signed_claim": '
    '<true o false>, "explanation_requested": <true o false>}\n'
    'En "fields" solo van los datos que la persona haya mencionado o '
    'confirmado en ESTE turno — todo lo demás va en null, aunque ya lo '
    "sepamos de antes. No repita en \"fields\" un dato que ya aparece en la "
    'lista de "Datos que ya tenemos" salvo que la persona lo esté '
    'corrigiendo.\n'
    '"client_full_name" y "client_phone" no se guardan hasta que usted '
    "tenga los DOS confirmados a la vez — repórtelos juntos, los dos en el "
    "mismo turno, la primera vez que los tenga completos (así el nombre se "
    "haya confirmado en un turno anterior y el teléfono recién en este: "
    "repita el que ya tenía, no solo el nuevo). Antes de tener ambos, "
    "repórtelos como null. Una vez que la sección \"Datos de contacto de la "
    'persona" ya muestra los dos, no vuelva a repetirlos salvo que la '
    "persona esté corrigiendo alguno.\n"
    '"handoff_requested" es true únicamente cuando "reply" es el mensaje en '
    "el que usted le avisa a la persona que la va a conectar con un asesor "
    '(según las condiciones ya indicadas) — en cualquier otro caso, false.\n'
    '"signed_claim" es true únicamente cuando la persona afirma en ESTE turno '
    'que ya firmó la Autorización de Corretaje (ej. "ya firmé", "ya la firmé", '
    '"listo, firmé eso") — en cualquier otro caso, false.\n'
    '"explanation_requested" es true cuando, en cualquier momento de la '
    "conversación (incluso si antes dijo que no quería), la persona pide "
    "explícitamente que le expliquen el proceso o que le manden el audio — "
    "en cualquier otro caso, false."
)


def _identity_block(
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    def fmt(value: str | None) -> str:
        return value if value else "(no confirmado)"

    def fmt_phone(value: str | None) -> str:
        return f"+{value}" if value else "(no confirmado)"

    lines = [
        "Datos de contacto de la persona:",
        f"- Nombre completo: {fmt(confirmed_name)}",
        f"- Teléfono: {fmt_phone(confirmed_phone)}",
    ]
    if confirmed_name is None and candidate_name:
        lines.append(
            f"- Nombre de perfil de WhatsApp (sin confirmar, pregúntele si es el suyo): {candidate_name}"
        )
    if confirmed_phone is None and candidate_phone:
        lines.append(
            f"- Teléfono detectado del chat (sin confirmar, pregúntele si es correcto): +{candidate_phone}"
        )
    return "\n".join(lines)


def _build_system_prompt(
    base_prompt: str,
    confirmed_name: str | None,
    confirmed_phone: str | None,
    candidate_name: str | None = None,
    candidate_phone: str | None = None,
) -> str:
    return (
        f"{base_prompt}\n\n{_identity_block(confirmed_name, confirmed_phone, candidate_name, candidate_phone)}"
        f"{_OUTPUT_FORMAT_INSTRUCTIONS}"
    )


def _awaiting_acceptance_note() -> str:
    return (
        "\n\nYa se le explicó el proceso a la persona (mensaje + nota de voz) y se le "
        "preguntó si desea continuar — no repita esa explicación. Su única tarea en este "
        'turno es conseguir un "sí" o un "no" claro a esa pregunta: si el mensaje de la '
        "persona es una duda u objeción, respóndala brevemente y termine reafirmando la "
        'misma pregunta ("¿desea que continuemos con el proceso?"); si es un comentario '
        'vago, evasivo o que no responde la pregunta (ej. "no sé", "está bien", "ya '
        'veremos", "que quieres saber"), no lo interprete como aceptación ni cambie de '
        "tema — repita la pregunta de forma directa. Bajo ninguna circunstancia pase a "
        "otro tema ni pregunte por datos del inmueble mientras siga en este estado."
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
    signed_claim: bool = False
    explanation_requested: bool = False
    client_full_name: str | None = None
    client_phone: str | None = None


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
        signed_claim=data.get("signed_claim") is True,
        explanation_requested=data.get("explanation_requested") is True,
        client_full_name=_as_text(data.get("client_full_name")),
        client_phone=_as_text(data.get("client_phone")),
    )


_SAFE_HISTORY_ANALYSIS: dict[str, Any] = {
    "client_full_name": None,
    "client_phone": None,
    "process_explained": False,
    "authorization_mentioned": False,
    "summary": "",
}


def _format_prior_history_transcript(messages: list[dict[str, Any]]) -> str:
    """Arma una transcripción legible en orden cronológico a partir de mensajes crudos de Waha.

    Cada mensaje de Waha trae `fromMe` (bool) y `body` (texto), mismo shape
    que el payload del webhook (ver `app.waha.inbound`) — `fromMe: true` es
    un mensaje del asesor humano, `fromMe: false` es del cliente. Se ordena
    por `timestamp` (si viene) para no depender de en qué orden Waha haya
    devuelto la lista. Los mensajes sin texto (media no soportada, notas de
    voz nunca transcritas en su momento, etc.) se omiten — no hay nada que
    analizar en ellos.
    """
    ordered = sorted(messages, key=lambda m: m.get("timestamp") or 0)
    lines = []
    for message in ordered:
        body = message.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        speaker = "Asesor" if message.get("fromMe") else "Cliente"
        lines.append(f"{speaker}: {body.strip()}")
    return "\n".join(lines)


def analyze_prior_history(llm_client: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Analiza con el LLM una conversación previa de WhatsApp (traída de Waha, no del store local).

    Pensado para cuando un admin activa el bot en un chat donde un asesor
    humano ya habló con la persona por WhatsApp Web antes de que el bot
    existiera para ese chat (ver `app.flows.whatsapp_bot_history_seed`) —
    así el bot no vuelve a pedir nombre/teléfono ni reenvía plantillas
    (explicación del proceso, Autorización de Corretaje) ya habladas a
    mano. Reusa `LlmClient.reply` (mismo mecanismo que la conversación
    normal) con `history=[]` y toda la transcripción como `user_text` —
    es un análisis de una sola pasada, no una conversación turno a turno,
    así que no hace falta un método nuevo en `LlmClient`.

    Ante cualquier falla (LLM caído, JSON inválido o con campos con tipo
    incorrecto, o transcripción vacía) retorna un default seguro sin
    lanzar — nunca debe bloquear la activación de un chat.
    """
    transcript = _format_prior_history_transcript(messages)
    if not transcript:
        return dict(_SAFE_HISTORY_ANALYSIS)

    system_prompt = templates_store.get_template("whatsapp_history_analysis_prompt")
    raw_output = llm_client.reply(system_prompt, [], transcript)
    if raw_output is None:
        logger.warning("LLM no devolvió análisis de historial previo, se usa el default seguro")
        return dict(_SAFE_HISTORY_ANALYSIS)

    return _parse_history_analysis(raw_output)


def _parse_history_analysis(raw: str) -> dict[str, Any]:
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
        logger.warning("Análisis de historial previo no es JSON válido, se usa el default seguro")
        return dict(_SAFE_HISTORY_ANALYSIS)

    summary = data.get("summary")
    return {
        "client_full_name": _as_text(data.get("client_full_name")),
        "client_phone": _as_text(data.get("client_phone")),
        "process_explained": data.get("process_explained") is True,
        "authorization_mentioned": data.get("authorization_mentioned") is True,
        "summary": summary.strip() if isinstance(summary, str) else "",
    }
