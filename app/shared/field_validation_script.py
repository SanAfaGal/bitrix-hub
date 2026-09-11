"""JS genérico para marcar errores de campo y validar obligatorios.

Compartido por `app/forms/page_script_submit.py` (formulario público) y
`app/interno/page_script.py` (formulario interno) — cada uno lo concatena
dentro de su propia IIFE, después de declarar `form`
(`document.getElementById(...)` / `document.querySelector(...)`), y asume la
misma convención de marcado: cada campo obligatorio vive en un `.field` que
contiene el `.field__input` y, opcionalmente, un `.field__error` donde cae
el mensaje (ver `.field__error`/`.field__error--visible` en
`app/forms/page_styles_fields.py` y `app/interno/static/estilos.css`).
"""
from __future__ import annotations

FIELD_VALIDATION_SCRIPT = """  function fieldErrorEl(el) {
    var wrap = el.closest('.field');
    return wrap && wrap.querySelector('.field__error');
  }

  function fieldLabelText(el) {
    var wrap = el.closest('.field');
    var label = wrap && wrap.querySelector('.field__label');
    return label ? label.textContent.replace('*', '').trim() : 'Este dato';
  }

  function showFieldError(el, message) {
    el.classList.add('field__input--invalid');
    var errorEl = fieldErrorEl(el);
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.classList.add('field__error--visible');
    }
  }

  function clearFieldError(el) {
    el.classList.remove('field__input--invalid');
    var errorEl = fieldErrorEl(el);
    if (errorEl) {
      errorEl.textContent = '';
      errorEl.classList.remove('field__error--visible');
    }
  }

  // Un checkbox obligatorio (ej. "Acepto política de tratamiento de datos")
  // siempre tiene `value` (el que viaja si está marcado) — lo que importa es
  // `checked`, no el value, a diferencia de un input de texto.
  function isFieldEmpty(el) {
    if (el.type === 'checkbox') return !el.checked;
    return !el.value || !el.value.trim();
  }

  // Marca con `message` cada campo obligatorio vacío dentro de `form` (no
  // solo el primero) y devuelve el primero, para poder llevarle el foco.
  function markMissingRequiredFields(form, message) {
    var firstMissing = null;
    Array.prototype.forEach.call(form.querySelectorAll('[required]'), function (el) {
      if (isFieldEmpty(el)) {
        showFieldError(el, message);
        if (!firstMissing) firstMissing = el;
      } else {
        clearFieldError(el);
      }
    });
    return firstMissing;
  }
"""
