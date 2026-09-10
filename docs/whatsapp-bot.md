# Bot conversacional de WhatsApp — diseño y porqués

Documento de referencia para el flujo `whatsapp_bot` (`app/flows/whatsapp_bot*.py` +
`app/waha/`). No repite lo que ya dicen los docstrings de cada módulo (línea a
línea) sino que arma el panorama completo: qué hace cada pieza, cómo se
conectan, y por qué quedaron así — casi todas las decisiones no obvias acá
vienen de un bug real visto en producción, no de preferencia estética.

Ver también: `README.md` raíz (sección "Bot conversacional de WhatsApp",
variables de entorno), `app/flows/README.md` (por qué este flujo vive en
`app/flows/` y no en `app/waha/`).

## Qué es

Bot conversacional que responde por WhatsApp usando un LLM, combinando tres
integraciones: Waha (WhatsApp), un LLM (cualquier proveedor compatible con
OpenAI, vía `app/llm/`) y el CRM (Bitrix). Experimental, **apagado por
defecto** (`WHATSAPP_BOT_ENABLED=false`).

## Archivos y su rol

| Archivo | Rol |
|---|---|
| `whatsapp_bot.py` | Orquestador — `process()`/`_process()`, el pipeline completo por mensaje entrante |
| `whatsapp_bot_models.py` | Modelos SQLAlchemy: `Conversation` (tabla `leads`), `ConversationMessage` (tabla `messages`) |
| `whatsapp_bot_store.py` | Funciones puras sobre una `Session` ya abierta — persistencia real |
| `whatsapp_bot_conversation_store.py` | `ConversationStore` — envuelve `whatsapp_bot_store.py`, agrega locks/dedup/rate-limit en memoria |
| `whatsapp_bot_db.py` | Engine/sesión SQLAlchemy del bot (comparte pool MySQL con `app.message_templates.db`) |
| `whatsapp_bot_llm.py` | Texto puro: arma el prompt, parsea la salida del LLM — no toca CRM/Waha/store |
| `whatsapp_bot_welcome.py` | Bienvenida de primer contacto (texto fijo, no generado por LLM) |
| `whatsapp_bot_explanation.py` | Explicación del proceso + pregunta de aceptación, antes de mandar el link de Autorización |
| `whatsapp_bot_new_chat_check.py` | Decide si un chat visto por primera vez ya tenía conversación real en Waha |
| `whatsapp_bot_history_seed.py` | Importa y analiza con IA el historial de Waha al activar un chat viejo a mano |
| `whatsapp_bot_assets.py` | Assets compartidos (nota de voz fija de la explicación), aislado para evitar ciclo de imports |

Todos estos módulos (salvo `whatsapp_bot_history_seed.py` y `whatsapp_bot_assets.py`)
se separaron de `whatsapp_bot.py` por el límite de 500 líneas del repo — ver
"Cómo agregar una integración nueva" / "Code style" en `CLAUDE.md`.
`whatsapp_bot_history_seed.py` se separó porque combina `ConversationStore` +
`WahaClient` + `LlmClient` a la vez (no encaja en el criterio texto-puro vs.
solo-`Session` ya usado); `whatsapp_bot_assets.py` para que `welcome.py` y
`explanation.py` puedan importarlo sin ciclo entre ellos dos.

Del lado de Waha: `app/waha/inbound.py` (parseo del webhook),
`app/waha/client.py` (HTTP a la API de Waha), `app/waha/router.py` (los
endpoints), `app/waha/phone.py` (conversión teléfono ↔ `chatId`).

## Flujo completo de un mensaje entrante

1. `POST /webhook/waha-message` (`app/waha/router.py`) — valida `?secret=`
   contra `WHATSAPP_WEBHOOK_SECRET` (sin esto, cualquiera que descubra la
   URL dispara LLM + creación de deals en Bitrix a nombre de un cliente
   inventado).
