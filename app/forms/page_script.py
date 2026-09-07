"""JS del formulario de Autorización de Corretaje — separado de page.py por tamaño.

`FORM_SCRIPT` se arma concatenando fragmentos (cada uno en su propio módulo,
también por el límite de 500 líneas): helpers de storage compartidos con el
wizard, formato/validación de campos, firma (modelo de fondo + canvas) y el
envío. Todos corren dentro de la misma IIFE — es un único
`<script type="module">` en el HTML final; la separación es solo de
archivos fuente en este repo, no de scope en el navegador (las funciones y
`var` de un fragmento son visibles en los que se concatenan después, igual
que si estuvieran escritos a mano en un solo archivo).

Contiene `__CLEAN_SIGNATURE_PATH__`, reemplazado por `render_form_html()` en
`page.py` (mismo mecanismo de placeholders que el resto de la plantilla).
"""
from __future__ import annotations

from app.forms.page_script_inputs import INPUT_FORMATTING_SCRIPT
from app.forms.page_script_signature_canvas import SIGNATURE_CANVAS_SCRIPT
from app.forms.page_script_signature_model import SIGNATURE_MODEL_SCRIPT
from app.forms.page_script_submit import SUBMIT_SCRIPT
from app.forms.page_storage_script import STORAGE_SCRIPT

FORM_SCRIPT = (
    """<script type="module">
import { env, AutoModel, AutoProcessor, RawImage } from 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3/+esm';

(function () {
"""
    + STORAGE_SCRIPT
    + INPUT_FORMATTING_SCRIPT
    + SIGNATURE_MODEL_SCRIPT
    + SIGNATURE_CANVAS_SCRIPT
    + SUBMIT_SCRIPT
    + """})();
</script>"""
)
