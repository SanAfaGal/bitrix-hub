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


def load_signed_form_drive_folder_id() -> str:
    """Carga el ID de la carpeta del drive del CRM donde se guardan los PDFs firmados."""
    load_dotenv()

    folder_id = (os.getenv("BITRIX_DRIVE_FOLDER_ID") or "").strip()

    if not folder_id:
        raise RuntimeError("Falta variable de entorno: BITRIX_DRIVE_FOLDER_ID")

    return folder_id
