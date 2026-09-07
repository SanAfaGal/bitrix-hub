"""crea tabla de deduplicacion de correos de Microsoft Graph

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

Refleja `app/graph/models.py::ProcessedGraphMessage` — usada por
`app/flows/graph_lead_intake.py` para no crear un contacto/negociación
duplicado en Bitrix si el mismo correo vuelve a aparecer en una corrida
posterior de `POST /graph/process-leads`.
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
    op.create_table(
        "graph_processed_messages",
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.Column("deal_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("message_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("graph_processed_messages")
