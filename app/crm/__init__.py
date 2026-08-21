"""Interfaz genérica de CRM: punto único que el resto del hub conoce.

`app/flows/*`, `app/forms/*` y `app/waha/*` dependen de `app.crm`, nunca
directamente de `app.bitrix` — así, cambiar de CRM se reduce a agregar un
paquete nuevo que implemente `CrmClient` y apuntar `get_crm_client` a él.
"""
