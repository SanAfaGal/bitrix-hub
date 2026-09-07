"""baseline: templates, leads, messages

Revision ID: 0001
Revises:
Create Date: 2026-08-31

Migración única — reemplaza la cadena anterior (0001..0004), squasheada
porque ninguna base real (fuera de este entorno de desarrollo) tenía datos
que preservar salvo `templates` (antes `message_templates`), respaldada y
reimportada a mano al aplicar esto. Crea el esquema final completo:

- `templates` (antes `message_templates`): texto editable desde el panel
  admin, identificado por `key` (`app.message_templates.models.MessageTemplate`).
- `leads`: un prospecto por `chat_id` (WhatsApp, `channel="whatsapp"`) o
  `tracking_id` (formulario web vía correo, `channel="email"`) — nunca por
  los dos; PK sintética `id` porque ninguna de las dos claves de negocio
  aplica a todas las filas (`app.flows.whatsapp_bot_models.Conversation`).
- `messages`: historial de turnos de un lead de WhatsApp, 1:N vía
  `lead_id` -> `leads.id` (`app.flows.whatsapp_bot_models.ConversationMessage`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "templates",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=True),
    )

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("tracking_id", sa.String(length=64), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("deal_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("explanation_sent", sa.Boolean(), nullable=False),
        sa.Column("authorization_link_sent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_leads_chat_id"),
        sa.UniqueConstraint("tracking_id", name="uq_leads_tracking_id"),
        sa.UniqueConstraint("deal_id", name="uq_leads_deal_id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_lead_id", "messages", ["lead_id", "id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("messages")
    op.drop_table("leads")
    op.drop_table("templates")
