"""Configuración de variables de entorno para la integración con Microsoft Graph."""
from __future__ import annotations

import os

from dotenv import load_dotenv


def load_graph_settings() -> tuple[str, str, str, str]:
    """Carga y valida las variables de entorno requeridas para Microsoft Graph."""
    load_dotenv()

    tenant_id = (os.getenv("GRAPH_TENANT_ID") or "").strip()
    client_id = (os.getenv("GRAPH_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GRAPH_CLIENT_SECRET") or "").strip()
    mailbox = (os.getenv("GRAPH_MAILBOX") or "").strip()

    missing = [name for name, value in (
        ("GRAPH_TENANT_ID", tenant_id),
        ("GRAPH_CLIENT_ID", client_id),
        ("GRAPH_CLIENT_SECRET", client_secret),
        ("GRAPH_MAILBOX", mailbox),
    ) if not value]

    if missing:
        raise RuntimeError("Faltan variables de entorno: " + ", ".join(missing))

    return tenant_id, client_id, client_secret, mailbox
