# Panel admin

Plantillas de WhatsApp, comportamiento del bot, prospectos y cobertura de
ventas — protegido con `Depends(require_admin)` (cuenta corporativa +
`ADMIN_EMAILS`, ver `app/auth/`).

## HTML/CSS/JS

Sigue el patrón de `app/interno/`: HTML suelto con placeholders en
`app/admin/templates/` vía `app/shared/html_templates.py::render_template`,
CSS/JS sueltos en `app/admin/static/` servidos por `StaticFiles`
(`app/main.py` monta `/static/admin`). Sin motor de templates ni framework
de frontend — mismo criterio en todo el repo.

`page.py` arma el shell compartido (topbar, `render_app_shell`) sobre
`templates/shell.html` + `static/admin.css` — lo reusan las cuatro vistas
(Plantillas, Configuración, Prospectos, Cobertura). Cada vista después arma
su propio `body` (funciones Python que devuelven `RawHTML`, igual que
`app/interno/router.py`) y engancha su CSS/JS propio vía los parámetros
`extra_head_html`/`extra_body_html` de `render_app_shell` — ver
`prospects_page.py`/`coverage_page.py` para el ejemplo.

Prospectos además usa AJAX (`static/prospects.js`) para cambiar de chat sin
recargar toda la página — ver el docstring de `prospects_page.py` y el
endpoint `GET /admin/prospects/{key}/detail` en `router.py`.
