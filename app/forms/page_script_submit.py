"""JS de validación, restauración de campos y envío del formulario completo.

Fragmento de FORM_SCRIPT (ver page_script.py) — separado por tamaño. Usa
`bhLoadState`/`bhSaveState`/`bhStorageKey` (page_storage_script.py),
`locationInput`/`locationSelected`/`validateLocationSelection`
(page_script_inputs.py) y `hasSignature`/`processingSignature`/`canvas`/
`trimSignature`/`statusText` (page_script_signature_canvas.py) — todos
fragmentos que se concatenan antes que este en page_script.py, dentro de la
misma IIFE.
"""
from __future__ import annotations

SUBMIT_SCRIPT = """  var form = document.getElementById('authorization-form');
  var status = document.getElementById('form-status');
  var submitButton = document.getElementById('submit-button');

  // Mensajes propios de Alberto Álvarez en vez de los globos genéricos del
  // navegador ("Please fill out this field") — el <form> lleva `novalidate`
  // y esta validación reemplaza por completo a la nativa. Los de campos
  // obligatorios van junto al campo (`.field__error`), no en un mensaje
  // general abajo del formulario — así la persona ve de una cuál dato falta.
  function showFormError(message) {
    status.className = 'form-status--error';
    status.textContent = message;
  }
  function clearFormError() {
    status.className = '';
    status.textContent = '';
  }

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

  // Marca con un mensaje propio cada campo obligatorio vacío (no solo el
  // primero) y devuelve el primero, para poder llevarle el foco.
  function markMissingRequiredFields() {
    var firstMissing = null;
    Array.prototype.forEach.call(form.querySelectorAll('[required]'), function (el) {
      if (!el.value || !el.value.trim()) {
        showFieldError(el, 'Dato obligatorio para tu Autorización de Corretaje.');
        if (!firstMissing) firstMissing = el;
      } else {
        clearFieldError(el);
      }
    });
    return firstMissing;
  }

  // El backend (Pydantic) devuelve 422 con `detail: [{loc: ["body", "campo"],
  // msg: "Value error, <mensaje>"}, ...]` — esto lo lleva al campo exacto que
  // falló (mismo `.field__error` que "obligatorio"), en vez de un mensaje
  // genérico abajo del formulario. Devuelve el primer campo marcado, o null
  // si ningún error de la respuesta correspondía a un campo visible (caso
  // raro: solo pasaría si alguien le pega a la API sin usar este formulario).
  function applyServerValidationErrors(detail) {
    var firstInvalid = null;
    (detail || []).forEach(function (item) {
      var fieldName = item.loc && item.loc[item.loc.length - 1];
      var el = fieldName && document.getElementById('field-' + fieldName);
      if (!el) return;
      var rawMessage = item.msg || '';
      var message = rawMessage.indexOf('Value error,') === 0
        ? rawMessage.replace(/^Value error,\s*/, '')
        : fieldLabelText(el) + ' inválido.';
      showFieldError(el, message);
      if (!firstInvalid) firstInvalid = el;
    });
    return firstInvalid;
  }

  // Limpia el error de un campo (obligatorio o no) apenas la persona vuelve
  // a tocarlo — cubre tanto "faltaba" como un formato inválido que haya
  // marcado `applyServerValidationErrors` (ej. matrícula, precio).
  function bhSaveField(el) {
    if (!el.name) return;
    var patch = { fields: {} };
    patch.fields[el.name] = el.value;
    bhSaveState(patch);
  }
  Array.prototype.forEach.call(form.querySelectorAll('.field__input'), function (el) {
    el.addEventListener('input', function () { clearFieldError(el); bhSaveField(el); });
    el.addEventListener('change', function () { clearFieldError(el); bhSaveField(el); });
  });

  // "Saldo actual de la deuda" solo aplica si hay crédito hipotecario o
  // leasing vigente — se mantiene oculto (no solo deshabilitado) mientras
  // ninguno de los dos esté en "Sí", y se limpia al ocultarse para no
  // enviar un saldo de una deuda que la persona ya dijo que no tiene.
  var mortgageSelect = document.getElementById('field-mortgage_loan');
  var leasingSelect = document.getElementById('field-leasing');
  var debtWrap = document.getElementById('field-wrap-outstanding_debt');
  var debtInput = document.getElementById('field-outstanding_debt');
  function refreshDebtFieldVisibility() {
    var show = mortgageSelect.value === 'si' || leasingSelect.value === 'si';
    debtWrap.classList.toggle('field--hidden', !show);
    if (!show) {
      debtInput.value = '';
      clearFieldError(debtInput);
    }
  }
  mortgageSelect.addEventListener('change', refreshDebtFieldVisibility);
  leasingSelect.addEventListener('change', refreshDebtFieldVisibility);
  refreshDebtFieldVisibility();

  // Restaura los campos guardados (recarga de página) — después de que el
  // resto de listeners/estado de arriba ya quedó armado.
  (function bhRestoreFields() {
    var state = bhLoadState();
    var savedFields = state.fields || {};
    Object.keys(savedFields).forEach(function (name) {
      // registration_number es de solo lectura, dueño del wizard (confirmado
      // contra Xposure) — page_wizard_script.py ya lo restaura desde
      // `state.wizard.matricula`; un valor viejo acá no debe pisarlo.
      if (name === 'registration_number') return;
      var el = form.elements[name];
      if (el && savedFields[name] != null) el.value = savedFields[name];
    });
    refreshDebtFieldVisibility();
    var w = state.wizard || {};
    if (locationInput && w.location) {
      // Ubicación ya validada en una sesión anterior — se confía en lo
      // guardado aunque este script corra antes de que el wizard restaure
      // el valor del campo (viven en <script> separados sin orden garantizado).
      locationSelected = true;
    }
  })();

  // Spinner + frases que van rotando mientras se espera al backend, para
  // que la espera no se sienta larga aunque tarde unos segundos. Devuelve
  // una función para pararla al terminar (éxito o error).
  function startStatusAnimation(messages) {
    var i = 0;
    status.className = '';
    status.innerHTML = '<span class="status-loading">'
      + '<span class="spinner"></span>'
      + '<span class="status-loading__text">' + messages[0] + '</span>'
      + '</span>';
    var textEl = status.querySelector('.status-loading__text');
    var timer = setInterval(function () {
      i = (i + 1) % messages.length;
      textEl.textContent = messages[i];
    }, 1800);
    return function stop() { clearInterval(timer); };
  }

  form.addEventListener('submit', function (evt) {
    evt.preventDefault();
    clearFormError();

    var missingField = markMissingRequiredFields();
    var invalidLocation = !missingField ? validateLocationSelection() : null;
    var firstInvalid = missingField || invalidLocation;
    if (firstInvalid) {
      firstInvalid.focus();
      return;
    }
    if (processingSignature) {
      statusText.textContent = 'Espera a que termine de procesar la firma antes de enviar.';
      statusText.classList.add('signature-status-text--error');
      return;
    }
    if (!hasSignature) {
      statusText.textContent = 'Falta tu firma: es necesaria para tu Autorización de Corretaje.';
      statusText.classList.add('signature-status-text--error');
      return;
    }
    var data = {};
    new FormData(form).forEach(function (value, key) { data[key] = value; });
    data.signer_id_number = data.id_number;
    data.signature_png = trimSignature(canvas).toDataURL('image/png');

    submitButton.disabled = true;
    var stopAnimation = startStatusAnimation([
      'Generando el documento...',
      'Armando el PDF...',
      'Colocando la firma en el documento...',
      'Verificando los datos...',
      'Ya casi...'
    ]);

    fetch(window.location.pathname, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(function (resp) {
      if (resp.status === 422) {
        return resp.json().then(function (body) {
          return Promise.reject({ validationDetail: (body && body.detail) || [] });
        });
      }
      if (!resp.ok) throw new Error('No se pudo generar el documento. Intenta de nuevo en unos minutos.');
      return resp.blob();
    }).then(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'Autorización de Corretaje - Firmada.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      stopAnimation();
      document.getElementById('form-flow').style.display = 'none';
      document.getElementById('success-view').classList.remove('success-view--hidden');
      try { localStorage.removeItem(bhStorageKey()); } catch (e) {}
    }).catch(function (err) {
      stopAnimation();
      submitButton.disabled = false;
      if (err && err.validationDetail) {
        var firstInvalid = applyServerValidationErrors(err.validationDetail);
        if (firstInvalid) {
          clearFormError();
          firstInvalid.focus();
        } else {
          showFormError('Alberto Álvarez: revisa tus datos, algo no tiene el formato correcto.');
        }
        return;
      }
      showFormError('Alberto Álvarez: ' + err.message);
    });
  });
"""
