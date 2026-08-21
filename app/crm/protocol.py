"""Contrato que debe cumplir cualquier cliente de CRM usado por el hub.

Solo incluye las operaciones que los flows/forms reales necesitan hoy — no
es un mapeo genérico de "toda la API de un CRM". Un CRM nuevo se agrega
implementando esta clase (duck typing: no hace falta heredar de ella).
"""
from __future__ import annotations

from typing import Any, Protocol


class CrmClient(Protocol):
    def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Obtiene los campos de un deal/negocio. Retorna {} si falla o no existe."""
        ...

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Obtiene los campos de un contacto. Retorna {} si falla o no existe."""
        ...

    def get_deal_contact_id(self, deal: dict[str, Any]) -> str | None:
        """Extrae el ID del contacto vinculado a un deal ya obtenido con get_deal."""
        ...

    def get_contact_phone(self, contact: dict[str, Any]) -> str | None:
        """Extrae el mejor teléfono disponible de un contacto ya obtenido con get_contact."""
        ...

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        """Extrae la matrícula/registro del inmueble de un deal ya obtenido con get_deal."""
        ...

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        """Marca en el CRM si el inmueble del deal resultó duplicado en Xposure."""
        ...

    def add_comment(self, deal_id: str, comment: str) -> int | None:
        """Agrega un comentario al deal. Retorna el ID del comentario, o None si falla."""
        ...

    def pin_comment(self, comment_id: int, deal_id: str) -> None:
        """Fija un comentario en el deal (best-effort, no lanza si falla)."""
        ...
