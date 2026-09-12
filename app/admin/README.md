# Panel admin

Plantillas de WhatsApp, comportamiento del bot, prospectos y cobertura de
ventas — protegido con `Depends(require_admin)` (cuenta corporativa +
`ADMIN_EMAILS`, ver `app/auth/`).

## Estado actual del HTML (pendiente de migrar)

A diferencia de `app/interno/` (HTML/CSS/JS sueltos en `templates/`/`static/`,
sin motor de templates), este paquete arma el marcado como f-strings de
Python: `page.py` (shell + plantillas/config), `prospects_page.py`,
`coverage_page.py`, más el CSS también como string Python en `page_styles.py`
y `coverage_styles.py`. Es el patrón más viejo del repo acá y el más difícil
de leer/editar de los dos.

**Pendiente:** migrar estas cuatro vistas (Plantillas, Configuración,
Prospectos, Cobertura) + el shell compartido (topbar) al patrón de
`app/interno/` — HTML suelto con placeholders vía
`app/shared/html_templates.py::render_template`, CSS en un `.css` estático
servido por `StaticFiles`. Se decidió NO hacerlo de una sola vez: son las
vistas más complejas del repo (editor con preview en vivo y estado "sin
guardar", layout tipo WhatsApp Web para prospectos, tabla con filtros/selección
multi-fila en JS para cobertura), así que primero se migraría una sola vista
como piloto (candidata: Configuración del bot, la más simple) para validar el
patrón antes de tocar el resto.

Mientras tanto, seguir el estilo ya existente en `page.py` para cualquier
cambio nuevo en estas vistas (no mezclar los dos patrones dentro de la misma
vista).
