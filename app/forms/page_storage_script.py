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

STORAGE_SCRIPT = """  var BH_STORAGE_TTL_MS = 48 * 60 * 60 * 1000; // 48h: si no se envía en ese tiempo, se descarta.
  function bhStorageKey() {
    var form = document.getElementById('authorization-form');
    var dealIdInput = form && form.elements.deal_id;
    return 'bh_authForm_v1_' + (dealIdInput && dealIdInput.value ? dealIdInput.value : 'anon');
  }
  function bhLoadState() {
    try {
      var state = JSON.parse(localStorage.getItem(bhStorageKey())) || {};
      // Datos personales (cédula, correo, dirección) quedan en texto plano en
      // localStorage — si el formulario se abandonó, no deben quedar ahí
      // indefinidamente (ej. dispositivo compartido/público).
      if (state.savedAt && Date.now() - state.savedAt > BH_STORAGE_TTL_MS) {
        localStorage.removeItem(bhStorageKey());
        return {};
      }
      return state;
    } catch (e) { return {}; }
  }
  function bhSaveState(patch) {
    try {
      var state = bhLoadState();
      Object.keys(patch).forEach(function (section) {
        state[section] = Object.assign({}, state[section], patch[section]);
      });
      state.v = 1;
      state.savedAt = Date.now();
      localStorage.setItem(bhStorageKey(), JSON.stringify(state));
    } catch (e) { /* navegación privada o cuota agotada: persistencia best-effort */ }
  }

"""
