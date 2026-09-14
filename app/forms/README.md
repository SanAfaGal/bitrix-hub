# Formulario de Autorización de Corretaje

Wizard público (link de WhatsApp) que un cliente llena y firma desde el
celular — `app/forms/router.py` expone los endpoints, `app/forms/models.py`
valida el payload, `app/forms/filler.py` genera el PDF final.

## HTML/CSS/JS

Plantillas Jinja2 en `app/forms/jinja_templates/`, CSS/JS reales en
`app/forms/static/{css,js}/` — cero HTML/CSS/JS como string de Python.
`app/forms/render.py` arma el contexto (datos planos: campos, prefill,
config de rutas) y llama `.render()`; `app/forms/page.py` solo guarda los
datos (`_FIELDS`, secciones, rutas), sin una sola etiqueta HTML.

A diferencia de `app/admin/`/`app/interno/` (que sirven su CSS/JS por
`StaticFiles`, requests separados), el formulario público sigue siendo una
sola respuesta HTTP autocontenida — es un link que un cliente abre desde
WhatsApp en el celular, sin garantía de que assets externos carguen bien.
`read_static_text` (`app/shared/static_text.py`) lee cada `.css`/`.js` del
disco (cacheado por proceso) y `render.py` los inyecta inline en
`<style>`/`<script>` al momento de renderizar — el archivo en disco es real
y editable, pero nunca se sirve por una URL propia.

Los pocos valores que antes viajaban como placeholders de texto dentro del
JS (rutas de los endpoints en vivo del wizard) ahora van en un único
`window.BH_CONFIG = {...}` armado con `json.dumps` e inyectado como
`<script>` chiquito antes del resto — el JS de `static/js/` es JS real, sin
sustituciones de texto.

`_fields.html` son macros de Jinja (nunca `{% include %}`) que reciben los
dicts de campo armados por `app/forms/page.py::_shared_field`/`_FIELDS` —
Python solo arma datos, las macros son el único lugar donde ese dato se
convierte en HTML.
