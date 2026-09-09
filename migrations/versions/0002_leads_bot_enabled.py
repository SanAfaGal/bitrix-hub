"""leads: agrega bot_enabled

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-09

Agrega el flag `bot_enabled` a `leads` — activación por chat (opt-in) del
bot de WhatsApp, arranca en False para todo lead existente y nuevo; un
admin lo prende a mano desde el panel admin (ver
`app.flows.whatsapp_bot_models.Conversation`).
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
    op.add_column(
        "leads",
        sa.Column("bot_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("leads", "bot_enabled", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leads", "bot_enabled")
