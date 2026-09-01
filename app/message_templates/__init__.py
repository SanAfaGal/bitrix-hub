"""Textos configurables que le llegan al cliente por WhatsApp (plantillas + system prompt del bot).

Guardados en MySQL vía SQLAlchemy, misma base que el resto del storage del
bot (`app/flows/whatsapp_bot_store.py`) — este paquete queda aparte porque
lo edita el equipo comercial desde `app/admin/`, no el propio bot. Ver
`app/message_templates/store.py` para las keys disponibles y sus defaults.
"""
