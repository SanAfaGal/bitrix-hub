"""whatsapp_messages: dedup persistente de message_id de Waha

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11

El dedup de mensajes entrantes de WhatsApp vivía solo en memoria del proceso
(`ConversationStore._seen_message_ids`), que se vacía en cada reinicio del
contenedor `api`. Si Waha resincroniza historial del chat al reconectar la
sesión tras un restart y reemite mensajes viejos como webhooks nuevos, el bot
los procesaba de cero y reenviaba respuestas reales duplicadas (visto en
producción).

`whatsapp_messages` es un log de `message_id` sin relación con `leads`/
`messages`: no todo mensaje entrante llega a guardarse como turno (bot
apagado, número no permitido, media no soportada, transcripción fallida),
pero igual necesita dedup. Sin TTL — una fila por mensaje procesado, para
siempre, es trivial en espacio para el volumen de este bot.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(128), nullable=False),
        sa.Column("processed_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("whatsapp_messages")
