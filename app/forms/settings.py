"""Configuración de variables de entorno para el formulario de Autorización de Corretaje."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_form_link_secret() -> str:
    """Carga el secreto usado para firmar el `deal_id` en el link del formulario."""
    load_dotenv()

    secret = (os.getenv("FORM_LINK_SECRET") or "").strip()

    if not secret:
        raise RuntimeError("Falta variable de entorno: FORM_LINK_SECRET")

    return secret
