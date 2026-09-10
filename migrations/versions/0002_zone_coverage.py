"""zone coverage: pregunta de Medellín / Oriente antioqueño en leads

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10

Agrega a `leads` (`app.flows.whatsapp_bot_models.Conversation`) el estado de
la pregunta de cobertura de zona que el bot de WhatsApp le hace al cliente
antes de la explicación del proceso — ver `app/flows/whatsapp_bot_zone.py`.

- `zone_asked`: True una vez que se mandó la pregunta.
- `zone_in_coverage`: `NULL` hasta que la persona responda con claridad,
  luego `True`/`False`.
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
    op.add_column("leads", sa.Column("zone_asked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("leads", sa.Column("zone_in_coverage", sa.Boolean(), nullable=True))
    op.alter_column("leads", "zone_asked", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leads", "zone_in_coverage")
    op.drop_column("leads", "zone_asked")
