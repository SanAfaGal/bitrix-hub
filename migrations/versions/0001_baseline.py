"""baseline: templates, leads, messages, whatsapp_messages, checkpoints, lead_checkpoints

Revision ID: 0001
Revises:
Create Date: 2026-09-14

Migración única — reemplaza la cadena anterior (0001..0005), squasheada de
nuevo porque ninguna base real (fuera de este entorno de desarrollo) tenía
datos que preservar salvo `templates` (respaldada y reimportada a mano al
aplicar esto, igual que en el squash anterior). Crea el esquema final
completo:

- `templates`: texto editable desde el panel admin, identificado por `key`
  (`app.message_templates.models.MessageTemplate`).
- `leads`: un prospecto por `chat_id` (WhatsApp, `channel="whatsapp"`) o
  `tracking_id` (formulario web vía correo, `channel="email"`) — nunca por
  los dos; PK sintética `id` porque ninguna de las dos claves de negocio
  aplica a todas las filas (`app.flows.whatsapp_bot_models.Conversation`).
  Incluye `bot_enabled`/`bot_enabled_reason` — activación explícita del bot
  por chat (opt-in) y el motivo del último cambio — e `history_seeded`, que
  marca si ya se intentó importar el historial previo de WhatsApp desde Waha
  para ese chat. El progreso conversacional (zona en cobertura, explicación
  enviada, link de Autorización enviado) YA NO son columnas acá — viven en
  `checkpoints`/`lead_checkpoints` (ver abajo).
- `messages`: historial de turnos de un lead de WhatsApp, 1:N vía
  `lead_id` -> `leads.id` (`app.flows.whatsapp_bot_models.ConversationMessage`).
- `whatsapp_messages`: log de dedup de `message_id` de Waha, independiente de
  `messages`/`leads` (`app.flows.whatsapp_bot_models.WhatsappMessage`).
- `checkpoints` (catálogo) + `lead_checkpoints` (progreso por lead): modelo
  genérico de progreso conversacional — agregar un checkpoint nuevo es una
  fila en `CHECKPOINT_SEED`
  (`app.flows.whatsapp_bot_checkpoints.CHECKPOINT_SEED`), no una migración de
  schema. Que exista la fila en `lead_checkpoints` para
  `(lead_id, checkpoint_id)` ya significa "alcanzado", sin importar si
  `value`/`reached_at` son `NULL`. `bot_enabled`/`bot_enabled_reason` NO son
  checkpoints — son control operativo de admin, no progreso conversacional.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Debe quedar igual a `app.flows.whatsapp_bot_checkpoints.CHECKPOINT_SEED` —
# única fuente de verdad del catálogo inicial, no se importa desde acá para
# no atar esta migración (histórica, inmutable) a que ese módulo no cambie.
_CHECKPOINT_SEED = [
    ("zone_coverage", "¿Zona del inmueble está en cobertura (Medellín / Oriente antioqueño)?", 1),
    ("explanation", "Explicación del proceso enviada", 2),
    ("authorization_link", "Link de Autorización de Corretaje enviado", 3),
]


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
        sa.Column("bot_enabled", sa.Boolean(), nullable=False),
        sa.Column("bot_enabled_reason", sa.String(length=32), nullable=True),
        sa.Column("history_seeded", sa.Boolean(), nullable=False),
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

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.String(128), nullable=False),
        sa.Column("processed_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("message_id", name="uq_whatsapp_messages_message_id"),
    )

    op.create_table(
        "checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("key", name="uq_checkpoints_key"),
        sa.UniqueConstraint("order", name="uq_checkpoints_order"),
    )

    op.create_table(
        "lead_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("checkpoint_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("reached_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"]),
        sa.UniqueConstraint("lead_id", "checkpoint_id", name="uq_lead_checkpoints_lead_checkpoint"),
    )

    checkpoints_table = sa.table(
        "checkpoints",
        sa.column("key", sa.String),
        sa.column("description", sa.Text),
        sa.column("order", sa.Integer),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        checkpoints_table,
        [
            {"key": key, "description": description, "order": order, "active": True}
            for key, description, order in _CHECKPOINT_SEED
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("lead_checkpoints")
    op.drop_table("checkpoints")
    op.drop_table("whatsapp_messages")
    op.drop_table("messages")
    op.drop_table("leads")
    op.drop_table("templates")
