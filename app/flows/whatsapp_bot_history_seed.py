"""Trae historial real de WhatsApp desde Waha y lo importa como contexto local al activar un chat.

Pensado para cuando un admin activa el bot (`ConversationStore.set_bot_enabled`,
Tarea 4 — no vive acá) para un chat que ya tuvo conversación previa que el
bot nunca vio: un asesor humano habló con la persona por WhatsApp Web antes
de que el bot existiera para ese chat. Waha sigue teniendo esos mensajes
(incluidos los `fromMe: true` del asesor, que el webhook entrante descarta
en silencio — ver `app.waha.inbound.parse_inbound_message`), aunque este
hub nunca los guardó en `messages`.

Separado de `whatsapp_bot.py`/`whatsapp_bot_llm.py` porque, a diferencia de
esos dos, esta pieza combina `ConversationStore` + `WahaClient` + `LlmClient`
a la vez — no encaja en el criterio de separación ya usado en ese par de
módulos (uno es puro texto LLM, el otro es solo `Session` de SQLAlchemy).
"""
from __future__ import annotations

import logging
from typing import Any

from app.flows.whatsapp_bot import _normalize_phone, load_bot_config
from app.flows.whatsapp_bot_conversation_store import ConversationStore
from app.flows.whatsapp_bot_llm import analyze_prior_history
from app.llm.client import LlmClient
from app.waha.client import WahaClient

logger = logging.getLogger(__name__)


def _map_to_turns(messages: list[dict[str, Any]], *, max_turns: int) -> list[tuple[str, str]]:
    """Convierte mensajes crudos de Waha en turnos `(role, content)`, en orden cronológico.

    `fromMe: true` -> "assistant" (lo mandó la línea, sea el asesor a mano o
    el bot), `fromMe: false` -> "user" (lo mandó el cliente) — mismo mapeo
    que ya usa `ConversationStore.add_turn` en el flujo normal. Los mensajes
    sin texto (media no soportada, notas de voz de esa época) se descartan,
    no hay nada que darle al LLM de contexto ahí. Se recorta a los últimos
    `max_turns` ya en orden cronológico (los más viejos se pierden primero),
    igual que el tope de lectura de `ConversationStore.get_history`.
    `max_turns <= 0` (config de cero turnos) no importa nada, en vez de
    interpretarse como "sin tope" — un slice `turns[-0:]` sería `turns`
    completo, lo contrario de lo que pide un tope de cero.
    """
    ordered = sorted(messages, key=lambda m: m.get("timestamp") or 0)
    turns: list[tuple[str, str]] = []
    for message in ordered:
        body = message.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        role = "assistant" if message.get("fromMe") else "user"
        turns.append((role, body.strip()))
    return turns[-max_turns:] if max_turns > 0 else []


