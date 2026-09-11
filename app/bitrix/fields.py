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

# Pipeline "Consignación" donde caen los deals nuevos creados por el bot.
CONSIGNACION_CATEGORY_ID = 34

# Canal de origen del deal, obligatorio en Bitrix — ver
# BitrixClient.find_or_create_property_seller_deal. El bot de WhatsApp y
# graph_lead_intake.py asignan el suyo fijo; el formulario interno lo deja
# elegir al captador (ver app.crm.protocol.SOURCE_CHANNELS). El resto del
# picklist que no aparece acá ("Aviso", etc.) se asigna a mano en Bitrix.
FIELD_SOURCE = "UF_CRM_1787836749518"
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

# VALUE ID reales del picklist UF_CRM_1773860139420 en Bitrix (confirmados
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
FIELD_SECTOR_UBICACION = "UF_CRM_20_1789057091643"
FIELD_SECTOR_CODE = "UF_CRM_20_1789060466273"
