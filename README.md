# bitrix-hub

Servicio único que recibe webhooks de Bitrix y dispara acciones en sistemas
externos: consulta de inmuebles en Xposure (migrado desde el repo `MLS`,
ver abajo) y envío de WhatsApp vía Waha. ERP Mobilia y otras integraciones
a futuro. Un deploy, un `.env`, modular por integración por dentro.

`MLS` (repo aparte, `../Ventas/MLS`) sigue siendo el servicio en producción
hasta que el webhook de Bitrix se repunte a este hub. Su lógica de Xposure
ya está migrada acá (`app/xposure/` + `app/flows/deal_duplicado.py`), pero
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
XPOSURE_BASE_URL=https://tu-dominio-xposure.com
XPOSURE_USERNAME=tu_usuario
XPOSURE_PASSWORD=tu_password
WAHA_BASE_URL=http://waha:3000
WAHA_API_KEY=your_api_key_here
WAHA_SESSION=default
WHATSAPP_DEFAULT_ENGINE=GOWS
TZ=America/Bogota
HUB_PUBLIC_BASE_URL=https://tu-dominio-bitrix-hub.com
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

Levanta `api` y `waha` juntos, en el mismo compose. `api` espera a que
`waha` pase su healthcheck antes de arrancar (`depends_on: condition:
service_healthy`). Sesiones y media de WhatsApp persisten en
`./.waha-data/` (gitignored).

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
    protocol.py      # CrmClient (Protocol) — contrato que implementa cada CRM soportado
    deps.py            # get_crm_client() — único punto que cambia si se swapea de CRM
    README.md            # Cómo agregar un CRM nuevo
  bitrix/
    client.py       # BitrixClient — implementa CrmClient (get_deal, get_contact, add_comment, pin_comment, update_deal, ...)
    settings.py      # BITRIX_WEBHOOK_URL
    deps.py           # get_bitrix_client() — construye el BitrixClient concreto
  xposure/
    client.py         # XposureClient — login + search_property (migrado de MLS)
    settings.py        # XPOSURE_BASE_URL, XPOSURE_USERNAME, XPOSURE_PASSWORD
    models.py           # PropertySearchResult, BulkRequest (Pydantic, con description/examples para /docs)
    deps.py              # get_xposure_client() — atrapa errores de login y los traduce a HTTPException(502)
    router.py             # GET /properties/{tax_roll}, POST /properties/bulk (tag "Xposure")
  waha/
    client.py         # WahaClient — send_text(chat_id, text, session=None)
    settings.py        # WAHA_BASE_URL, WAHA_API_KEY, WAHA_SESSION
    phone.py             # to_chat_id() — limpieza y formato del teléfono para WhatsApp (genérico, cualquier CRM)
    events.py             # Reglas de negocio Waha-solo (vacío por ahora)
    deps.py                # get_waha_client()
    router.py               # POST /webhook/waha-test (tag "Waha", scaffolding)
  flows/
    deal_duplicado.py    # CRM + Xposure: matrícula -> consulta -> comentario/campo (ex MLS/app/deal_event.py)
    router.py              # POST /webhook/deal-event (tag "Bitrix Webhooks")
    README.md               # Patrón para flujos que combinan >1 integración
  main.py                 # FastAPI(), openapi_tags, include_router(...), GET /health
tests/
  fakes.py               # FakeCrmClient — fake compartido de app.crm.protocol.CrmClient
  test_bitrix_client.py
  test_waha_client.py
  test_phone.py
  test_deal_duplicado.py
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
   `app/flows/<nombre>.py` (ver `app/flows/README.md`; `deal_duplicado.py`
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
   `tests/test_deal_duplicado.py`.

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
`app/flows/deal_duplicado.py`.

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

### Cambio de etapa de deal -> bienvenida + Autorización de Corretaje por WhatsApp

Apuntar acá la regla de automatización de Bitrix de la etapa que dispara el
envío. Le manda al contacto del deal, por WhatsApp, un mensaje de
bienvenida y — tras una pausa aleatoria de 3-6s simulando comportamiento
humano — el enlace al formulario público de Autorización de Corretaje
(`/formularios/autorizacion-de-corretaje?deal_id=<id>`). Ver
`app/flows/welcome_authorization.py`.

```bash
curl -X POST "http://127.0.0.1:8000/webhook/deal-stage-broker-auth" \
  -d "data[FIELDS][ID]=42"
```

Cuando el cliente completa y firma ese formulario, si llegó con `deal_id`
en la URL, queda un comentario en el timeline del deal en Bitrix
confirmando la firma (best-effort: si Bitrix falla, el cliente igual
descarga su PDF firmado — ver `app/forms/router.py`).

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
