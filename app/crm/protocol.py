"""Contrato que debe cumplir cualquier cliente de CRM usado por el hub.

Solo incluye las operaciones que los flows/forms reales necesitan hoy — no
es un mapeo genérico de "toda la API de un CRM". Un CRM nuevo se agrega
implementando esta clase (duck typing: no hace falta heredar de ella).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

AuthorizationStatus = Literal["pendiente_envio", "pendiente_firma", "firmada"]

DealSource = Literal[
    "whatsapp", "pagina_web", "referido", "captacion", "email_marketing", "servicio_al_cliente", "redes_sociales_ads"
]

# Canales que un captador puede elegir a mano en el formulario interno (ver
# app/interno/) — (identificador, label visible), mismo NAME/VALUE que el
# picklist "Canal de origen" (UF_CRM_1787836749518) tiene en Bitrix.
# "whatsapp" no aparece: ese origen lo asigna automáticamente el bot
# (app/flows/whatsapp_bot_identity.py), no algo que se escoja a mano.
SOURCE_CHANNELS: tuple[tuple[str, str], ...] = (
    ("referido", "Referido"),
    ("captacion", "Captación"),
    ("pagina_web", "Página Web"),
    ("email_marketing", "Email Marketing"),
    ("servicio_al_cliente", "Servicio al cliente"),
    ("redes_sociales_ads", "Redes Sociales Ads"),
)


@dataclass(frozen=True)
class PropertyListing:
    """Datos de un inmueble que un cliente quiere vender, ya recolectados en el CRM.

    Un campo en `None` significa "todavía no se sabe" — no "vacío a propósito".
    `property_type` es uno de los valores de `app.forms.models.PROPERTY_TYPES`.
    """

    property_type: str | None = None
    address: str | None = None
    expected_sale_price: int | None = None
    registration_number: str | None = None
    location_sector_code: str | None = None
    """sector_code de Mobilia (el mismo que identifica el sector en el
    catálogo de app.location_catalog) — no un id interno de Bitrix. Cada CRM
    resuelve internamente cómo vincular esto a su propio modelo de datos;
    ver BitrixClient.update_property_listing/find_sector_item_id_by_code."""


class CrmClient(Protocol):
    def get_deal(self, deal_id: str) -> dict[str, Any]:
        """Obtiene los campos de un deal/negocio. Retorna {} si falla o no existe."""
        ...

    def deal_exists(self, deal_id: str) -> bool:
        """Confirma si un deal existe en el CRM. Ante error ambiguo (red, timeout), asume que existe."""
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

    def find_contact_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Busca un contacto ya existente para `phone`. Retorna sus campos, o None si no hay match.

        Usado para decidir la plantilla de bienvenida del bot de WhatsApp
        (cliente conocido vs. desconocido) — a diferencia de
        `find_or_create_property_seller_contact`, nunca crea nada.
        """
        ...

    def get_contact_full_name(self, contact: dict[str, Any]) -> str | None:
        """Extrae el nombre completo de un contacto ya obtenido con get_contact/find_contact_by_phone."""
        ...

    def get_matricula(self, deal: dict[str, Any]) -> str | None:
        """Extrae la matrícula/registro del inmueble de un deal ya obtenido con get_deal."""
        ...

    def set_duplicado_status(self, deal_id: str, has_duplicate: bool) -> None:
        """Marca en el CRM si el inmueble del deal resultó duplicado en Xposure."""
        ...

    def find_property_seller_deal_id(self, contact_id: str) -> str | None:
        """Busca (sin crear) un deal de consignación ya existente para el contacto.

        A diferencia de `find_or_create_property_seller_deal`, nunca crea
        nada — usado para saber de antemano si un lead nuevo en realidad
        va a reusar un deal existente (ver `app.flows.interno_nuevo_lead`).
        """
        ...

    def get_authorization_status(self, deal: dict[str, Any]) -> AuthorizationStatus | None:
        """Extrae el estado de firma de la Autorización de Corretaje de un deal ya obtenido con get_deal."""
        ...

    def set_authorization_status(self, deal_id: str, status: AuthorizationStatus) -> None:
        """Marca en el CRM el estado de firma de la Autorización de Corretaje del deal."""
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
        self,
        phone: str | None,
        username: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
    ) -> str | None:
        """Busca un contacto por teléfono (o por `username` si no hay teléfono); si no existe, lo crea.

        `username` es el identificador que queda cuando WhatsApp oculta el
        número del remitente (ver `app.waha.phone.lid_from_chat_id`) — se
        guarda en un campo aparte, no reemplaza al teléfono. Al menos uno de
        `phone`/`username` debe venir con valor. `display_name`, si se
        conoce, se usa como nombre del contacto nuevo en vez de un
        placeholder genérico. `email`, si se conoce (ej. lead de formulario
        web), se guarda en el contacto nuevo — no afecta la búsqueda de
        duplicados, que sigue siendo solo por teléfono/username.

        Un contacto **solo se crea si hay `phone`** — el CRM puede tener el
        teléfono como campo obligatorio del contacto; sin `phone`, si
        `username` no matchea un contacto ya existente, retorna `None`.
        """
        ...

    def update_contact_identity(self, contact_id: str, *, phone: str | None = None, full_name: str | None = None) -> None:
        """Actualiza nombre y/o teléfono de un contacto ya existente, solo lo que no es `None`.

        Se usa cuando la persona confirma su nombre/teléfono en la
        conversación después de que el contacto ya se creó (con un
        placeholder de nombre, o solo con `username` sin teléfono).
        """
        ...

    def find_or_create_property_seller_deal(
        self, contact_id: str, title: str | None = None, source: DealSource | None = None
    ) -> str | None:
        """Busca un deal de consignación abierto para el contacto; si no existe, lo crea. Retorna el deal_id, o None si falla.

        `title`, si se pasa, se usa como título del deal nuevo en vez del
        default (pensado para orígenes distintos a WhatsApp, ej. leads de
        formulario web) — no tiene efecto si el deal ya existía.

        `source`, si se pasa, marca el canal de origen del deal nuevo —
        tampoco tiene efecto si el deal ya existía, porque el canal de
        origen es propio del primer contacto, no se reescribe en cada
        reintento.
        """
        ...

    def get_property_listing(self, deal_id: str) -> PropertyListing:
        """Lee los datos del inmueble ya guardados en el deal (lo que falta queda en None)."""
        ...

    def update_property_listing(self, deal_id: str, listing: PropertyListing) -> None:
        """Actualiza en el CRM solo los campos de `listing` que no son None."""
        ...

