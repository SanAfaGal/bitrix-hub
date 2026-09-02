"""CRUD de plantillas de mensajes sobre MySQL, con fallback a los defaults hardcodeados acá.

Las keys son disparadores fijos en código (ver `DEFAULT_TEMPLATES`) — el
panel admin (`app/admin/`) solo edita el `content` de una key existente,
nunca crea una nueva. Lecturas nunca lanzan: si MySQL no está disponible
(o la fila no existe todavía), se cae al texto por defecto — el bot no debe
dejar de responder por un problema de la base de plantillas. Escrituras sí
propagan el error, para que el panel pueda avisarle al usuario que no se
guardó.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.message_templates import db
from app.message_templates.models import MessageTemplate

logger = logging.getLogger(__name__)

# Tras un fallo de conexión a MySQL, no se reintenta por este rato — evita
# que cada mensaje de una ráfaga del bot espere el connect_timeout completo
# mientras la base está caída. Mismo patrón que TranscriptionClient.
COOLDOWN_SECONDS = 30

_lock = threading.Lock()
_unavailable_until = 0.0


def _mark_unavailable() -> None:
    global _unavailable_until
    with _lock:
        _unavailable_until = time.monotonic() + COOLDOWN_SECONDS


def _is_in_cooldown() -> bool:
    with _lock:
        return time.monotonic() < _unavailable_until


def reset_circuit() -> None:
    """Solo para tests: limpia el estado de "MySQL caído" entre casos."""
    global _unavailable_until
    with _lock:
        _unavailable_until = 0.0


DEFAULT_TEMPLATES: dict[str, str] = {
    "whatsapp_welcome_unknown": (
        "¡Bienvenido a la Inmobiliaria Alberto Álvarez! 💙🧡 Si estás buscando una manera "
        "eficiente y segura de vender tu inmueble, has llegado al lugar indicado. Soy Andrea "
        "y estaré pendiente a tu respuesta, ¿Cuál es tu nombre?"
    ),
    "whatsapp_welcome_known": (
        "¡Hola, buenos días {{nombre}}!\n"
        "Mi nombre es Andrea, de Inmobiliaria Alberto Álvarez 💙🧡 Recibimos tu contacto y "
        "entendemos que deseas vender un inmueble con nosotros.\n"
        "A continuación, te explicaré cómo es todo el proceso y el acompañamiento que "
        "realizamos para la venta de tu inmueble. 🏡"
    ),
    "whatsapp_system_prompt": (
        "Usted es el asistente virtual de Alberto Álvarez, una inmobiliaria, y "
        "atiende por WhatsApp a personas interesadas en vender su apartamento. "
        "Trate siempre de usted, nunca de tú ni de vos — mantenga un tono "
        "formal, profesional y amable en todo momento.\n\n"
        "Su único objetivo en esta conversación es (1) confirmar el nombre "
        "completo y el teléfono de la persona y (2) conseguir que acepte "
        "continuar con el proceso y firme la Autorización de Corretaje — la "
        "explicación del proceso se la manda el sistema automáticamente, no "
        "usted. Bajo NINGUNA circunstancia pregunte, mencione o pida datos "
        "del inmueble (tipo, dirección, sector/zona/ciudad, precio de venta "
        "esperado, matrícula) — ni siquiera si la persona pregunta qué "
        "necesita saber, dice que no sabe qué contarle, o usted no tiene "
        "claro qué más decir: esos datos se recogen únicamente en el "
        "formulario de la Autorización de Corretaje que la persona firma "
        "después. Usted no cierra negocios ni reemplaza al asesor.\n\n"
        "No dé cifras de avalúo ni valorización bajo ninguna circunstancia — "
        "eso lo define un asesor tras conocer el inmueble. No dé asesoría "
        "legal, tributaria ni de trámites específicos; si le preguntan, "
        "indique que un asesor lo puede orientar en eso. No invente "
        "información sobre inmuebles, disponibilidad ni la empresa.\n\n"
        "Antes de seguir, confirme con la persona su nombre completo (nombre "
        "y apellido) y su teléfono — sin esto no se puede registrar su "
        "solicitud. Nunca invente ni complete de su cuenta un dato que la "
        "persona no le haya dado o confirmado — si falta el nombre, el "
        "teléfono, o ambos, pregunte específicamente por el dato que falta "
        "(uno a la vez si hace falta) en vez de asumirlo o de explicarle el "
        "proceso mientras la identidad siga incompleta. Si el sistema le muestra un nombre de perfil de WhatsApp "
        "o un teléfono detectado sin confirmar, no los dé por buenos: "
        "pregúntele si son correctos (ej. \"¿usted es Juan Pérez, cierto?\", "
        "\"¿y escribe desde su número personal?\") en vez de pedírselos de "
        "cero. Si la persona se sorprende o le pregunta cómo sabe su nombre "
        "o su número, explíquele con naturalidad que es el nombre de su "
        "perfil de WhatsApp (o el número desde el que escribe) — nunca sea "
        "evasivo ni ignore esa pregunta. Lo mismo si la persona misma le "
        "acaba de escribir su nombre y teléfono en su mensaje anterior: "
        "repítaselos y pregúntele si están correctos antes de darlos por "
        "buenos. Cuando la persona responda afirmativamente a esa pregunta "
        "(ej. \"sí\", \"correcto\", \"exacto\", \"así es\"), tome el nombre y "
        "el teléfono que usted mismo propuso en su mensaje anterior y "
        "repórtelos en \"client_full_name\" y \"client_phone\" de este turno "
        "— la persona no tiene por qué volver a escribirlos. En el turno en "
        "que usted registre nombre y teléfono confirmados por primera vez "
        "(\"client_full_name\" y \"client_phone\" con valor en ese turno), "
        "responda ÚNICAMENTE con un agradecimiento breve (ej. \"¡Perfecto, "
        "gracias!\") — NO explique el proceso, NO mencione la Autorización "
        "de Corretaje ni próximos pasos: el sistema le manda esa explicación "
        "automáticamente apenas termine este turno, y si usted también la "
        "menciona la persona recibe el mensaje duplicado.\n\n"
        "Conecte con un asesor humano de inmediato, sin insistir ni intentar "
        "resolverlo usted, en estos casos concretos: (1) la persona pide "
        "explícitamente hablar con una persona/asesor/humano; (2) pregunta "
        "por avalúo, valorización, temas legales, tributarios o trámites "
        "específicos (ya cubierto arriba); (3) la persona se muestra "
        "molesta o frustrada, o lo insulta o le habla con grosería (ej. "
        "\"usted es un tonto\", \"esto no sirve\", groserías) — un insulto "
        "directo siempre amerita conectar con un asesor, no responda con "
        "una disculpa genérica y siga la conversación como si nada. Fuera "
        "de esos casos, si no tiene certeza de un detalle menor o la "
        "persona pregunta algo fuera de lo anterior, no escale de una: "
        "respóndale con lo que sí sabe, o si de plano no aplica a lo que "
        "usted maneja, dígaselo con naturalidad y siga la conversación "
        "normalmente — no toda duda o pregunta fuera de tema amerita un "
        "asesor.\n\n"
        "Responda en español, en mensajes breves y claros, como una "
        "conversación real de WhatsApp — sin markdown ni emojis."
    ),
    "whatsapp_transcription_failed": "No pude escuchar tu audio, ¿me lo puedes escribir? 🙏",
    "whatsapp_unsupported_message": "Por ahora solo puedo leer texto o notas de voz, ¿me lo puedes escribir? 🙏",
    "whatsapp_process_explanation": (
        "¡Perfecto! Ahora te voy a explicar cómo funciona todo el proceso para vender tu "
        "inmueble con nosotros 🏡"
    ),
    "whatsapp_offer_explanation": "¿Te gustaría que te explique cómo funciona el proceso? 🎙️",
    "whatsapp_explanation_declined_ack": "¡Listo! Cualquier duda que tengas, aquí estoy.",
    "whatsapp_ask_acceptance": (
        "El siguiente paso es firmar la Autorización de Corretaje, que le permite a "
        "Inmobiliaria Alberto Álvarez administrar la venta de tu inmueble: publicarlo, "
        "mostrarlo a compradores interesados y gestionar todo el proceso hasta cerrar el "
        "negocio 🤝 ¿Deseas que te la envíe para que la firmes?"
    ),
    "bitrix_authorization_link_message": (
        "Para continuar, necesitamos que completes y firmes la Autorización de Corretaje aquí: {{link}}"
    ),
    "whatsapp_authorization_signed_message": (
        "¡Gracias! Hemos recibido tu Autorización de Corretaje firmada ✅ En breve uno de "
        "nuestros asesores se pondrá en contacto contigo para solicitarte la demás "
        "documentación y continuar con el proceso."
    ),
    "whatsapp_authorization_not_received_yet": (
        "Todavía no nos ha llegado tu Autorización de Corretaje firmada. Te comparto de nuevo "
        "el enlace para que la completes:"
    ),
}

# Metadatos para el panel admin (etiqueta amigable + variables disponibles). No
# afectan el envío — solo la UI de app/admin/.
TEMPLATE_LABELS: dict[str, str] = {
    "whatsapp_welcome_unknown": "Bienvenida — cliente nuevo",
    "whatsapp_welcome_known": "Bienvenida — cliente conocido",
    "whatsapp_system_prompt": "Comportamiento del bot",
    "whatsapp_transcription_failed": "No se pudo transcribir el audio",
    "whatsapp_unsupported_message": "Mensaje con contenido no soportado",
    "whatsapp_process_explanation": "Explicación del proceso (antes del audio)",
    "whatsapp_offer_explanation": "Oferta del audio explicativo",
    "whatsapp_explanation_declined_ack": "Confirmación cuando rechaza el audio",
    "whatsapp_ask_acceptance": "Pregunta de aceptación (después del audio)",
    "bitrix_authorization_link_message": "Link de firma",
    "whatsapp_authorization_signed_message": "Confirmación de firma recibida",
    "whatsapp_authorization_not_received_yet": "Aviso cuando el cliente dice haber firmado pero no ha llegado",
}

TEMPLATE_VARIABLES: dict[str, list[str]] = {
    "whatsapp_welcome_known": ["nombre"],
    "bitrix_authorization_link_message": ["link"],
}

# Valores de ejemplo para la vista previa del panel admin (nunca se envían,
# solo ilustran cómo se ve el mensaje con la variable ya reemplazada).
TEMPLATE_VARIABLE_SAMPLES: dict[str, dict[str, str]] = {
    "whatsapp_welcome_known": {"nombre": "Carlos Ramírez"},
    "bitrix_authorization_link_message": {"link": "https://hub.albertoalvarez.com/autorizacion/8841"},
}

# Quién/qué la dispara — a propósito NO repite lo que ya dice el título
# (eso está en TEMPLATE_WHEN_USED, debajo del título en el editor).
TEMPLATE_HINTS: dict[str, str] = {
    "whatsapp_welcome_unknown": "Automático · bot de WhatsApp",
    "whatsapp_welcome_known": "Automático · bot de WhatsApp",
    "whatsapp_transcription_failed": "Automático · bot de WhatsApp",
    "whatsapp_unsupported_message": "Automático · bot de WhatsApp",
    "whatsapp_process_explanation": "Automático · bot de WhatsApp",
    "whatsapp_offer_explanation": "Automático · bot de WhatsApp",
    "whatsapp_explanation_declined_ack": "Automático · bot de WhatsApp",
    "whatsapp_ask_acceptance": "Automático · bot de WhatsApp",
    "bitrix_authorization_link_message": "Manual · lo dispara un asesor en Bitrix",
    "whatsapp_authorization_signed_message": "Automático · al firmar el formulario público",
    "whatsapp_authorization_not_received_yet": "Automático · bot de WhatsApp",
}

TEMPLATE_WHEN_USED: dict[str, str] = {
    "whatsapp_welcome_unknown": (
        "Se envía apenas alguien escribe por primera vez y Bitrix no tiene ningún contacto "
        "registrado con ese teléfono."
    ),
    "whatsapp_welcome_known": (
        "Se envía cuando alguien escribe por primera vez y su teléfono ya coincide con un "
        "contacto que tiene nombre en Bitrix (por ejemplo, vino de un formulario o de un "
        "negocio creado antes)."
    ),
    "whatsapp_transcription_failed": (
        "Se dispara si el cliente manda una nota de voz y el sistema no logra transcribirla "
        "(audio dañado, muy largo o el servicio de transcripción falló)."
    ),
    "whatsapp_unsupported_message": (
        "Se dispara si el cliente manda algo que el bot no puede leer (imagen, video, "
        "documento, sticker, ubicación, contacto, etc.) — cualquier tipo de mensaje distinto "
        "de texto o nota de voz."
    ),
    "whatsapp_process_explanation": (
        "Se envía apenas se crea el negocio y el contacto en Bitrix (nombre y teléfono ya "
        "confirmados), justo antes de preguntar si quiere que se le explique el proceso."
    ),
    "whatsapp_offer_explanation": (
        "Se envía justo después de la explicación escrita del proceso (cliente nuevo) o de la "
        "bienvenida (cliente ya conocido en Bitrix), preguntando si quiere la nota de voz antes "
        "de mandarla — nunca se manda el audio sin que la persona confirme primero."
    ),
    "whatsapp_explanation_declined_ack": (
        "Se envía cuando la persona responde que no quiere la explicación del proceso — el bot "
        "no vuelve a ofrecerla ni avanza por su cuenta a pedir la firma, queda a la espera."
    ),
    "whatsapp_ask_acceptance": (
        "Se envía justo después de la nota de voz que explica el proceso, para preguntarle a "
        "la persona si quiere continuar antes de mandarle el link de la Autorización de "
        "Corretaje."
    ),
    "bitrix_authorization_link_message": (
        "Lo dispara un asesor desde Bitrix al cambiar la etapa del negocio, con el enlace "
        "único para firmar desde el celular — no pasa por el bot conversacional."
    ),
    "whatsapp_authorization_signed_message": (
        "Se envía apenas el cliente completa y firma el formulario público de Autorización de "
        "Corretaje, para confirmarle que la recibimos y que un asesor la continuará."
    ),
    "whatsapp_authorization_not_received_yet": (
        "Se envía cuando el cliente escribe por el chat que ya firmó la Autorización de "
        "Corretaje pero en Bitrix todavía no está marcada como firmada — antes de reenviarle "
        "el enlace de firma."
    ),
}

# Agrupación de las plantillas (mensajes reales) en el panel admin — el
# system prompt (CONFIG_KEY) vive en su propia vista, "Configuración del
# bot", no acá. Igual que las keys, el agrupamiento es fijo en código.
TEMPLATE_SECTIONS: list[dict[str, object]] = [
    {"name": "Primer contacto", "keys": ["whatsapp_welcome_unknown", "whatsapp_welcome_known"]},
    {
        "name": "Durante la conversación",
        "keys": ["whatsapp_transcription_failed", "whatsapp_unsupported_message"],
    },
    {
        "name": "Explicación del proceso",
        "keys": [
            "whatsapp_process_explanation",
            "whatsapp_offer_explanation",
            "whatsapp_explanation_declined_ack",
            "whatsapp_ask_acceptance",
        ],
    },
    {
        "name": "Autorización de corretaje",
        "keys": [
            "bitrix_authorization_link_message",
            "whatsapp_authorization_signed_message",
            "whatsapp_authorization_not_received_yet",
        ],
    },
]

CONFIG_KEY = "whatsapp_system_prompt"


def _open_session(session: Session | None) -> tuple[Session, bool]:
    if session is not None:
        return session, False
    return db.SessionLocal(), True


def get_template(key: str, session: Session | None = None) -> str:
    """Lee el texto de `key` desde MySQL; si falla o no existe todavía, retorna el default."""
    if session is None and _is_in_cooldown():
        return DEFAULT_TEMPLATES[key]

    active_session, owns_session = _open_session(session)
    try:
        row = active_session.get(MessageTemplate, key)
        if row is not None:
            return row.content
    except SQLAlchemyError:
        logger.exception("No se pudo leer la plantilla %s de MySQL, se usa el valor por defecto", key)
        if owns_session:
            _mark_unavailable()
    finally:
        if owns_session:
            active_session.close()
    return DEFAULT_TEMPLATES[key]


def render_template(key: str, session: Session | None = None, **variables: str) -> str:
    """`get_template(key)` con reemplazo simple de `{{variable}}` — sin motor de plantillas."""
    content = get_template(key, session=session)
    for name, value in variables.items():
        content = content.replace("{{" + name + "}}", value)
    return content


def set_template(key: str, content: str, updated_by: str | None, session: Session | None = None) -> None:
    """Guarda (crea o actualiza) el texto de `key`. Lanza si MySQL falla — el panel debe avisar al usuario."""
    if key not in DEFAULT_TEMPLATES:
        raise ValueError(f"Plantilla desconocida: {key!r}")

    active_session, owns_session = _open_session(session)
    try:
        row = active_session.get(MessageTemplate, key)
        now = datetime.now(timezone.utc)
        if row is None:
            active_session.add(MessageTemplate(key=key, content=content, updated_at=now, updated_by=updated_by))
        else:
            row.content = content
            row.updated_at = now
            row.updated_by = updated_by
        active_session.commit()
    finally:
        if owns_session:
            active_session.close()


def list_templates(session: Session | None = None) -> dict[str, str]:
    """`key -> content` para todas las keys conocidas (default si falta la fila en MySQL)."""
    if session is None and _is_in_cooldown():
        return dict(DEFAULT_TEMPLATES)

    active_session, owns_session = _open_session(session)
    try:
        rows = {row.key: row.content for row in active_session.query(MessageTemplate).all()}
    except SQLAlchemyError:
        logger.exception("No se pudo listar las plantillas de MySQL, se usan los valores por defecto")
        if owns_session:
            _mark_unavailable()
        rows = {}
    finally:
        if owns_session:
            active_session.close()
    return {key: rows.get(key, default) for key, default in DEFAULT_TEMPLATES.items()}


def seed_defaults(session: Session | None = None) -> None:
    """Inserta en MySQL las keys que todavía no tengan fila — idempotente, se llama al arrancar la app."""
    active_session, owns_session = _open_session(session)
    try:
        existing = {row[0] for row in active_session.query(MessageTemplate.key).all()}
        now = datetime.now(timezone.utc)
        for key, content in DEFAULT_TEMPLATES.items():
            if key not in existing:
                active_session.add(MessageTemplate(key=key, content=content, updated_at=now, updated_by=None))
        active_session.commit()
    finally:
        if owns_session:
            active_session.close()
