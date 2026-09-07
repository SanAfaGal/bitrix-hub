"""fusiona conversations + dedup de correos de Graph en una tabla leads

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

Reemplaza `conversations` por `leads`: un prospecto puede llegar por
WhatsApp (`chat_id` set, `channel="whatsapp"`) o por el formulario web vía
correo (`email_tracking_id` set, `channel="email"`) — ver
`app/flows/whatsapp_bot_models.py::Conversation`. PK sintética `id`
autoincrement porque ninguna de las dos claves de negocio puede ser NOT
NULL para todas las filas. Ninguna de las dos tablas (`conversations` ni la
`graph_processed_messages` que esta migración iba a crear originalmente)
tiene datos reales desplegados todavía, así que es un drop+create limpio,
sin migrar filas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("conversation_messages")
    op.drop_table("conversations")

    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=True),
        sa.Column("email_tracking_id", sa.String(length=64), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("deal_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("explanation_offered", sa.Boolean(), nullable=False),
        sa.Column("explanation_sent", sa.Boolean(), nullable=False),
        sa.Column("authorization_link_sent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_leads_chat_id"),
        sa.UniqueConstraint("email_tracking_id", name="uq_leads_email_tracking_id"),
        sa.UniqueConstraint("deal_id", name="uq_leads_deal_id"),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["leads.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversation_messages_chat_id", "conversation_messages", ["chat_id", "id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("conversation_messages")
    op.drop_table("leads")

    op.create_table(
        "conversations",
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("deal_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("explanation_offered", sa.Boolean(), nullable=False),
        sa.Column("explanation_sent", sa.Boolean(), nullable=False),
        sa.Column("authorization_link_sent", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
        sa.UniqueConstraint("deal_id", name="uq_conversations_deal_id"),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["conversations.chat_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversation_messages_chat_id", "conversation_messages", ["chat_id", "id"], unique=False)
