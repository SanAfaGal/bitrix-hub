# Sincronización de sectores Mobilia → Bitrix — diseño y porqués

Documento de referencia para `scripts/sync_mobilia_sectores.py` +
`app/location_catalog/sector_sync.py` + `app/bitrix/client_sectors.py`. No
repite línea a línea lo que ya dicen los docstrings — arma el panorama
completo: qué hace, por qué quedó así, y qué queda pendiente de confirmar
contra el Bitrix real.

Ver también: `app/location_catalog/normalize.py` (normalización compartida
con el formulario web), `app/bitrix/client.py` (por qué `BitrixClient` es un
composite de mixins), `app/flows/README.md` (por qué este sync NO vive ahí).

## Qué hace

Copia el catálogo de sectores de `mobilia_dwh` (vista `cat_mobilia_sectores`)
hacia el Smart Process de Bitrix `entityTypeId=1088`. **Mobilia es la única
fuente de verdad; Bitrix es un espejo.** Corre sola cada `SECTOR_SYNC_INTERVAL_DAYS`
días (default 7) vía `app/scheduler.py::job_sync_sectores` — el script
(`uv run python scripts/sync_mobilia_sectores.py`) queda para correrlo a
mano fuera de ese ciclo (ej. con `--dry-run` para revisar antes de esperar
a la próxima corrida automática).

## Campos de Mobilia usados

