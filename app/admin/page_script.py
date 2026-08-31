"""JS del panel admin: preview en vivo, contador de caracteres, insertar variable y aviso de cambios sin guardar.

Vainilla, sin build step — mismo criterio que `app/forms/page_script.py`.
No hace red ni nada async: todo el estado vive en el propio DOM.
"""
from __future__ import annotations

EDITOR_SCRIPT = """<script>
(function () {
  var textarea = document.querySelector('[data-editor]');
  if (!textarea) return;

  var initial = textarea.value;
  var samples = {};
  try { samples = JSON.parse(textarea.getAttribute('data-var-samples') || '{}'); } catch (e) { samples = {}; }

  var charCount = document.querySelector('[data-char-count]');
  var previewText = document.querySelector('[data-preview-text]');
  var badges = document.querySelectorAll('[data-badge]');
  var form = textarea.closest('form');
  var submitting = false;

  function renderPreview(text) {
    var out = text;
    for (var name in samples) {
      if (Object.prototype.hasOwnProperty.call(samples, name)) {
        out = out.split('{{' + name + '}}').join(samples[name]);
      }
    }
    return out;
  }

  function update() {
    var value = textarea.value;
    if (charCount) charCount.textContent = value.length + ' caracteres';
    if (previewText) previewText.textContent = renderPreview(value);
    var dirty = value !== initial;
    for (var i = 0; i < badges.length; i++) {
      badges[i].classList.toggle('badge-unsaved--visible', dirty);
      badges[i].classList.toggle('sidebar__item-dot--visible', dirty);
      badges[i].classList.toggle('navpill__dot--visible', dirty);
    }
  }

  textarea.addEventListener('input', update);
  update();

  var chips = document.querySelectorAll('[data-insert-var]');
  for (var c = 0; c < chips.length; c++) {
    chips[c].addEventListener('click', function (e) {
      e.preventDefault();
      var token = this.getAttribute('data-insert-var');
      var start = textarea.selectionStart != null ? textarea.selectionStart : textarea.value.length;
      var end = textarea.selectionEnd != null ? textarea.selectionEnd : textarea.value.length;
      textarea.value = textarea.value.slice(0, start) + token + textarea.value.slice(end);
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = start + token.length;
      update();
    });
  }

  if (form) {
    form.addEventListener('submit', function () { submitting = true; });
  }

  window.addEventListener('beforeunload', function (e) {
    if (submitting || textarea.value === initial) return;
    e.preventDefault();
    e.returnValue = '';
  });
})();
</script>"""
