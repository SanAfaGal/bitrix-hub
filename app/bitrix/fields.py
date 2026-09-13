"""Catálogo de campos custom (`UF_CRM_*`) y mapas de VALUE de esta instancia de Bitrix.

Solo datos, sin lógica de negocio — los métodos que los usan viven en
`app/bitrix/client.py`. Se separa acá porque esta lista crece con cada
integración nueva y no aporta nada mezclada con la clase del cliente HTTP.

Cada campo custom es un `FieldSpec`, no un string suelto — este portal tiene
varios campos parecidos (ej. `FIELD_SECTOR_UBICACION` del Smart Process de
Sectores vs. `FIELD_DEAL_UBICACION_SECTOR` del deal) y ya hubo confusión
entre ellos. `FieldSpec.uf_crm` es el `UF_CRM_*` real que se manda a Bitrix;
los call sites usan `fields.FIELD_X.uf_crm` como key/valor de la API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FIELD_CONTACT_ID = "CONTACT_ID"


@dataclass(frozen=True)
class FieldSpec:
    uf_crm: str
    label: str
    entity: str  # "deal" | "sector_item"
    pipeline: str | None  # embudo/categoría donde aplica; None si es de todos
    field_type: str  # "string" | "enumeration" | "crm" | "money" | "date" | "int"
    description: str


FIELD_MATRICULA = FieldSpec(
    uf_crm="UF_CRM_1773860489786",
    label="Matrícula",
    entity="deal",
    pipeline=None,
    field_type="string",
    description="Número de matrícula inmobiliaria del inmueble.",
)

FIELD_DUPLICADO = FieldSpec(
    uf_crm="UF_CRM_1773861337167",
    label="Duplicado",
    entity="deal",
    pipeline=None,
    field_type="enumeration",
    description="Si el deal es un duplicado de otro ya existente (detectado por matrícula).",
)
VALUE_SIN_DUPLICADO = 89296
VALUE_DUPLICADO = 89298

FIELD_AUTHORIZATION_STATUS = FieldSpec(
    uf_crm="UF_CRM_1773864282733",
    label="Estado de autorización",
    entity="deal",
    pipeline=None,
    field_type="enumeration",
    description="Estado de la Autorización de Corretaje: pendiente de envío, pendiente de firma o firmada.",
)
VALUE_AUTHORIZATION_PENDIENTE_ENVIO = 89306
VALUE_AUTHORIZATION_PENDIENTE_FIRMA = 89308
VALUE_AUTHORIZATION_FIRMADA = 89310
AUTHORIZATION_STATUS_BY_VALUE = {
    VALUE_AUTHORIZATION_PENDIENTE_ENVIO: "pendiente_envio",
    VALUE_AUTHORIZATION_PENDIENTE_FIRMA: "pendiente_firma",
    VALUE_AUTHORIZATION_FIRMADA: "firmada",
}
AUTHORIZATION_VALUE_BY_STATUS = {
    "pendiente_envio": VALUE_AUTHORIZATION_PENDIENTE_ENVIO,
    "pendiente_firma": VALUE_AUTHORIZATION_PENDIENTE_FIRMA,
    "firmada": VALUE_AUTHORIZATION_FIRMADA,
}

# Campos del inmueble que un cliente quiere vender (bot de WhatsApp,
# experimental — ver app/flows/whatsapp_bot.py).
FIELD_PROPERTY_TYPE = FieldSpec(
    uf_crm="UF_CRM_1773860139420",
    label="Tipo de inmueble",
    entity="deal",
    pipeline=None,
    field_type="enumeration",
    description="Tipo de inmueble que el cliente quiere vender (picklist, ver PROPERTY_TYPE_VALUE_BY_NAME).",
)
FIELD_ADDRESS = FieldSpec(
    uf_crm="UF_CRM_1773860692300",
    label="Dirección",
    entity="deal",
    pipeline=None,
    field_type="string",
    description="Dirección del inmueble a vender.",
)
FIELD_EXPECTED_SALE_PRICE = FieldSpec(
    uf_crm="UF_CRM_1773861238965",
    label="Precio esperado de venta",
    entity="deal",
    pipeline=None,
    field_type="money",
    description="Precio esperado de venta que indica el cliente.",
)
FIELD_FIRST_CONTACT = FieldSpec(
    uf_crm="UF_CRM_1773860044607",
    label="Primer contacto",
    entity="deal",
    pipeline=None,
    field_type="date",
    description="Fecha del primer contacto con el cliente.",
)

# Identificador de respaldo cuando WhatsApp oculta el teléfono del remitente
# (chat "@lid" en vez de "@c.us" — ver app.waha.phone.lid_from_chat_id). Campo
# dedicado en Bitrix ("Link ID") — antes se guardaba en "Nombre de Usuario"
# (UF_CRM_1786458989056), ya no se usa para esto.
FIELD_LINK_ID = FieldSpec(
    uf_crm="UF_CRM_1789150797407",
    label="Link ID",
    entity="contact",
    pipeline=None,
    field_type="string",
    description="Identificador de WhatsApp (@lid) cuando Bitrix no puede resolver el teléfono real del remitente.",
)

# Pipeline "Consignación" donde caen los deals nuevos creados por el bot.
CONSIGNACION_CATEGORY_ID = 34

# Canal de origen del deal, obligatorio en Bitrix — ver
# BitrixClient.create_property_seller_deal. El bot de WhatsApp y
# graph_lead_intake.py asignan el suyo fijo; el formulario interno lo deja
# elegir al captador (ver app.crm.protocol.SOURCE_CHANNELS). El resto del
# picklist que no aparece acá ("Aviso", etc.) se asigna a mano en Bitrix.
FIELD_SOURCE = FieldSpec(
    uf_crm="UF_CRM_1787836749518",
    label="Canal de origen",
    entity="deal",
    pipeline=None,
    field_type="enumeration",
    description="Canal de origen del lead (picklist, ver SOURCE_VALUE_BY_NAME). Obligatorio en Bitrix.",
)
# El picklist de Bitrix no tiene una opción "WhatsApp" — "Servicio al
# cliente" es la aproximación usada a propósito para leads que llegan
# directo por WhatsApp. No renombrar a *_WHATSAPP: el VALUE real en
# Bitrix es "Servicio al cliente", y ese nombre generaba confusión.
VALUE_SOURCE_SERVICIO_AL_CLIENTE = 93060
VALUE_SOURCE_PAGINA_WEB = 93026
VALUE_SOURCE_REFERIDO = 93034
VALUE_SOURCE_CAPTACION = 93098
VALUE_SOURCE_EMAIL_MARKETING = 93170
VALUE_SOURCE_REDES_SOCIALES_ADS = 93040
SOURCE_VALUE_BY_NAME: dict[str, int] = {
    "whatsapp": VALUE_SOURCE_SERVICIO_AL_CLIENTE,
    "pagina_web": VALUE_SOURCE_PAGINA_WEB,
    "referido": VALUE_SOURCE_REFERIDO,
    "captacion": VALUE_SOURCE_CAPTACION,
    "email_marketing": VALUE_SOURCE_EMAIL_MARKETING,
    "servicio_al_cliente": VALUE_SOURCE_SERVICIO_AL_CLIENTE,
    "redes_sociales_ads": VALUE_SOURCE_REDES_SOCIALES_ADS,
}

# VALUE ID reales del picklist FIELD_PROPERTY_TYPE en Bitrix (confirmados
# contra el campo real, no adivinados) — sin esto, `update_property_listing`
# omitía `property_type` en silencio (logueaba un warning) y el deal
# quedaba con "Tipo de inmueble" vacío.
PROPERTY_TYPE_VALUE_BY_NAME: dict[str, int] = {
    "Aparta Suite": 93172,
    "Apartaestudio": 93174,
    "Apartamento": 93176,
    "Bodega": 93178,
    "Burbuja": 93180,
    "Cabaña": 93182,
    "Casa Campestre": 93184,
    "Casa Comercial": 93186,
    "Casa Vivienda": 93188,
    "Consultorio": 93190,
    "Edificio": 93192,
    "Finca": 93194,
    "Hotel": 93196,
    "Local": 93198,
    "Lote": 93200,
    "Oficina": 93202,
    "Parqueadero": 93204,
    "Penthouse": 93206,
}

# Smart Process "Sectores" (crm.item.*, ver app/bitrix/client_sectors.py) —
# sincronizado desde el catálogo de sectores de Mobilia DWH
# (app/location_catalog/), scripts/sync_mobilia_sectores.py.
SECTOR_ENTITY_TYPE_ID = 1088

# Vínculo del deal al ítem del Smart Process de Sectores — campo tipo "crm"
# (buscador de elementos de CRM), no texto libre; isMultiple=False (un solo
# vínculo, nunca una lista). Necesita el id del ítem de Bitrix en el Smart
# Process, no el sector_code de Mobilia.
FIELD_DEAL_UBICACION_SECTOR = FieldSpec(
    uf_crm="UF_CRM_1789061336",
    label="[Ventas] Ubicación",
    entity="deal",
    pipeline=None,
    field_type="crm",
    description=(
        "Vínculo al ítem del Smart Process de Sectores (entityTypeId=1088) "
        "que identifica dónde está el inmueble."
    ),
)


def sector_crm_link_value(item_id: str) -> str:
    """Value que Bitrix espera para vincular `FIELD_DEAL_UBICACION_SECTOR` a
    un ítem del Smart Process de Sectores — formato `T{hex(entityTypeId)}_{id}`
    (confirmado contra Bitrix real y contra la documentación oficial:
    https://apidocs.bitrix24.com/api-reference/crm/data-types.html, sección
    "Vínculo a elementos de CRM": el prefijo de un objeto dinámico (SPA) es
    `T` + el entityTypeId en hexadecimal minúscula; ej. entityTypeId=128 →
    prefijo `T80`). No es una lista aunque el campo permita "isMultiple" en
    otras instancias — acá `isMultiple=False`, va como string plano.
    """
    return f"T{SECTOR_ENTITY_TYPE_ID:x}_{item_id}"


def sector_item_id_from_crm_link_value(value: Any) -> str | None:
    """Inverso de `sector_crm_link_value`: de `"T{hex(entityTypeId)}_{id}"` (lo
    que devuelve Bitrix al leer `FIELD_DEAL_UBICACION_SECTOR`) extrae el `id`
    del ítem del Smart Process de Sectores. `None` si `value` no viene en ese
    formato (campo vacío, u otro tipo de vínculo)."""
    if not isinstance(value, str):
        return None
    prefix = f"T{SECTOR_ENTITY_TYPE_ID:x}_"
    if not value.startswith(prefix):
        return None
    item_id = value[len(prefix) :]
    return item_id or None
FIELD_SECTOR_UBICACION = FieldSpec(
    uf_crm="UF_CRM_20_1789057091643",
    label="Ubicación",
    entity="sector_item",
    pipeline=None,
    field_type="string",
    description="Etiqueta de ubicación del sector (build_location_label), sincronizada desde Mobilia.",
)
FIELD_SECTOR_CODE = FieldSpec(
    uf_crm="UF_CRM_20_1789060466273",
    label="ID Sector (Mobilia)",
    entity="sector_item",
    pipeline=None,
    field_type="string",
    description="sector_code de Mobilia — clave de negocio del ítem, requerido por Bitrix al crear.",
)