2. `parse_inbound_message()` descarta eco (`fromMe`), `status@broadcast`, y
   eventos sin los campos mínimos.
3. Chequeo del switch global `WHATSAPP_BOT_ENABLED` antes de construir
   ningún cliente.
4. `process_whatsapp_bot()` corre en `asyncio.to_thread` — es sincrónico y
   puede tardar varios segundos (transcripción de audio, pausas
   deliberadas de `send_text_sequence`); así no bloquea el event loop.
5. Dentro de `process()`: adquiere `store.chat_lock(chat_id)` (ver
   "Por qué un lock por chat" abajo) y llama a `_process()`:
   - Re-chequea el switch global.
   - Allowlist de dev (`WHATSAPP_BOT_ALLOWED_NUMBERS`).
   - Dedup por `message_id` (reintentos de Waha).
   - **Chat nuevo**: si es la primera vez que se ve este `chat_id`,
     `is_chat_new_in_waha()` decide el `bot_enabled` inicial (ver sección
     dedicada).
   - **Gate por chat**: si `bot_enabled=False`, guarda el mensaje tal cual
     y corta ahí — silencio total (ver "Por qué `bot_enabled` por chat").
   - Bienvenida de primer contacto (`maybe_send_first_contact_welcome`,
     texto fijo).
   - Fallback si es media no soportada.
   - Resuelve texto (transcribe audio si aplica).
   - Rate limit (guarda el mensaje para el próximo turno, no lo descarta).
   - Resuelve `deal_id` cacheado (o revalida que el deal siga existiendo en
     el CRM).
   - Si no hay deal, intenta crearlo desde identidad ya confirmada.
   - Si está esperando aceptación de la explicación, intenta resolverla
     antes de llamar al LLM.
   - Arma el prompt (identidad confirmada + candidatos + instrucciones de
     salida JSON) y llama al LLM.
   - Parsea la salida (`_parse_llm_output` — tolerante, nunca rompe la
     conversación por un JSON mal formado).
   - Manda la respuesta por Waha; si tiene éxito: guarda ambos turnos,
     aplica identidad confirmada, actualiza datos del inmueble en el CRM,
     maneja `handoff_requested`, manda la explicación si el deal se acaba
     de crear, maneja pedidos tardíos de explicación.

## Por qué `bot_enabled` es opt-in por chat (no solo el switch global)

Cada chat tiene su propia activación, además del interruptor global.
**Arranca en `False` para todo chat, nuevo o viejo.** Mientras esté apagado:
no hay bienvenida, no se transcribe audio, no se llama al LLM — silencio
total, para que un asesor pueda seguir atendiendo el chat a mano por
WhatsApp Web — pero el mensaje entrante SÍ se guarda tal cual llega, así el
chat aparece en `/admin/prospects` para que un admin lo revise y active.

**Por qué:** evitar que el bot se meta en conversaciones que un asesor ya
está llevando a mano. Bug real visto antes de este diseño: chats de
asesores existentes terminaban secuestrados por respuestas del bot.

Dos caminos a `True`:
- Manual: admin hace clic en "Activar" en `/admin/prospects`
  (`POST {PROSPECTS_PATH}/{chat_id}/bot/activate`).
- Automático: la primera vez que se ve un `chat_id` nuevo, si Waha no
  muestra conversación real previa (`is_chat_new_in_waha`), se activa solo
  y este mismo mensaje ya se responde sin intervención de admin.

## Cómo se decide si un chat "nuevo" ya tenía conversación real

`whatsapp_bot_new_chat_check.py::is_chat_new_in_waha()`. Se llama una sola
vez, justo al crear el lead por primera vez.

**Regla:** hace falta un mensaje previo de **cada lado** (`fromMe=True` Y
`fromMe=False`) para considerar que ya hay "alguien atendiendo". Un lead
que escribió y nunca le contestó nadie (se cayó, ningún asesor lo tocó) SÍ
se auto-activa — ahí no hay nada humano que el bot interrumpa.

