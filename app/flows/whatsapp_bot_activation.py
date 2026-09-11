"""Activación manual de un chat desde el panel admin — importa historial + responde un
mensaje pendiente. Separado de `app/admin/router.py` (que queda solo con la llamada +
respuesta HTTP, ver CLAUDE.md: `app/admin/` es presentación, la orquestación de negocio va
en `app/flows/`) para que el mismo flujo se pueda reusar fuera del panel el día que haga
falta (ej. un endpoint de API o un cron), sin duplicar esta lógica.

Recibe los constructores de clientes (`get_waha_client`, etc.) y las funciones de flujo
(`seed_history_from_waha`, `reply_after_activation`) como parámetros en vez de importarlos
fijos, para que el caller (hoy `app/admin/router.py`) siga siendo el único punto donde se
resuelven esas dependencias — mismo patrón que ya usan los tests existentes para
sustituirlas por fakes.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from app.crm.protocol import CrmClient
from app.llm.client import LlmClient
from app.waha.client import WahaClient

if TYPE_CHECKING:
    from app.flows.whatsapp_bot_conversation_store import ConversationStore

logger = logging.getLogger(__name__)


def activate_bot_for_chat(
    chat_id: str,
    conversation_store: "ConversationStore",
    get_waha_client: Callable[[], WahaClient],
    get_llm_client: Callable[[], LlmClient],
    get_crm_client: Callable[[], CrmClient],
    seed_history_from_waha: Callable[..., dict[str, Any]],
    reply_after_activation: Callable[..., dict[str, Any]],
) -> None:
    """Activa el bot para `chat_id`: importa su historial previo de WhatsApp si hace falta y
    responde un mensaje pendiente si lo había. Si ya estaba activo no hace nada — evita
    reimportar/reanalizar de más ante un doble clic en "Activar" desde el panel.
    """
    if conversation_store.get_bot_enabled(chat_id):
        return

    try:
        waha_client = get_waha_client()
        llm_client = get_llm_client()
        # `chat_lock` acá evita la carrera con un mensaje real llegando al mismo tiempo por el
        # webhook (`_process()` también toma este lock) — sin esto, `seed_history_from_waha`
        # podía pisar (`clear_messages`) un mensaje recién guardado por el webhook, o al revés.
        with conversation_store.chat_lock(chat_id):
            seed_history_from_waha(conversation_store, waha_client, llm_client, chat_id)
    except Exception:  # noqa: BLE001 — una integración mal configurada no debe romper el panel admin
        logger.exception(
            "No se pudo importar el historial de Waha al activar el bot para %s — se activa igual", chat_id
        )

    conversation_store.set_bot_enabled(chat_id, True, reason="admin_manual")

    try:
        # Si el cliente tenía un mensaje sin responder (llegó mientras el chat estaba
        # apagado), se contesta de una vez acá — sin esto, se queda sin respuesta hasta
        # que el cliente escriba de nuevo, aunque el admin ya haya activado el bot mirando
        # ese mismo mensaje. Try/except aparte del de arriba: que el seed haya fallado (o no)
        # no debe impedir el intento de responder, y viceversa.
        reply_after_activation(
            chat_id, get_waha_client(), get_llm_client(), get_crm_client(), store=conversation_store
        )
    except Exception:  # noqa: BLE001 — una integración mal configurada no debe romper el panel admin
        logger.exception("No se pudo responder el mensaje pendiente de %s al activar el bot", chat_id)
