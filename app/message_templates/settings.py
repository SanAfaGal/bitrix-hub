"""Configuración de variables de entorno para la base MySQL de plantillas de mensajes."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class MessageTemplatesSettings:
    host: str
    port: int
    database: str
    user: str
    password: str


def load_message_templates_settings() -> MessageTemplatesSettings:
    """Carga la configuración de conexión a MySQL, con defaults pensados para el contenedor de docker-compose.yml."""
    load_dotenv()

    return MessageTemplatesSettings(
        host=(os.getenv("MYSQL_HOST") or "mysql").strip(),
        port=int((os.getenv("MYSQL_PORT") or "3306").strip()),
        database=(os.getenv("MYSQL_DATABASE") or "bitrix_hub").strip(),
        user=(os.getenv("MYSQL_USER") or "bitrix_hub").strip(),
        password=os.getenv("MYSQL_PASSWORD") or "",
    )
