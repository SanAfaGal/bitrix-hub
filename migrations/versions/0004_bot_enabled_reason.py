"""bot_enabled_reason: motivo del último cambio de activación del bot por chat

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11

Hoy no hay forma de saber por qué un chat tiene `bot_enabled=False` (o por
qué se activó) — seis caminos distintos escriben ese mismo booleano
(auto-activación de chat nuevo, fail-closed de la consulta a Waha, toggle
manual del admin, handoff explícito del cliente, firma de la Autorización de
Corretaje, fuera de zona de cobertura) sin dejar ningún rastro de cuál fue.

`bot_enabled_reason` se sobreescribe en cada cambio — no es auditoría
histórica, solo el motivo del estado actual.
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
    op.add_column("leads", sa.Column("bot_enabled_reason", sa.String(32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leads", "bot_enabled_reason")
