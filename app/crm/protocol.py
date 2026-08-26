"""Contrato que debe cumplir cualquier cliente de CRM usado por el hub.

Solo incluye las operaciones que los flows/forms reales necesitan hoy — no
es un mapeo genérico de "toda la API de un CRM". Un CRM nuevo se agrega
implementando esta clase (duck typing: no hace falta heredar de ella).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

AuthorizationStatus = Literal["pendiente_envio", "pendiente_firma", "firmada"]


@dataclass(frozen=True)
class PropertyListing:
    """Datos de un inmueble que un cliente quiere vender, ya recolectados en el CRM.

    Un campo en `None` significa "todavía no se sabe" — no "vacío a propósito".
    `property_type` es uno de los valores de `app.forms.models.PROPERTY_TYPES`.
    """

    property_type: str | None = None
    address: str | None = None
    sector_zone_city: str | None = None
    expected_sale_price: int | None = None
    registration_number: str | None = None


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

    def get_authorization_status(self, deal: dict[str, Any]) -> AuthorizationStatus | None:
        """Extrae el estado de firma de la Autorización de Corretaje de un deal ya obtenido con get_deal."""
        ...

    def set_authorization_status(self, deal_id: str, status: AuthorizationStatus) -> None:
        """Marca en el CRM el estado de firma de la Autorización de Corretaje del deal."""
        ...

    def set_welcome_sent(self, deal_id: str) -> None:
        """Marca en el CRM que el mensaje de bienvenida ya se envió para este deal."""
        ...

    def add_comment(self, deal_id: str, comment: str) -> int | None:
        """Agrega un comentario al deal. Retorna el ID del comentario, o None si falla."""
        ...

    def pin_comment(self, comment_id: int, deal_id: str) -> None:
        """Fija un comentario en el deal (best-effort, no lanza si falla)."""
        ...

    def upload_file(self, folder_id: str, filename: str, content: bytes) -> str | None:
        """Sube un archivo a una carpeta del drive del CRM. Retorna el link de visualización, o None si falla."""
        ...

    def find_or_create_property_seller_contact(
        self, phone: str | None, username: str | None = None, display_name: str | None = None
    ) -> str | None:
        """Busca un contacto por teléfono (o por `username` si no hay teléfono); si no existe, lo crea.

        `username` es el identificador que queda cuando WhatsApp oculta el
        número del remitente (ver `app.waha.phone.lid_from_chat_id`) — se
        guarda en un campo aparte, no reemplaza al teléfono. Al menos uno de
        `phone`/`username` debe venir con valor. `display_name`, si se
        conoce, se usa como nombre del contacto nuevo en vez de un
        placeholder genérico.

        Un contacto **solo se crea si hay `phone`** — el CRM puede tener el
        teléfono como campo obligatorio del contacto; sin `phone`, si
        `username` no matchea un contacto ya existente, retorna `None`.
        """
        ...

    def find_or_create_property_seller_deal(self, contact_id: str) -> str | None:
        """Busca un deal de consignación abierto para el contacto; si no existe, lo crea. Retorna el deal_id, o None si falla."""
        ...

    def get_property_listing(self, deal_id: str) -> PropertyListing:
        """Lee los datos del inmueble ya guardados en el deal (lo que falta queda en None)."""
        ...

    def update_property_listing(self, deal_id: str, listing: PropertyListing) -> None:
        """Actualiza en el CRM solo los campos de `listing` que no son None."""
        ...

    def get_bot_active(self, deal_id: str) -> bool:
        """Indica si el bot de WhatsApp debe seguir respondiendo en este deal.

        `True` (activo) es el default cuando el deal no tiene el campo
        seteado — un asesor lo pausa marcándolo manualmente en el CRM, o el
        propio bot lo pausa vía `set_bot_active` cuando detecta que la
        persona pidió hablar con un humano.
        """
        ...

    def set_bot_active(self, deal_id: str, active: bool) -> None:
        """Marca en el CRM si el bot de WhatsApp debe seguir respondiendo en este deal."""
        ...
