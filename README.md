# bitrix-hub

Servicio único que recibe webhooks de Bitrix y dispara acciones en sistemas
externos: consulta de inmuebles en Xposure (migrado desde el repo `MLS`,
ver abajo) y envío de WhatsApp vía Waha. ERP Mobilia y otras integraciones
a futuro. Un deploy, un `.env`, modular por integración por dentro.

`MLS` (repo aparte, `../Ventas/MLS`) sigue siendo el servicio en producción
hasta que el webhook de Bitrix se repunte a este hub. Su lógica de Xposure
ya está migrada acá (`app/xposure/` + `app/flows/registry_duplicate_check.py`), pero
la automatización de Bitrix todavía apunta al endpoint de `MLS` — ver nota
de corte en la sección de despliegue más abajo.

Waha vive **en este repo** (`docker-compose.yml`, servicio `waha`) — no se
usa `../waha` como repo separado. Todo lo que ese repo aparte tenía
hardcodeado en su `docker-compose.yaml` (motor de WhatsApp, TZ, worker id,
tipo de storage de sesión, log level, etc.) ahora está en el `.env` de acá,
como cualquier otra variable — ver la sección "Waha" del bloque de
configuración abajo. No queda nada oculto en un compose de otro repo.

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker y Docker Compose (para levantar Waha; también corre el propio API)
- Credenciales de Xposure

## Configuración

```bash
cp .env.example .env
```

Variables clave (ver `.env.example` para la lista completa, incluye todas
las de Waha: engine, TZ, dashboard, logging, media, etc.):

```env
CRM_PROVIDER=bitrix
BITRIX_WEBHOOK_URL=https://tu-dominio.bitrix24.com/rest/1/tu_token/
FORM_LINK_SECRET=cambia-esto-por-un-secreto-largo-y-aleatorio
XPOSURE_BASE_URL=https://tu-dominio-xposure.com
XPOSURE_USERNAME=tu_usuario
XPOSURE_PASSWORD=tu_password
WAHA_BASE_URL=http://waha:3000
WAHA_API_KEY=your_api_key_here
WAHA_SESSION=default
WHATSAPP_DEFAULT_ENGINE=GOWS
TZ=America/Bogota
HUB_PUBLIC_BASE_URL=https://tu-dominio-bitrix-hub.com

# Bot conversacional de WhatsApp (experimental, apagado por defecto)
WHATSAPP_BOT_ENABLED=false
LLM_API_KEY=sk-tu-api-key
LLM_BASE_URL=
LLM_MODEL=gpt-4o-mini
WHATSAPP_BOT_DB_PATH=data/whatsapp_bot.db
WHATSAPP_BOT_ALLOWED_NUMBERS=
```

## Ejecución local

```bash
uv sync
uv run uvicorn app.main:app --reload
```

API disponible en http://127.0.0.1:8000/docs

Para que `app/main.py` pueda llamar a Waha necesitás el contenedor de Waha
corriendo (`docker compose up waha`, ver abajo) — el resto del API sí puede
correr suelto con `uv run uvicorn`.

`WAHA_BASE_URL` en `.env` viene seteado a `http://waha:3000` (hostname de
Docker — funciona porque `api` y `waha` están en el mismo
`docker-compose.yml`). Corriendo `app/main.py` suelto sin Docker, "waha" no
resuelve por hostname — override puntual, sin editar el archivo:

```bash
WAHA_BASE_URL=http://localhost:3000 uv run uvicorn app.main:app --reload
```

(requiere que python-dotenv no pise una variable ya seteada en el shell —
así es el comportamiento por defecto de `load_dotenv()`)

## Ejecución con Docker

```bash
docker compose up --build
```

Levanta `api`, `waha` y `whisper` (transcripción de audio, contenedor
`onerahmet/openai-whisper-asr-webservice`) juntos, en el mismo compose.
`api` espera a que `waha` y `whisper` pasen su healthcheck antes de
arrancar (`depends_on: condition: service_healthy`). Sesiones y media de
WhatsApp persisten en `./.waha-data/` (gitignored); el historial del bot de
WhatsApp (SQLite) persiste en `./.whatsapp-bot-data/` (gitignored); el
modelo de whisper descargado persiste en `./.whisper-data/` (gitignored).

Para desarrollo local, `docker compose up` carga automáticamente
`docker-compose.override.yml` (monta `./app`, agrega `--reload`) — no hace
falta pasar `-f`. En producción se corre explícitamente sin él:
`docker compose -f docker-compose.yml up -d`.