**Por qué el límite de lectura es 10 y no 2:** antes del mensaje real,
WhatsApp manda un evento `e2e_notification`/`encrypt` (placeholder de
intercambio de claves) que Waha guarda como mensaje del chat, con `id`
propio y `body` vacío. Se descarta exigiendo `body` no vacío (no solo
comparando `id`) — si no, ese placeholder podría contarse como "mensaje
real de un lado" y disparar falsamente el criterio de "ambos lados
escribieron" con un solo mensaje genuino en la conversación.

**Fail-closed:** si la consulta a Waha falla (`None`), se trata como si
hubiera conversación previa (`bot_enabled` queda apagado) — más seguro no
interrumpir una conversación existente que arriesgar una auto-activación
sin poder verificarlo.

## Importar historial al activar un chat viejo a mano

`whatsapp_bot_history_seed.py::seed_history_from_waha()`, llamado desde la
ruta de admin, **siempre antes** de `set_bot_enabled(chat_id, True)`
(nunca al revés — la función no toca `bot_enabled`, eso lo decide un nivel
más arriba).

**Por qué importar en vez de dejar el chat "tal cual":** esto solo corre
cuando un admin decide prender el bot para un chat que un asesor ya venía
atendiendo a mano. Si el bot arranca sin ese contexto, vuelve a pedir
nombre/teléfono que el cliente ya dio, repite la explicación del proceso ya
mandada, y queda evidente para el cliente que "no se acuerda" de la
conversación. La importación trae el historial real desde Waha, lo analiza
con el LLM (`analyze_prior_history`) y precarga: identidad confirmada
(nombre+teléfono), si la explicación ya se dio (`explanation_sent`), y los
turnos mismos (reemplazan, no duplican, lo que ya estaba guardado local del
período apagado — ver `store.clear_messages`).

Chats que **nunca** se activan simplemente nunca pasan por acá — "viejo, no
tocar" nunca dispara este import.

