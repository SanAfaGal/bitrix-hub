"""Panel admin interno: edición de plantillas de WhatsApp y del comportamiento del bot.

Solo UI + login — la lógica de negocio (qué plantillas existen, sus
defaults) vive en `app/message_templates/`. Sigue el patrón de HTML en
Python de `app/forms/` (sin Jinja2/build step) y la guía de estilo de la
empresa.
"""