## Pruebas

```bash
uv run python -m pytest -q
```

## Estructura del proyecto

Cada integración es dueña de su router y sus dependencias de FastAPI —
`app/main.py` solo arma la app y monta routers, ninguna ruta vive ahí.

```
app/
  crm/
    protocol.py      # CrmClient (Protocol) + PropertyListing — contrato que implementa cada CRM soportado
    deps.py            # get_crm_client() — único punto que cambia si se swapea de CRM
    README.md            # Cómo agregar un CRM nuevo
  bitrix/
    client.py       # BitrixClient — implementa CrmClient (get_deal, get_contact, add_comment, pin_comment, update_deal, find_or_create_property_seller_*, ...)
    fields.py        # IDs UF_CRM_* y VALUE de picklists de esta instancia (incluye los del bot de WhatsApp)
    settings.py      # BITRIX_WEBHOOK_URL
    deps.py           # get_bitrix_client() — construye el BitrixClient concreto
  xposure/
    client.py         # XposureClient — login + search_property (migrado de MLS)
    settings.py        # XPOSURE_BASE_URL, XPOSURE_USERNAME, XPOSURE_PASSWORD
    models.py           # PropertySearchResult, BulkRequest (Pydantic, con description/examples para /docs)
    deps.py              # get_xposure_client() — atrapa errores de login y los traduce a HTTPException(502)
    router.py             # GET /properties/{tax_roll}, POST /properties/bulk (tag "Xposure")
  waha/
    client.py         # WahaClient — send_text(chat_id, text, session=None), resolve_lid_to_phone(lid, session=None)
    settings.py        # WAHA_BASE_URL, WAHA_API_KEY, WAHA_SESSION
    phone.py             # to_chat_id() / from_chat_id() / lid_from_chat_id() — conversión chatId <-> teléfono (genérico, cualquier CRM)
    inbound.py             # parse_inbound_message() — parsea el webhook `message` entrante de Waha
    events.py             # Reglas de negocio Waha-solo (vacío por ahora)
    deps.py                # get_waha_client()
    router.py               # POST /webhook/waha-test (scaffolding) y /webhook/waha-message (bot, tag "Waha")
  transcription/
    client.py         # TranscriptionClient — transcribe(audio_bytes) vía whisper-asr-webservice (contenedor propio)
    settings.py        # TRANSCRIPTION_BASE_URL, TRANSCRIPTION_LANGUAGE
    deps.py              # get_transcription_client()
  llm/
    client.py         # LlmClient — reply(system_prompt, history, user_text), SDK de OpenAI (cualquier proveedor compatible)
    settings.py        # LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    deps.py              # get_llm_client()
  flows/
    registry_duplicate_check.py    # CRM + Xposure: matrícula -> consulta -> comentario/campo (ex MLS/app/deal_event.py)
    whatsapp_bot.py                  # Waha + LLM + CRM: bot conversacional (experimental) — ver sección Endpoints
    router.py              # POST /webhook/deal-event (tag "Bitrix Webhooks")
    README.md               # Patrón para flujos que combinan >1 integración
  main.py                 # FastAPI(), openapi_tags, include_router(...), GET /health
scripts/
  resolve_bitrix_drive_folder.py     # Busca carpetas de Bitrix Drive por nombre
  list_bitrix_picklist_values.py     # Lista los VALUE ID de un campo picklist del deal (ej. Tipo de inmueble)
tests/
  fakes.py               # FakeCrmClient — fake compartido de app.crm.protocol.CrmClient
  test_bitrix_client.py
  test_waha_client.py
  test_waha_inbound.py
  test_transcription_client.py
  test_llm_client.py
  test_whatsapp_bot.py
  test_phone.py
  test_registry_duplicate_check.py
  test_main.py
```

Documentación interactiva (Swagger) con los endpoints agrupados por tag,
ejemplos por campo y los alias de formulario que acepta cada webhook:
http://127.0.0.1:8000/docs

## Cómo agregar una integración nueva

1. Crear `app/<integracion>/client.py` (cliente HTTP, sin lanzar excepciones
   en fallos de red — loguear y retornar `None`/`False`, igual que
   `bitrix/client.py` y `waha/client.py`) y `app/<integracion>/settings.py`
   (carga de env vars).
2. Si el flujo de negocio solo usa esa integración: las funciones van en
   `app/<integracion>/events.py`.
