"""Textos configurables que le llegan al cliente por WhatsApp (plantillas + system prompt del bot).

Guardados en MySQL vía SQLAlchemy — el resto del storage del bot
(`app/flows/whatsapp_bot_store.py`) sigue en SQLite, esto es aparte porque
lo edita el equipo comercial desde `app/admin/`, no el propio bot. Ver
`app/message_templates/store.py` para las keys disponibles y sus defaults.
"""
