"""baseline message_templates

Revision ID: 0001
Revises:
Create Date: 2026-08-31

Refleja el esquema ACTUAL de `message_templates`
(app/message_templates/models.py::MessageTemplate), creado originalmente por
`Base.metadata.create_all()` fuera de Alembic. Contra una base que ya tiene
esta tabla (producción), esta migración NO se corre con `upgrade` — se marca
como aplicada con `alembic stamp 0001`.
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
        "message_templates",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("message_templates")
