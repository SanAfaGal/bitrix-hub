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