3. Si el flujo combina esta integración con otra(s): va en
   `app/flows/<nombre>.py` (ver `app/flows/README.md`; `registry_duplicate_check.py`
   es un ejemplo real ya cableado).
4. Agregar el endpoint correspondiente en `app/<integracion>/router.py` (o
   `app/flows/<nombre>/router.py` si es un flow multi-integración), con su
   propio `APIRouter(tags=["..."])`, y montarlo en `app/main.py` con
   `app.include_router(...)`. Un endpoint por disparador de Bitrix — cada
   regla de automatización en Bitrix apunta a su propia URL. No hace falta
   un dispatcher genérico: Bitrix ya decide qué se dispara cuándo.
   Documentar cada campo con `Field(description=..., examples=[...])` en
   los modelos Pydantic y `Query()`/`Path()`/`Form()` con `description=` en
   los parámetros — así queda visible y probable desde `/docs` sin leer
   código.
5. Tests unitarios del cliente (mock de `requests`) + tests del flujo con
   los clientes mockeados, siguiendo `tests/test_bitrix_client.py` y
   `tests/test_registry_duplicate_check.py`.

Para agregar (o reemplazar) el CRM en vez de una integración externa, ver
`app/crm/README.md` — el resto del hub depende de `app.crm.protocol.CrmClient`,
nunca de `BitrixClient` directamente.