**Por qué existe `history_seeded` como columna dedicada** (y no se infiere
de si `messages` tiene filas): mientras `bot_enabled=False`, `_process()`
ya guarda cada mensaje entrante localmente para que el chat aparezca en
`/admin/prospects`. Para cuando un admin activa el chat, casi siempre YA
hay historial local — con el criterio viejo ("hay historial local ⇒ ya se
importó") esta función nunca llegaba a pegarle a Waha ni al LLM, y el
contexto previo real nunca se importaba (hallazgo de una revisión anterior).
Si Waha no devuelve nada (chat realmente nuevo o falla la llamada), igual
se marca `history_seeded=True` — así una reactivación futura no reintenta
por siempre.

## Responder de una vez el mensaje pendiente al activar

Antes: al activar un chat (`post_activate_bot`), si el cliente tenía el
último mensaje sin contestar (llegó mientras el bot estaba apagado, o
durante el import de historial), quedaba sin respuesta hasta que el
cliente escribía de nuevo — el admin veía el chat "activado" pero en
silencio.

Ahora, `whatsapp_bot.py::reply_after_activation()` se llama justo después
de `set_bot_enabled(chat_id, True)`, en un `try/except` aparte del de
`seed_history_from_waha` (uno fallando no debe bloquear al otro). Solo
responde si el último turno guardado es del cliente (`role="user"`); si el
último turno ya es del `assistant`, no hay nada pendiente y no hace nada.

Implementación: se extrajo de `_process()` el tramo "resolver deal, armar
prompt, llamar LLM, mandar respuesta" a una función interna reusable
(`_generate_and_send_reply`), parametrizada con `history_override` (para no
repetirle al LLM el mensaje pendiente dos veces: una como parte del
historial, otra como "mensaje actual") y `persist_user_turn=False` (el
mensaje ya está guardado en `messages` desde que llegó con el bot apagado —
no se duplica). `_process()` sigue usando la misma función con sus
defaults normales.

`reply_after_activation` chequea `store.get_bot_enabled(chat_id)` (además
del switch global `config.enabled`) antes de responder, y descarta un
turno pendiente vacío (nota de voz recibida mientras el chat estaba
apagado — no se transcribe en ese estado, queda como `content=""`) — sin
esto, el catch-up de rate limit (ver abajo, que también llama a esta
misma función) podía mandar una respuesta a un chat que un admin acababa
de desactivar, o generar una respuesta del LLM a partir de texto en
blanco.

## El mensaje atrapado por el rate limit ya no se queda sin respuesta

Bug real visto en logs de producción: dentro del cooldown de 5s
(`RATE_LIMIT_COOLDOWN_SECONDS`), un mensaje se guarda pero no se contesta
(ver arriba, "otras decisiones no obvias"). Antes, ese turno solo se
"recogía" cuando el cliente escribía un mensaje nuevo — si no volvía a
escribir, quedaba sin respuesta para siempre.

Ahora, al guardar el mensaje atrapado, `_process()` llama a
`_schedule_rate_limit_catchup()`, que programa (`threading.Timer`, thread
daemon, no bloquea la respuesta HTTP del webhook) un reintento pasado el
cooldown (`RATE_LIMIT_COOLDOWN_SECONDS + 1`s de margen). El callback reusa
`reply_after_activation()` tal cual — esa función ya es exactamente "si el
último turno guardado es del cliente, respondelo; si no, no hagas nada",
sin importar si la razón de que quedara sin responder fue `bot_enabled=False`
o el rate limit. Si para cuando dispara el timer ya se respondió por otra
vía (un mensaje posterior salió del cooldown con normalidad, o alguien
contestó a mano), el último turno ya es `assistant` y el catch-up no hace
nada — así que una ráfaga de varios mensajes seguidos, cada uno programando
su propio timer, como mucho termina mandando una sola respuesta.

## Los cuatro flags que parecen redundantes pero no lo son

- **`explanation_sent`** — ¿ya se mandó el texto+voz+pregunta de
  aceptación? Local, gatilla la rama "esperando aceptación" del prompt.
- **`authorization_link_sent`** — ¿ya se mandó el link REAL de
  Autorización de Corretaje? Deliberadamente independiente del campo de
  Bitrix: ese picklist trae un default no-nulo (`"pendiente_envio"`) desde
  que se crea el deal, así que "no es `None`" no significa "ya se mandó"
  (bug real: el gate nunca se abría, el bot prometía el link sin mandarlo
  nunca). Bitrix (`"pendiente_firma"`/`"firmada"`) se usa solo como
  respaldo si el tracking local se pierde (ej. reset de la base).
- **`authorization_mentioned`** — NO es columna persistida. Es resultado
  transitorio de analizar el historial importado: "¿se habló del tema en
  la conversación previa?" Se usa solo para el resumen que ve el admin al
  activar un chat. Explícitamente NO se mapea a `authorization_link_sent`
  — un asesor mencionando la Autorización no es lo mismo que haberla
  mandado; setearlo acá bloquearía para siempre que el bot mande el link
  real.
- **`confirmed_identity` (name/phone)** — se escriben atómicamente juntos,
  nunca uno solo, solo cuando el LLM confirma ambos en el mismo turno
  (`_apply_confirmed_identity`). Distinto de los "candidatos" (nombre de
  perfil de WhatsApp, número del chat) que se muestran al LLM como sugerencia
  pero nunca se dan por buenos sin confirmación explícita de la persona.

Conflacionar cualquier par de estos cuatro causó bugs reales en producción
(explicación repetida, link que nunca se manda, re-pedir identidad ya
conocida) — por eso quedaron separados.

## Por qué un lock por chat (`chat_lock`)

`threading.Lock` por `chat_id`, en memoria del proceso — **no distribuido**,
asume un único worker de `uvicorn`. Serializa `process()` para un mismo
chat: sin esto, dos mensajes casi simultáneos del mismo chat (ej. WhatsApp
entrega uno por teléfono y otro por `@lid` casi a la vez) corren en threads
distintos, ambos ven `deal_id is None` antes de que cualquiera termine de
crearlo, y cada uno crea su propio deal duplicado en Bitrix (visto en
producción: dos deals para el mismo contacto, 400ms aparte).

Los locks nunca se purgan — borrar uno mientras otro thread ya lo obtuvo
(antes de `with lock:`) recrearía la misma condición de carrera. Costo
acotado: un lock por cada chat distinto que haya escrito alguna vez, no por
mensaje. **Si el hub llega a correr con más de un worker/réplica, este
lock deja de servir** y hay que migrar a algo compartido (ej.
`SELECT ... FOR UPDATE` en MySQL).

## Otras decisiones no obvias

- **Pausa manual (asesor) y autopausa (handoff, firma de Autorización)
  comparten el mismo `bot_enabled` de chat** — no hay un gate aparte a
  nivel deal. Antes existía un checkbox de Bitrix (`FIELD_BOT_ACTIVE`)
  independiente del `bot_enabled` local; se eliminó porque duplicaba el
  mismo control en dos lugares distintos sin necesidad.
- **Explicación del proceso se manda sin preguntar antes** ("¿te gustaría
  que te explique?" se sacó — agregaba fricción y un estado
  (`explanation_offered`) que se prestaba a confusión si la respuesta no
  caía limpio en el regex de afirmación/negación).
- **Rate limit no descarta el mensaje** — lo guarda para el próximo turno,
  porque alguien mandando varias burbujas seguidas es uso normal de
  WhatsApp.
- **Bienvenida de primer contacto usa `has_assistant_turn`, no "historial
  no vacío"** — el caso típico de go-live (cliente escribe con el bot
  apagado, se guarda su mensaje, admin activa después) hacía que la
  bienvenida nunca se mandara bajo el criterio viejo.
