"""IDs de campos custom (`UF_CRM_*`) y mapas de VALUE de esta instancia de Bitrix.

Solo datos, sin lógica de negocio — los métodos que los usan viven en
`app/bitrix/client.py`. Se separa acá porque esta lista crece con cada
integración nueva y no aporta nada mezclada con la clase del cliente HTTP.
"""
from __future__ import annotations

FIELD_CONTACT_ID = "CONTACT_ID"

FIELD_MATRICULA = "UF_CRM_1773860489786"

FIELD_DUPLICADO = "UF_CRM_1773861337167"
VALUE_SIN_DUPLICADO = 89296
VALUE_DUPLICADO = 89298

FIELD_WELCOME_SENT = "UF_CRM_1776879856695"

FIELD_AUTHORIZATION_STATUS = "UF_CRM_1773864282733"
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
FIELD_PROPERTY_TYPE = "UF_CRM_1773860139420"
FIELD_ADDRESS = "UF_CRM_1773860692300"
FIELD_SECTOR_ZONE_CITY = "UF_CRM_1773861181680"
FIELD_EXPECTED_SALE_PRICE = "UF_CRM_1773861238965"
FIELD_FIRST_CONTACT = "UF_CRM_1773860044607"

# Identificador de respaldo cuando WhatsApp oculta el teléfono del remitente
# (chat "@lid" en vez de "@c.us" — ver app.waha.phone.lid_from_chat_id).
FIELD_USERNAME = "UF_CRM_1786458989056"

# TODO: reemplazar por el ID real una vez creado en Bitrix (checkbox, mismo
# patrón que FIELD_WELCOME_SENT). Vacío/None se interpreta como "activo" —
# ver BitrixClient.get_bot_active — así los deals existentes sin el campo no
# quedan pausados por defecto.
FIELD_BOT_ACTIVE = "UF_CRM_0000000000000"

# Pipeline "Consignación" donde caen los deals nuevos creados por el bot.
CONSIGNACION_CATEGORY_ID = 34

# TODO: llenar corriendo `scripts/list_bitrix_picklist_values.py UF_CRM_1773860139420`
# contra el Bitrix real — no se puede adivinar el VALUE ID de cada tipo de
# inmueble. Mientras esté vacío, `BitrixClient.update_property_listing`
# ignora `property_type` (loguea un warning, no rompe el resto del update).
PROPERTY_TYPE_VALUE_BY_NAME: dict[str, int] = {}
