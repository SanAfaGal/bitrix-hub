# Campo "[Ventas] Ubicación" del deal — investigación y formato real

Documento de referencia para `FIELD_DEAL_UBICACION_SECTOR` en
`app/bitrix/fields.py`, `BitrixClient.find_sector_item_id_by_code`/
`update_property_listing` en `app/bitrix/client_sectors.py`/`client_deals.py`,
y `PropertyListing.location_sector_code` en `app/crm/protocol.py`. Cubre por
qué el campo no se llenaba, cómo se encontró el formato real que Bitrix
espera, y qué queda fuera de alcance.

## Qué es

El deal en Bitrix tiene un campo `[Ventas] Ubicación` (`UF_CRM_1789061336`),
tipo "vínculo a elemento de CRM" — un buscador que, en este portal, busca
entre los ítems del Smart Process "Sectores" (`entityTypeId=1088`, ver
`docs/sync-mobilia-sectores.md`). No es texto libre: guarda una referencia al
ítem del Smart Process, no una copia del nombre del sector.

## Root cause: por qué nunca se llenaba

Este campo no aparecía en ningún lugar del código — nunca se conectó. Lo que
sí existía y se confundía fácilmente con él era `FIELD_SECTOR_ZONE_CITY`
(`UF_CRM_1773861181680`), un campo de texto libre **ya eliminado de Bitrix**
(confirmado por el usuario) que además, al viajar siempre junto a los demás
campos del deal en un único `crm.deal.update`, rompía en silencio esas otras
actualizaciones (Bitrix rechaza el update completo si trae un UF
inexistente). Se eliminó del código por completo.

## El formato del value — investigación contra Bitrix real

Un campo tipo "vínculo a elemento de CRM" no acepta el `sector_code` de
Mobilia ni el nombre del sector — necesita el **id del ítem de Bitrix** en
el Smart Process 1088 (resuelto por `find_sector_item_id_by_code`), envuelto
en el formato que esta clase de campo espera. No había antecedente en este
repo de escribir este tipo de campo, así que se verificó contra un deal de
prueba real (creado y borrado durante esta investigación, `TITLE="PRUEBA
formato Ubicacion (borrar)"`) en vez de confiar solo en la documentación.

Primero, `crm.deal.fields` confirmó la forma del campo:

```json
{
  "type": "crm",
  "isMultiple": false,
  "isDynamic": true,
  "settings": { "DYNAMIC_1088": "Y" }
}
```

`isMultiple: false` ya descartaba mandar una lista — la primera versión del
código mandaba `[sector_item_id]` (una lista de un solo elemento) y Bitrix
la aceptaba sin error pero la guardaba como `""` (campo vacío) — **esta era
la causa directa de que el campo no quedara vinculado**, aunque el resto del
`crm.deal.update` sí aplicara.

Se probaron varios formatos de string contra el deal de prueba, leyendo con
`crm.deal.get` después de cada uno:

| Value enviado | `crm.deal.update` | Guardado (`crm.deal.get`) | Se ve en la UI de Bitrix |
|---|---|---|---|
| `["16"]` (lista) | sin error | `""` (vacío) | vacío |
| `"16"` (id sin prefijo) | sin error | `"16"` | vacío |
| `"1088_16"` (entityTypeId decimal) | sin error | `"1088_16"` | vacío |
| `"DYNAMIC_1088_16"` | sin error | `"DYNAMIC_1088_16"` | vacío |
| `"T440_16"` (`T` + hex del entityTypeId) | sin error | `"T440_16"` | **vinculado correctamente** |

Ninguno de los formatos incorrectos devolvió error — Bitrix no valida el
contenido de un campo `crm` al escribirlo por API, solo lo guarda tal cual.
Sin verificación visual en la UI, cualquiera de esos formatos parecía
"funcionar" (el `crm.deal.update`/`crm.deal.get` hacían round-trip sin
quejarse). La única forma de confirmar cuál era el correcto fue mirar el
campo en la UI de Bitrix después de cada intento.

El formato real está documentado en la [documentación oficial de Bitrix24
sobre tipos de datos de CRM](https://apidocs.bitrix24.com/api-reference/crm/data-types.html),
sección "Vínculo a elementos de CRM": el value es `{PREFIJO}_{ID}`, y para un
objeto dinámico (Smart Process/SPA) el prefijo es `T` + el `entityTypeId` en
hexadecimal minúscula (ej. `entityTypeId=128` → prefijo `T80`). Para
`entityTypeId=1088` (0x440), el prefijo es `T440` — confirmado visualmente
contra Bitrix real con `T440_16` apuntando al ítem 16 del Smart Process de
Sectores.

`app.bitrix.fields.sector_crm_link_value(item_id)` construye este value
(`f"T{SECTOR_ENTITY_TYPE_ID:x}_{item_id}"`), usado por
`BitrixClient.update_property_listing`.

## Dónde vive cada cosa

```
payload.location_sector_code (interno/forms)
      ↓
PropertyListing.location_sector_code   app/crm/protocol.py — portable, no expone IDs de Bitrix a los flows
      ↓
BitrixClient.update_property_listing   app/bitrix/client_deals.py
      ↓ find_sector_item_id_by_code    app/bitrix/client_sectors.py — busca el id del ítem por sector_code
      ↓ sector_crm_link_value          app/bitrix/fields.py — arma el value T{hex}_{id}
UF_CRM_1789061336 del deal
```

Los flows (`app/flows/interno_nuevo_lead.py`, `app/forms/router.py`) nunca
ven el id de Bitrix ni el formato del value — solo pasan
`location_sector_code` (el mismo `sector_code` de Mobilia que ya usan para
`check_coverage`). Esto respeta la regla de `app/flows/README.md`: un flow
nunca depende de detalles específicos de Bitrix, solo de `CrmClient`.

## Pendiente / fuera de alcance

- `app/interno/router.py::get_lead_detail` todavía muestra `"(pendiente)"`
  para "Ubicación" en `lead_detail.html` — `PropertyListing` ya no trae un
  texto legible de ubicación (el deal solo guarda el vínculo, no una copia
  de texto). Mostrar el sector vinculado ahí requeriría resolver
  `UF_CRM_1789061336` de vuelta a un nombre de sector (leer el ítem del
  Smart Process), no implementado todavía.
- Sin confirmar: comportamiento si `sector_code` no existe todavía en el
  Smart Process (sector nuevo en Mobilia, aún no corrido
  `scripts/sync_mobilia_sectores.py`) — el código actual loguea warning y
  sigue sin bloquear el deal, pero no se probó contra Bitrix real.
