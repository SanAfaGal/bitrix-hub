"""Helpers de localStorage compartidos por el formulario y su wizard.

Progreso del formulario (wizard + campos ya diligenciados) persistido en
localStorage por deal_id, para no perderlo si la persona recarga la página.
Este módulo es la única fuente de esta lógica — `page_script.py`
(FORM_SCRIPT) y `page_wizard_script.py` (WIZARD_SCRIPT) insertan cada uno
`STORAGE_SCRIPT` dentro de su propia IIFE al armar el HTML final (son dos
`<script>` independientes, sin mecanismo de import entre sí en el
navegador), pero el texto fuente de estas tres funciones vive acá una sola
vez en vez de estar copiado a mano en los dos archivos.
"""
from __future__ import annotations

STORAGE_SCRIPT = """  function bhStorageKey() {
    var form = document.getElementById('authorization-form');
    var dealIdInput = form && form.elements.deal_id;
    return 'bh_authForm_v1_' + (dealIdInput && dealIdInput.value ? dealIdInput.value : 'anon');
  }
  function bhLoadState() {
    try { return JSON.parse(localStorage.getItem(bhStorageKey())) || {}; }
    catch (e) { return {}; }
  }
  function bhSaveState(patch) {
    try {
      var state = bhLoadState();
      Object.keys(patch).forEach(function (section) {
        state[section] = Object.assign({}, state[section], patch[section]);
      });
      state.v = 1;
      localStorage.setItem(bhStorageKey(), JSON.stringify(state));
    } catch (e) { /* navegación privada o cuota agotada: persistencia best-effort */ }
  }

"""
