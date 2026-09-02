"""agrega authorization_link_sent a conversations

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02

Refleja `app/flows/whatsapp_bot_models.py::Conversation.authorization_link_sent`
— fuente de verdad LOCAL de si ya se mandó el link de Autorización de
Corretaje, en vez de inferirlo del picklist `UF_CRM_1773864282733` de Bitrix
(`is None`), que puede traer un valor por defecto no nulo desde que se crea
el deal y hacía que el bot nunca detectara "todavía no se mandó".
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
    op.add_column(
        "conversations",
        sa.Column("authorization_link_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.alter_column("authorization_link_sent", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("conversations", "authorization_link_sent")
