"""leads: agrega history_seeded

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-09

Agrega el flag `history_seeded` a `leads` — marca si ya se intentó importar
el historial previo de WhatsApp desde Waha para este chat
(`app.flows.whatsapp_bot_history_seed.seed_history_from_waha`). Arranca en
False para todo lead existente y nuevo.

Reemplaza el uso de "el chat no tiene historial local todavía" como señal de
"todavía no se importó" — esa señal era incorrecta: `_process()` en
whatsapp_bot.py ya guarda cada mensaje entrante localmente aunque
`bot_enabled=False` (para que el chat aparezca en /admin/prospects), así que
para cuando un admin activa un chat, casi siempre YA tiene historial local y
`seed_history_from_waha` nunca llegaba a pegarle a Waha ni al LLM.
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
        "leads",
        sa.Column("history_seeded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("leads", "history_seeded", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("leads", "history_seeded")