Para Mobilia específicamente: no escribir un cliente nuevo desde cero, usar
el paquete ya existente
[`mobilia-erp-client`](https://github.com/albertoalvarez/mobilia-erp-client)
(`ERPClient`/`AsyncERPClient`, ya probado y en uso en otros proyectos) como
dependencia — el trabajo acá sería solo `app/mobilia/events.py` (o un flow)
que lo consuma, no un `app/mobilia/client.py`.

## Endpoints

### Salud

```bash
curl http://127.0.0.1:8000/health
```

### Consultar un inmueble (Xposure)

```bash
curl "http://127.0.0.1:8000/properties/5322493"
curl "http://127.0.0.1:8000/properties/5322493?tax_roll_area_code=001N"
curl -X POST "http://127.0.0.1:8000/properties/bulk" \
  -H "Content-Type: application/json" \
  -d '{"tax_rolls": ["5322493", "5322494"]}'
```

### Evento de deal (Bitrix webhook) — flujo matrícula/duplicado

Recibe un evento de deal de Bitrix, obtiene el deal completo y lee el campo
`UF_CRM_1773860489786` (matrícula). Si está presente, consulta Xposure y
comenta el resultado en el timeline del deal; actualiza el campo
`UF_CRM_1773861337167` (Duplicado/Sin duplicado) siempre. Ver
`app/flows/registry_duplicate_check.py`.

```bash
curl -X POST "http://127.0.0.1:8000/webhook/deal-event" \
  -d "data[FIELDS][ID]=42"
```

El comentario **solo se fija** en el timeline (pin) cuando el inmueble se
encontró y es duplicado — el caso que de verdad necesita llamar la
atención. Sin matrícula, o inmueble no encontrado, queda como comentario
normal, sin ocupar uno de los 3 espacios fijados que permite Bitrix por
entidad.

### Waha — endpoint de scaffolding (sin flujo de negocio real todavía)

```bash
curl -X POST "http://127.0.0.1:8000/webhook/waha-test?chat_id=573001112233@c.us&text=hola"
```

Sirve para confirmar que `WahaClient` llega a la instancia de Waha
configurada.

### Bot conversacional de WhatsApp (experimental)

`POST /webhook/waha-message` recibe el evento `message` que Waha reenvía
por su propio webhook saliente (no lo llamás vos directamente por curl —
lo dispara Waha en cada mensaje entrante). Responde con un LLM y, a
diferencia de un chatbot de FAQ genérico, **guarda lo que el cliente
cuenta directo en Bitrix** — pero recién cuando hay con quién asociarlo:
el bot no crea contacto ni deal en Bitrix hasta que la persona confirmó
en el chat su nombre completo y su teléfono (uno solo de los dos no
alcanza, ni siquiera si se confirman en turnos distintos). Antes de eso,
el bot conversa y responde normal por WhatsApp, pero nada queda en
Bitrix — así un asesor nunca ve negociaciones a medio llenar de alguien
que escribió una vez y no volvió. Apenas ambos datos están confirmados
se busca (o crea) el contacto y el deal de consignación (pipeline
`CATEGORY_ID=34`), y en cada turno siguiente se actualizan los campos del
inmueble que el LLM haya identificado (tipo, dirección, sector/zona/
ciudad, precio de venta esperado, matrícula —
`app.crm.protocol.PropertyListing`). Si el cliente cuenta datos del
inmueble antes de confirmar su identidad, esos datos no se guardan — el
bot puede tener que volver a preguntarlos una vez creado el deal. Ver
`app/flows/whatsapp_bot.py`.

La fuente de verdad de los datos del inmueble es el deal de Bitrix. El
historial de turnos y el `deal_id` por chat (`ConversationStore`) se
persisten en SQLite (`app/flows/whatsapp_bot_store.py`,
`WHATSAPP_BOT_DB_PATH`) y sobreviven a un restart/deploy — solo el dedup
de mensajes reintentados por Waha sigue en memoria del proceso (un TTL
corto, sin problema si se pierde). Así, si un cliente escribe, el bot le
pide datos y el cliente no vuelve a contestar hasta días después, al
retomar el bot sigue teniendo el historial y no repite preguntas ya
respondidas.

**Pausa por conversación / handoff a un asesor**: un asesor puede pausar
el bot para un deal puntual marcando el checkbox `fields.FIELD_BOT_ACTIVE`
en Bitrix — mientras esté desmarcado, `POST /webhook/waha-message` deja de
responder ese chat (`skipped: "bot_paused"`) y el asesor sigue la
conversación manualmente por WhatsApp normal. El bot también se autopausa
así cuando el LLM detecta que la persona pidió expresamente hablar con un
humano (`handoff_requested` en su salida JSON): manda el mensaje de
despedida, marca el checkbox y deja un comentario en el timeline del deal.
Para reactivar el bot en ese deal, el asesor vuelve a marcar el checkbox
manualmente — no hay reactivación automática.

Si el remitente ocultó su número (WhatsApp "username"/privacidad), Waha
manda el chat como `"<id>@lid"` en vez de `"<teléfono>@c.us"` — no es un
teléfono real. Mientras la identidad no esté confirmada, se intenta
resolver el teléfono real con `GET /api/{session}/lids/{lid}` de Waha
(`WahaClient.resolve_lid_to_phone`) — Waha mapea LID a número real cuando
ya lo aprendió (compartió un grupo o chat directo con ese número antes)
— solo para sugerírselo al LLM como candidato a confirmar con la persona
(ver siguiente párrafo); nunca se usa solo para crear nada en Bitrix. Al
confirmar la identidad en un chat `@lid`, se busca — antes de crear —
un contacto ya existente vinculado a ese identificador
(`fields.FIELD_USERNAME`, `UF_CRM_1786458989056`,
`app.waha.phone.lid_from_chat_id`), para no duplicar un contacto que un
asesor ya vinculó a mano.

**Candidatos de identidad sin confirmar**: para no interrogar de cero,
el system prompt del LLM incluye — mientras el deal no exista — el
nombre de perfil de WhatsApp del remitente y el teléfono detectado del
chat (directo si es `@c.us`, resuelto vía Waha si es `@lid`) como datos
"fáciles de conseguir pero sin confirmar"; el prompt le indica al LLM que
se los proponga a la persona ("¿usted es Fulano, cierto?") en vez de
pedirlos de cero. Ninguno de los dos se escribe en Bitrix hasta que la
persona los confirma explícitamente en el chat — ver "Limitaciones".

El cliente LLM (`app/llm/`) usa el SDK de OpenAI apuntado a `LLM_BASE_URL`
— funciona con OpenAI y con cualquier otro proveedor que hable el mismo
protocolo (Groq, Together, DeepSeek, OpenRouter, Azure OpenAI, un modelo
local con Ollama/vLLM, etc.), solo cambiando `LLM_BASE_URL`/`LLM_MODEL` en
`.env`, sin tocar código. El LLM responde en JSON estricto
(`{"reply": "...", "fields": {...}, "handoff_requested": ...}`, ver
`_OUTPUT_FORMAT_INSTRUCTIONS` en `app/flows/whatsapp_bot.py`) — si algún
proveedor no respeta el formato,
`_parse_llm_output` cae a modo seguro: manda el texto tal cual como
respuesta y no actualiza ningún campo, nunca rompe la conversación.

**Apagado por defecto** (`WHATSAPP_BOT_ENABLED=false`) — con el flag
apagado el endpoint sigue existiendo y respondiendo `200`, pero ignora todo
sin llamar al LLM ni al CRM. Para activarlo:

1. `LLM_API_KEY` en `.env` (obligatoria si se activa) y, si no es OpenAI,
   `LLM_BASE_URL`/`LLM_MODEL` del proveedor elegido.
2. `BITRIX_WEBHOOK_URL` configurado (ya necesario para el resto del hub) —
   el bot usa el mismo `CrmClient`.
3. `WHATSAPP_BOT_ENABLED=true`.
4. Opcional, para probar en desarrollo sin exponer el bot a todo el mundo:
   `WHATSAPP_BOT_ALLOWED_NUMBERS=573001112233,573004445566` (números
   separados por comas, código de país + número, sin `+`) — el bot ignora
   cualquier chat que no venga de esos números. Vacío (default) no
   restringe nada.
5. Que Waha esté mandando el webhook saliente a este hub —
   `WHATSAPP_HOOK_URL=http://api:8000/webhook/waha-message` y
   `WHATSAPP_HOOK_EVENTS=message` en `.env` (ver `.env.example`); tras
   cambiar estas variables hay que recrear la sesión de Waha
   (`docker compose restart waha`, y si la sesión ya estaba escaneada,
   confirmar en el dashboard de Waha que el webhook quedó configurado —
   `WAHA_DASHBOARD_ENABLED=true`).

Limitaciones conocidas, por ser experimental:

- **`V_Tipo Inmueble` no se guarda todavía** — es un picklist y
  `app/bitrix/fields.py::PROPERTY_TYPE_VALUE_BY_NAME` está vacío (no se
  puede adivinar el VALUE ID de cada opción). Correr
  `uv run python scripts/list_bitrix_picklist_values.py UF_CRM_1773860139420`
  y llenar el dict activa este campo; mientras tanto se ignora con un log
  de warning, el resto de campos sí se guardan normal.
- **`V_Canal de Origen` / `V_Canal de Contacto` no se tocan** — mismo
  motivo (picklist sin VALUE ID confirmado), fuera de esta primera versión.
- **`V_Precio Venta Esperado` se escribe como número plano** — falta
  confirmar si en Bitrix es un campo `money` (necesitaría formato
  `"123456|COP"`); si Bitrix lo rechaza, ajustar `update_property_listing`
  en `app/bitrix/client.py`.
- **Dedup de mensajes reintentados por Waha en memoria del proceso** — se
  pierde en cada restart del contenedor `api` (a lo sumo se reprocesa un
  mensaje reintentado, no rompe nada). El historial de conversación y el
  `deal_id` por chat sí persisten en SQLite, pero en un solo archivo
  (`WHATSAPP_BOT_DB_PATH`) — no pensado para correr con más de un worker
  simultáneo escribiendo el mismo archivo.
- **`fields.FIELD_BOT_ACTIVE` necesita crearse a mano en Bitrix** —
  checkbox en el deal; hasta que se reemplace el placeholder en
  `app/bitrix/fields.py` con el ID real, la pausa manual/automática no
  tiene dónde escribir (el bot sigue funcionando igual, solo sin este
  control).
- **Nombre de perfil del remitente (`sender_name`) es best-effort** — Waha
  no documenta un nombre de campo estable para esto (vive dentro de
  `_data`, que "puede variar según el engine" según sus propias docs).
  `app/waha/inbound.py::_extract_sender_name` prueba varias rutas
  conocidas (`notifyName`, `_data.pushName`, `_data.Info.PushName` para
  GOWS/whatsmeow); si ninguna aplica en tu engine real, el LLM
  simplemente no tiene candidato de nombre para sugerirle a la persona y
  se lo pide de cero — no bloquea nada (el contacto nunca se crea con
  este valor sin confirmar, ver arriba), ajustar `_SENDER_NAME_PATHS`
  cuando se confirme el campo real con un payload de producción.
- **Notas de voz se transcriben (whisper-asr-webservice, contenedor propio
  `whisper` en `docker-compose.yml`), otra media (imagen/video/documento) se
  ignora** (`app/waha/inbound.py`, `app/transcription/`). La detección usa
  `payload.media.mimetype` (`audio/...`) y la descarga usa
  `payload.media.url`, confirmado contra el schema `WAMessage`/`WAMedia` de
  la API de Waha. Si Waha no pudo descargar el audio (`media.error`, sin
  `url`) o la transcripción falla, el bot responde pidiendo que se escriba
  el mensaje en vez de quedarse en silencio. Audios de más de 15MB
  (`app/transcription/client.py::MAX_AUDIO_BYTES`) se rechazan sin llamar a
  whisper; tras un fallo de red/HTTP contra whisper, el cliente entra en
  cooldown de 30s (`COOLDOWN_SECONDS`, estado compartido a nivel de módulo)
  para que una ráfaga de audios no espere el timeout completo (60s) uno por
  uno mientras el servicio está caído. `process_whatsapp_bot` corre en un
  hilo aparte (`asyncio.to_thread` en `app/waha/router.py`) para no
  bloquear el event loop mientras transcribe.
- **Sin botones/listas interactivas** — solo texto plano (`WahaClient.send_text`).
- **Riesgo de baneo de Waha** — es WhatsApp Web no oficial. No usar este
  canal para mandar mensajes masivos no solicitados.
- **Crea contacto/deal automáticamente para cualquier número que escriba**
  — sin verificación humana; un número equivocado o un mensaje de spam
  también genera un deal en el pipeline 34.

```bash
curl -X POST "http://127.0.0.1:8000/webhook/waha-message" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "message",
    "session": "default",
    "payload": {
      "id": "test123",
      "from": "573001112233@c.us",
      "fromMe": false,
      "hasMedia": false,
      "body": "hola, quiero vender mi apartamento en el poblado"
    }
  }'
```

### Cambio de etapa de deal -> bienvenida + Autorización de Corretaje por WhatsApp

Apuntar acá la regla de automatización de Bitrix de la etapa que dispara el
envío. Le manda al contacto del deal, por WhatsApp, un mensaje de
bienvenida y — tras una pausa aleatoria de 3-6s simulando comportamiento
humano — el enlace al formulario público de Autorización de Corretaje
(`/formularios/autorizacion-de-corretaje?deal_id=<id>&token=<hmac>`). El
`token` es un HMAC del `deal_id` firmado con `FORM_LINK_SECRET` (sin
expiración): sin él, o con el `deal_id` de otro deal, el formulario no se
abre. Ver `app/flows/welcome_authorization.py` y `app/forms/link_token.py`.

```bash
curl -X POST "http://127.0.0.1:8000/webhook/deal-stage-broker-auth" \
  -d "data[FIELDS][ID]=42"
```

El estado de la firma se guarda en el campo `UF_CRM_1773864282733` del
deal (`Pendiente envío` / `Pendiente firma` / `Firmada`): se marca
`Pendiente firma` al enviar el link, y `Firmada` cuando el cliente
completa y firma el formulario — a partir de ahí el mismo link solo
muestra un aviso de "ya firmada", no deja reenviar el formulario. El PDF
firmado también se sube a la carpeta "Autorizaciones de corretaje"
(configurada en `BITRIX_DRIVE_FOLDER_ID`) dentro del Drive del grupo de
trabajo "Ventas" (workgroup id 184), con el nombre
`Autorizacion_{deal_id}_{direccion}_{fecha}.pdf`, y queda un comentario en
el timeline del deal confirmando la firma con el link al documento
(best-effort: si Bitrix falla —incluida la subida a Drive—, el cliente
igual descarga su PDF firmado — ver `app/forms/router.py`). El webhook de
Bitrix necesita el scope "disk" habilitado y su usuario debe ser miembro
del grupo "Ventas" para poder subir archivos ahí. Si la carpeta cambia
(se borra y se recrea), resuelve el nuevo ID con
`uv run python scripts/resolve_bitrix_drive_folder.py <texto>`.

## Corte de producción pendiente (MLS -> bitrix-hub)

Este repo tiene el código migrado y probado, pero la automatización real de
Bitrix (regla que dispara en creación/actualización de deal) sigue
apuntando a la URL de `MLS`. Falta, cuando se decida hacer el corte:

1. Desplegar `bitrix-hub` en un dominio/puerto propio.
2. Repuntar la regla de automatización de Bitrix a
   `https://<dominio-bitrix-hub>/webhook/deal-event`.
3. Confirmar en producción que el flujo corre igual (mismo campo de
   matrícula, mismo campo de duplicado).
4. Apagar el servicio de `MLS` (o dejarlo de respaldo un tiempo antes de
   retirarlo).

No hecho todavía — requiere acceso a la configuración de automatización de
Bitrix y coordinación de ventana de corte.
