"""crea tablas de conversacion del bot de whatsapp

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31

Generada con `alembic revision --autogenerate` contra una base MySQL de
scratch (0001 ya aplicada), revisada a mano contra
`app/flows/whatsapp_bot_models.py`: una sola tabla `conversations` (deal
vinculado, identidad, estado de la explicación — todo 1:1 por chat, no hay
razón de negocio para partirlo en varias tablas) + `conversation_messages`
(1:N) con FK `ondelete="CASCADE"` hacia `conversations.chat_id` y el índice
compuesto `idx_conversation_messages_chat_id`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "conversations",
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("deal_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("explanation_offered", sa.Boolean(), nullable=False),
        sa.Column("explanation_sent", sa.Boolean(), nullable=False),
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


def downgrade() -> None:
    """Downgrade schema."""
    # `drop_table` ya elimina el índice `idx_conversation_messages_chat_id`
    # junto con la tabla — un `drop_index` explícito antes fallaba en MySQL
    # porque el índice está en uso por el FK `conversation_messages.chat_id`
    # (error 1553: "needed in a foreign key constraint").
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