De `cat_mobilia_sectores` (vía `app.location_catalog.client.fetch_all_sectores`,
ya existente, reutilizado tal cual): `sector_code` (clave de negocio, string —
**nunca** se castea a int, hay códigos con ceros a la izquierda como
`"00083"`), `sector`, `zona`, `ciudad`, `departamento`, `pais`. `cobertura_ventas`
se lee pero no se usa en este sync (ver "Qué pasa cuando un sector
desaparece" abajo).

No hay columna `estado` ni `ubicacion` literal en la vista — `ubicacion` se
calcula (ver siguiente sección).

## Limpieza, transformación y normalización — compartida con el formulario web

`app.location_catalog.normalize.build_location_label(sector, zona, ciudad,
departamento, pais)` es la misma función que ya usa el formulario web
(`fetch_all_locations`) para mostrar la ubicación. Este sync la reutiliza
**tal cual, sin ningún formato nuevo** — el campo Ubicación en Bitrix recibe
exactamente el valor de salida de esa función
(`app.location_catalog.sector_sync.build_target_fields`). Decisión explícita:
no crear un formato alterno "Sector - Zona - Ciudad"; lo que ve el visitante
del formulario es lo que se sincroniza (ver el bug de guion colgado corregido
más abajo, único ajuste hecho a `normalize.py` durante este trabajo).

La comparación para decidir si hace falta un `update` (`needs_update`) se
hace sobre esos valores ya normalizados, nunca sobre los crudos del DWH —
así que espacios extra, mayúsculas o rellenos que la normalización ya
resuelve no generan updates innecesarios.

**Bug de guion colgado corregido en `_strip_trailing_word_block`** (afecta
también al formulario web, no solo a este sync): cuando el bloque de
palabras repetido que se quita estaba pegado a un separador suelto (ej. zona
"Abriaquil - antioquia" con departamento "Antioquia"), el "-" sobrevivía como
último token tras el split por espacios, dando `"Abriaquil, Abriaquil -,
Abriaquí, Antioquia, Colombia"` (sector_code 5988, visto en la prueba real
contra Bitrix). Corregido: tras quitar el bloque, también se descartan los
tokens finales que no tengan ningún caracter alfanumérico. Alcance acotado a
propósito — no se tocan paréntesis, comas internas de un campo ni puntos de
abreviaturas ("D.C."), esos casos son raros en la fuente (menos de 30 de
1.561 sectores) y no son un bug, solo estilo de los datos de origen.

**TITLE nunca se manda, ni al crear ni al actualizar.** Bitrix ya tiene una
regla de automatización configurada en el Smart Process que arma el nombre
del ítem concatenando campos existentes (confirmado contra Bitrix real: al
mandar nosotros `TITLE="Abejorral, Antioquia, Colombia"` en una prueba
anterior, Bitrix lo reescribió como `"678 - Abejorral, Antioquia, Colombia"`
de todas formas). Dejarlo fuera del payload evita competir con esa regla.
`needs_update` por lo tanto solo compara Ubicación.

## Campos de Bitrix sincronizados

Smart Process `entityTypeId=1088` (constantes en `app/bitrix/fields.py`):

| Campo Bitrix | Nombre técnico | Contenido |
|---|---|---|
| `TITLE` (estándar) | — | No se manda — lo arma una regla de automatización de Bitrix concatenando campos del ítem |
| Ubicación | `UF_CRM_20_1789057091643` | `build_location_label(...)` |
| ID Sector (Mobilia) | `UF_CRM_20_1789060466273` | `sector.sector_code` (string) — clave de negocio, también se manda en cada create/update: Bitrix lo exige como campo requerido |

## Cómo se identifica un sector

`UF_CRM_20_1789060466273` == `sector_code` de Mobilia, comparado como string
en ambos lados. Nunca se genera un ID nuevo para un sector ya existente ni se
elige un ID por nombre concatenado.

## Comportamiento

- **Sector nuevo en Mobilia, no en Bitrix** → se crea (`crm.item.add` vía batch).
- **Sector existente con datos cambiados** (Ubicación normalizada distinta a
  lo que ya hay en Bitrix) → se actualiza (`crm.item.update` vía batch). Si
  no cambió nada, no se toca (cuenta como "sin cambios").
- **`sector_code` duplicado dentro de la fuente** → **todas** sus apariciones
  se excluyen de la sincronización (nunca se elige una silenciosamente) y se
  reporta en `skipped_duplicates`.
- **Sector que desaparece de Mobilia** (existe en Bitrix, ya no en la fuente)
  → **no se toca, no se borra, no se desactiva.** Fuera de alcance a
  propósito: la vista no tiene una columna de estado del registro en sí
  (`cobertura_ventas` es un flag de si Mobilia vende ahí, no de si el sector
  sigue existiendo) y Bitrix hoy no tiene un campo de estado en este Smart
  Process. Se reporta solo informativamente en `missing_from_source`.
- **Idempotencia**: correr el script dos veces seguidas sin cambios en
  Mobilia da `Creados: 0, Actualizados: 0, Sin cambios: N, Errores: 0`.
- **Errores por ítem** no abortan la corrida — se acumulan con
  `sector_code`/etapa/operación/mensaje y se listan en el resumen final.

## Diseño (dónde vive cada cosa)

```
Mobilia (cat_mobilia_sectores)
      ↓  fetch_all_sectores()                        app/location_catalog/client.py (ya existía)
      ↓  dedupe_source() + build_target_fields()      app/location_catalog/sector_sync.py
      ↓  (build_location_label ya existente)          app/location_catalog/normalize.py (ya existía)
Bitrix (crm.item.list entityTypeId=1088)               app/bitrix/client_sectors.py (SectorsMixin)
      ↓  plan_sync() (diff puro, sin I/O)              app/location_catalog/sector_sync.py
      ↓  batch_upsert_sector_items()                   app/bitrix/client_sectors.py
run_sync() orquesta todo                                app/location_catalog/sector_sync.py
scripts/sync_mobilia_sectores.py                        entrypoint manual, --dry-run
```

`app/bitrix/client_sectors.py` agrega `SectorsMixin` a `BitrixClient`
(mismo patrón que `client_deals.py`/`client_contacts.py`/`client_files.py`:
nunca lanza, loguea y devuelve `None`/`False`, usa `app/bitrix/_shared.py`).
Usa `batch.json` (máx. 50 comandos por lote, `halt=0`) para no hacer una
llamada HTTP por sector — con ~1.500 sectores serían ~30 llamadas en vez de
1.500.

La orquestación (`sector_sync.py`) vive en `app/location_catalog/`, no en
`app/flows/`: `app/flows/` es para flujos disparados por un webhook de
Bitrix con su propio router HTTP (ver `app/flows/README.md`). Este sync no
tiene trigger ni endpoint, lo corre una persona a mano. Igual mantiene la
misma disciplina de una flow: recibe `BitrixClient` ya construido como
parámetro en vez de importarlo para construirlo él mismo.

El Smart Process no entra al `CrmClient` Protocol (`app/crm/protocol.py`):
es específico de Bitrix, no algo que otro CRM vaya a implementar.

## Ejecución

```bash
# sincroniza de verdad
uv run python scripts/sync_mobilia_sectores.py

# solo reporta qué haría, no escribe nada en Bitrix
uv run python scripts/sync_mobilia_sectores.py --dry-run

# limita a los primeros N sectores de la fuente — para probar sin tocar los ~1.500 de una vez
uv run python scripts/sync_mobilia_sectores.py --limit 3
uv run python scripts/sync_mobilia_sectores.py --dry-run --limit 3
```

Requiere `BITRIX_WEBHOOK_URL` y `MOBILIA_DWH_*` en `.env` — ya existían para
otras features de este repo, no se agregó ninguna variable nueva.

Salida: resumen con total origen, creados, actualizados, sin cambios,
duplicados omitidos (con sus códigos), ítems de Bitrix ausentes en la fuente
(informativo) y errores (con `sector_code`/etapa/operación/mensaje). Sale con
código 1 si hubo algún error.

## Comportamiento real de Bitrix, confirmado con una prueba de 3 sectores

No había antecedente de Smart Process (`crm.item.*`) en este repo — se probó
`--dry-run --limit 3` y luego `--limit 3` (creación real) contra el Bitrix de
producción antes de confiar en una corrida completa. Esto salió distinto de
lo documentado por Bitrix y quedó corregido en el código:

1. **`select` con nombres de campo explícitos (`"id"`, `"title"`, en cualquier
   mayúscula/minúscula) hace que este portal los omita del resultado por
   completo** — `crm.item.list` devolvía solo los campos `UF_CRM_*`
   solicitados, sin `id` ni `title`, rompiendo el índice por ítem. Corregido:
   `list_sector_items` manda `select=["*","UF_*"]` (estándar completo + todos
   los custom), que sí devuelve `id`/`title`.
2. **`TITLE` no se guarda tal cual se envía** — este Smart Process tiene una
   regla de automatización configurada en el portal que arma el título
   concatenando campos del ítem (antepone el ID Sector), pisando cualquier
   `TITLE` explícito. Corregido dos veces: primero se ajustó `needs_update`
   para ignorar TITLE en la comparación (evitaba el update infinito), y
   después se dejó de mandar `TITLE` por completo — no tiene sentido pelear
   contra una regla que ya existe en el portal.
3. **`UF_CRM_20_1789060466273` (ID Sector) es un campo requerido al crear** —
   la primera versión de `build_target_fields` no lo incluía en el payload y
   Bitrix rechazaba el create con `CRM_FIELD_ERROR_REQUIRED`. Corregido:
   ahora se manda en cada create/update.
4. `useOriginalUfNames=Y` sí devuelve `UF_CRM_20_...` (no `ufCrm20_...`) en
   este portal — confirmado, sin cambios.
5. El webhook de `BITRIX_WEBHOOK_URL` sí tiene permiso sobre
   `entityTypeId=1088` — confirmado (create/update/list funcionaron).

Sigue sin probarse contra Bitrix real: el shape exacto de `result_error`
dentro de `batch.call` ante un error real (el `error_detail` visto hasta
ahora viene de errores devueltos por `crm.item.add` directo, no dentro de un
batch) — el parser trata "la key está en `result_error`" como fallo sin
importar el shape interno, pero no se vio un batch con error real todavía.

**Los 3 sectores de prueba (`sector_code` 678, 5988, 507001) quedaron creados
de verdad en el Smart Process 1088** — revisar/limpiar a mano si no se
quieren ahí antes de la corrida completa.

## Pendiente del lado de Bitrix (no del código): la regla de automatización solo corrió al crear

Confirmado con el sector 5988: se actualizó Ubicación vía `crm.item.update`
(se corrigió el guion colgado), pero el `title` del ítem se quedó con el
valor viejo (`"Abriaquil, Abriaquil -, Abriaquí, Antioquia, Colombia"`) — la
regla de automatización que arma TITLE concatenando campos parece disparar
solo al crear el ítem, no en cada update de campo. Este sync nunca manda
TITLE (decisión explícita, ver arriba), así que si esa regla no se dispara en
updates, el título de un sector puede quedar desactualizado respecto a
Ubicación con el tiempo (cosmético — Ubicación, el dato que importa para
identificar/buscar el sector, sí queda siempre correcto). Revisar del lado de
Bitrix si la regla debe configurarse para disparar también en actualización
de campo, si se quiere que el título se mantenga al día.
