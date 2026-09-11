"""Páginas privadas para el staff (cuenta corporativa, sin ADMIN_EMAILS).

Crear un lead (contacto + deal en Bitrix, `app/flows/interno_nuevo_lead.py`)
y, opcionalmente, iniciar de inmediato la Autorización de Corretaje reusando
los datos ya capturados — ver `router.py`. HTML/CSS/JS sueltos en
`templates/`/`static/` (no HTML armado en Python, a diferencia de
`app/forms/`) — ver la discusión de trade-offs en el diseño de este paquete.
"""