- **Cliente ya conocido en Bitrix**: identidad y deal se resuelven ahí
  mismo al primer contacto, sin esperar a que el LLM los re-confirme en un
  turno futuro — sin esto, el bot saludaba a alguien por su nombre y dos
  turnos después le volvía a preguntar cuál era.
- **`@lid` vs. `@c.us`**: si WhatsApp oculta el número del remitente, el
  chat llega como `@lid` (id interno estable pero no es teléfono). Se
  intenta resolver a teléfono real vía `resolve_lid_to_phone`; si no se
  puede, se sigue con `username`/`phone=None`.
- **`messages` guarda todo el historial para siempre** (auditoría, panel
  admin); el recorte de cuántos turnos recientes van al LLM
  (`WHATSAPP_BOT_MAX_HISTORY_TURNS`) pasa al leer, no al escribir.

## Variables de entorno relevantes

Ver README raíz para la lista completa; las específicas de este flujo:

- `WHATSAPP_BOT_ENABLED` — switch global, default apagado.
- `WHATSAPP_BOT_MAX_HISTORY_TURNS` (default 6) — turnos recientes que ve el LLM.
- `WHATSAPP_BOT_ALLOWED_NUMBERS` — allowlist de dev, vacío = sin restricción.
- `WHATSAPP_BOT_HISTORY_ANALYSIS_LIMIT` (default 40) — mensajes de Waha a analizar al importar historial.
- `WHATSAPP_WEBHOOK_SECRET` — secreto compartido para `/webhook/waha-message` y `/webhook/waha-test`.
- `HUB_PUBLIC_BASE_URL` / `FORM_LINK_SECRET` — para construir el link de Autorización.

El system prompt del LLM **no** es variable de entorno — se edita desde el
panel admin (`app.message_templates`, clave `whatsapp_system_prompt`).