def seed_history_from_waha(
    store: ConversationStore,
    waha_client: WahaClient,
    llm_client: LlmClient,
    chat_id: str,
    *,
    limit: int | None = None,
    max_history_turns: int | None = None,
    session: str = "default",
) -> dict[str, Any]:
    """Si el chat todavía no tiene el historial de Waha importado, lo trae, lo analiza con IA e importa.

    La señal de "ya importado" es el flag dedicado `history_seeded`
    (columna de `leads`, `ConversationStore.get_history_seeded`/
    `set_history_seeded`) — NO si `messages` ya tiene filas para este chat.
    Esas dos cosas no son lo mismo: mientras `bot_enabled=False`, `_process()`
    en whatsapp_bot.py ya guarda cada mensaje entrante localmente (para que
    el chat aparezca en /admin/prospects), así que para cuando un admin
    activa un chat casi siempre YA hay historial local — con el criterio
    viejo ("hay historial local") esta función nunca llegaba a pegarle a
    Waha ni al LLM, y el contexto previo real (nombre/teléfono, si ya se
    explicó el proceso, etc.) nunca se importaba. Ver Hallazgo Crítico de la
    revisión final de esta rama.

    Si Waha sí devuelve mensajes y ya había turnos locales del período
    desactivado, esos turnos locales se reemplazan (no se duplican) por los
    recién importados de Waha — son un subconjunto estricto de lo que Waha
    devuelve para el mismo chat, ver `store.clear_messages`.

    Si Waha no devuelve mensajes (chat realmente nuevo, o falla la llamada),
    no hay nada que importar, pero igual se marca `history_seeded` — así una
    reactivación futura de ese mismo chat no vuelve a pegarle a Waha para
    nada. `limit`/`max_history_turns` son overrides opcionales para tests —
    en producción se cargan de `BotConfig`
    (`WHATSAPP_BOT_HISTORY_ANALYSIS_LIMIT` / `WHATSAPP_BOT_MAX_HISTORY_TURNS`).

    No toca `bot_enabled` — eso lo decide un nivel más arriba (la ruta de
    admin que active el chat, Tarea 4), esta función solo prepara el
    contexto para que esa activación no arranque en blanco.

    `session` default `"default"` solo cubre el caso de un único Waha
    session en el deployment — a diferencia de `is_chat_new_in_waha`
    (que recibe `inbound.session` real del webhook), acá no hay un
    `InboundMessage` de dónde sacarlo (se dispara desde el panel admin);
    el caller debe pasar la sesión configurada (`WahaSettings.session`) si
    el deployment usa más de una.

    Retorna un resumen: `{"seeded": bool, "messages_imported": int,
    "analysis": dict | None}` para que la ruta de admin le muestre algo útil
    a quien activó el chat.
    """
    if store.get_history_seeded(chat_id):
        logger.info("Chat %s ya tiene el historial de Waha importado, no se reimporta", chat_id)
        return {"seeded": False, "messages_imported": 0, "analysis": None}

    config = load_bot_config()
    resolved_limit = limit if limit is not None else config.history_analysis_limit
    resolved_max_turns = max_history_turns if max_history_turns is not None else config.max_history_turns

    messages = waha_client.get_chat_messages(chat_id, limit=resolved_limit, session=session)
    if not messages:
        logger.info("Sin historial previo en Waha para %s, no hay nada que importar", chat_id)
        store.set_history_seeded(chat_id)
        return {"seeded": False, "messages_imported": 0, "analysis": None}

    analysis = analyze_prior_history(llm_client, messages)

    turns = _map_to_turns(messages, max_turns=resolved_max_turns * 2)
    if turns:
        # Reemplaza (no duplica) los turnos locales del período desactivado —
        # ver docstring de arriba.
        store.clear_messages(chat_id)
        for role, content in turns:
            store.add_turn(chat_id, role, content)

    confirmed_name, confirmed_phone = store.get_confirmed_identity(chat_id)
    if confirmed_name is None and confirmed_phone is None:
        normalized_phone = _normalize_phone(analysis["client_phone"])
        if analysis["client_full_name"] is not None and normalized_phone is not None:
            store.set_confirmed_identity(chat_id, analysis["client_full_name"], normalized_phone)

    if analysis["process_explained"] and not store.get_explanation_sent(chat_id):
        store.set_explanation_sent(chat_id)

    # OJO: `analysis["authorization_mentioned"]` (el LLM detectó que se
    # HABLÓ de la Autorización en la conversación previa) NO se mapea a
    # `authorization_link_sent` — ese flag significa en el resto del código
    # (`maybe_handle_acceptance` en whatsapp_bot_explanation.py,
    # `Conversation.authorization_link_sent` en whatsapp_bot_models.py) que
    # el link REAL ya se mandó, y se usa para no volver a mandarlo nunca. Un
    # asesor humano mencionando la Autorización en el chat ("te voy a mandar
    # la Autorización") no es lo mismo que haberla mandado — setear el flag
    # acá bloquearía silenciosa y permanentemente que el bot mande el link
    # real. `authorization_mentioned` solo se usa para el `summary` del
    # análisis, no cambia ningún estado.
    store.set_history_seeded(chat_id)

    logger.info(
        "Historial previo de %s importado desde Waha: %d turnos, process_explained=%s, authorization_mentioned=%s",
        chat_id,
        len(turns),
        analysis["process_explained"],
        analysis["authorization_mentioned"],
    )
    return {"seeded": True, "messages_imported": len(turns), "analysis": analysis}
