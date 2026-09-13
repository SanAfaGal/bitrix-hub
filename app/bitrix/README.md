# app/bitrix/

Implementación concreta de `app.crm.protocol.CrmClient` contra Bitrix24 REST
(vía incoming webhook, `BITRIX_WEBHOOK_URL`). Es la única implementación de
CRM que existe hoy — ver `app/crm/README.md` para cómo se agregaría una
segunda.

## Estructura

- `client.py` — `BitrixClient`, compuesto de mixins (`client_deals.py`,
  `client_contacts.py`, `client_files.py`, `client_sectors.py`) más
  helpers privados compartidos en `_shared.py`.
- `fields.py` — todo el conocimiento específico de Bitrix que el resto del
  hub no debe ver: IDs de campo `UF_CRM_*`, VALUE IDs de picklist. Callers
  fuera de este paquete nunca ven un campo crudo, solo los métodos de
  `CrmClient` (`get_matricula`, `set_duplicado_status`, ...).
- `deps.py::get_bitrix_client()` — factory consumida por
  `app/crm/deps.py::get_crm_client()`.

## Picklists con VALUE ID fijo por instalación

Bitrix obliga a algunos campos a un VALUE ID numérico que solo existe
corriendo `scripts/list_bitrix_picklist_values.py <campo>` contra el Bitrix
real — no se puede adivinar. `PROPERTY_TYPE_VALUE_BY_NAME` y
`SOURCE_VALUE_BY_NAME` en `fields.py` ya están completos contra esta
instalación; si Bitrix agrega una opción nueva a cualquiera de los dos
picklists, hay que volver a correr el script y agregar la entrada acá —
mientras un nombre no tenga VALUE ID mapeado, `update_property_listing`/
`create_property_seller_deal` lo omiten en silencio (loguean un
warning) en vez de fallar.
