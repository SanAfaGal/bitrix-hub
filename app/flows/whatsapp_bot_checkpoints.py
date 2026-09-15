"""Progreso conversacional genérico del bot de WhatsApp: catálogo `Checkpoint` + `LeadCheckpoint`.

Reemplaza el patrón de una columna booleana/nullable por punto de progreso en
`leads` (ver `whatsapp_bot_models.py`) — agregar un checkpoint nuevo es una
fila en `CHECKPOINT_SEED`, no una migración de schema. `CHECKPOINT_SEED` es
la única fuente de verdad del catálogo: la usa tanto la migración Alembic
(`migrations/versions/0005_checkpoints.py`) como `build_sqlite_engine` (tests)
para no duplicar la lista en dos lugares.

Semántica "alcanzado": que exista la fila en `lead_checkpoints` para
`(lead_id, checkpoint_id)` ya significa que se alcanzó ese punto, sin
importar si `value`/`reached_at` son `NULL` — ver `has_reached` vs.
`get_answer`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.flows.whatsapp_bot_models import Checkpoint, LeadCheckpoint
from app.flows.whatsapp_bot_store import _get_by_chat_id, _get_or_create


@dataclass(frozen=True)
class CheckpointInfo:
    """Vista plana de `Checkpoint`, sin atar el caller al ciclo de vida de la sesión SQLAlchemy
    (mismo criterio que el resto de `whatsapp_bot_store.py`: nunca se devuelven filas ORM crudas)."""

    key: str
    description: str | None
    order: int

# (key, description, order) — agregar un checkpoint nuevo es agregar una tupla acá.
CHECKPOINT_SEED: list[tuple[str, str, int]] = [
    ("zone_coverage", "¿Zona del inmueble está en cobertura (Medellín / Oriente antioqueño)?", 1),
    ("explanation", "Explicación del proceso enviada", 2),
    ("authorization_link", "Link de Autorización de Corretaje enviado", 3),
]


def seed_default_checkpoints(session: Session) -> None:
    """Siembra `CHECKPOINT_SEED` si el catálogo está vacío — usado por `build_sqlite_engine`
    (tests); en producción el catálogo lo siembra la migración Alembic."""
    if session.query(Checkpoint).first() is not None:
        return
    for key, description, order in CHECKPOINT_SEED:
        session.add(Checkpoint(key=key, description=description, order=order, active=True))
    session.commit()


def _get_checkpoint_by_key(session: Session, key: str) -> Checkpoint | None:
    return session.query(Checkpoint).filter(Checkpoint.key == key).first()


def _get_lead_checkpoint(session: Session, lead_id: int, checkpoint_id: int) -> LeadCheckpoint | None:
    return (
        session.query(LeadCheckpoint)
        .filter(LeadCheckpoint.lead_id == lead_id, LeadCheckpoint.checkpoint_id == checkpoint_id)
        .first()
    )


def get_next_checkpoint(session: Session, chat_id: str) -> CheckpointInfo | None:
    """Primer checkpoint activo, en orden, que este lead todavía no alcanzó. `None` si ya
    pasó por todos (o si el lead no existe todavía — nada que alcanzar sin fila en `leads`)."""
    lead = _get_by_chat_id(session, chat_id)
    reached_ids: set[int] = set()
    if lead is not None:
        reached_ids = {
            row.checkpoint_id
            for row in session.query(LeadCheckpoint.checkpoint_id).filter(LeadCheckpoint.lead_id == lead.id)
        }

    checkpoints = session.query(Checkpoint).filter(Checkpoint.active.is_(True)).order_by(Checkpoint.order).all()
    for checkpoint in checkpoints:
        if checkpoint.id not in reached_ids:
            return CheckpointInfo(key=checkpoint.key, description=checkpoint.description, order=checkpoint.order)
    return None


def has_reached(session: Session, chat_id: str, checkpoint_key: str) -> bool:
    lead = _get_by_chat_id(session, chat_id)
    checkpoint = _get_checkpoint_by_key(session, checkpoint_key)
    if lead is None or checkpoint is None:
        return False
    return _get_lead_checkpoint(session, lead.id, checkpoint.id) is not None


def get_answer(session: Session, chat_id: str, checkpoint_key: str) -> bool | None:
    """`None` si el checkpoint no se ha alcanzado o se alcanzó sin dejar `value`; si no, `bool(value)`."""
    lead = _get_by_chat_id(session, chat_id)
    checkpoint = _get_checkpoint_by_key(session, checkpoint_key)
    if lead is None or checkpoint is None:
        return None
    row = _get_lead_checkpoint(session, lead.id, checkpoint.id)
    if row is None or row.value is None:
        return None
    return bool(row.value)


def mark_reached(session: Session, chat_id: str, checkpoint_key: str, value: bool | None = None) -> None:
    """Upsert de la fila en `lead_checkpoints` — `reached_at` solo se pone en filas nuevas,
    nunca se sobreescribe en una llamada repetida sobre un checkpoint ya alcanzado."""
    lead = _get_or_create(session, chat_id)
    checkpoint = _get_checkpoint_by_key(session, checkpoint_key)
    if checkpoint is None:
        raise ValueError(f"checkpoint desconocido: {checkpoint_key!r}")

    row = _get_lead_checkpoint(session, lead.id, checkpoint.id)
    stored_value = None if value is None else int(value)
    if row is None:
        row = LeadCheckpoint(
            lead_id=lead.id,
            checkpoint_id=checkpoint.id,
            value=stored_value,
            reached_at=datetime.now(timezone.utc),
        )
        session.add(row)
    else:
        row.value = stored_value
    session.commit()
