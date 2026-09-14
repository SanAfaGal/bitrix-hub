  function fieldErrorEl(el) {
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
