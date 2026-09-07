"""Assets estáticos compartidos por el bot de WhatsApp.

Separado en su propio módulo (sin lógica de negocio) para que
`whatsapp_bot_welcome.py` y `whatsapp_bot_explanation.py` puedan importarlo
sin crear un ciclo entre ellos dos.
"""
from __future__ import annotations

import base64
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# Nota de voz fija que explica el proceso — no cambia en runtime, se lee una
# sola vez y se cachea en base64 (evita releer disco en cada mensaje).
_PROCESS_EXPLANATION_VOICE_PATH = (
    Path(__file__).resolve().parent.parent / "waha" / "assets" / "process_explanation_voice.ogg"
)


@lru_cache(maxsize=1)
def process_explanation_voice_base64() -> str | None:
    try:
        return base64.b64encode(_PROCESS_EXPLANATION_VOICE_PATH.read_bytes()).decode("ascii")
    except OSError as exc:
        logger.error("No se pudo leer el audio de explicación del proceso (%s): %s", _PROCESS_EXPLANATION_VOICE_PATH, exc)
        return None
