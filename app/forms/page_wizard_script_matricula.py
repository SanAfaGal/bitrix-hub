"""Fragmento de WIZARD_SCRIPT (ver page_wizard_script.py) — separado por tamaño.

Corre dentro de la misma IIFE que el resto de los fragmentos de ese archivo,
después de la parte "core" (que declara `hide`/`show`/`stepMatricula`/
`stepConfirmMatch`/`stepBlocked`/`showBlocked`/`blockedReturnStep`/
`setWizardFieldError`/`confirmField`/`showConfirmMatch`/`bhSaveState`, todo
usado acá) y antes de los botones "Corregir"/`bhRestoreWizard` (que sí
necesitan `matriculaInput` ya declarado, ver el orden de concatenación en
`page_wizard_script.py`).

Contiene `__VERIFY_MATRICULA_PATH__` y `__CONFIRM_MATRICULA_MATCH_PATH__`,
reemplazados por `render_form_html()` en `page.py`.
"""
from __future__ import annotations

WIZARD_MATRICULA_SCRIPT = """  // Matrícula/ID: "código de oficina - folio", dígitos, letras (código de
  // oficina) y guion, en mayúscula — mismo formato que `_REGISTRATION_NUMBER_RE`
  // en app/forms/models.py: código de oficina de 3-4 caracteres, folio de
  // 5-8 dígitos. Se recorta en vivo a esos largos (no solo se valida al
  // continuar) para que la persona no pueda escribir de más y se entere
  // recién al final.
  function formatMatricula(value) {
    value = value.toUpperCase().replace(/[^0-9A-Z-]/g, '');
    var dashIndex = value.indexOf('-');
    if (dashIndex === -1) return value.slice(0, 4);
    var officeCode = value.slice(0, dashIndex).slice(0, 4);
    var folio = value.slice(dashIndex + 1).replace(/-/g, '').slice(0, 8);
    return officeCode + '-' + folio;
  }
  // Mismo formato que `_REGISTRATION_NUMBER_RE` en app/forms/models.py — se
  // valida en el cliente antes de llamar a Xposure para avisar de una vez
  // si el formato está mal, en vez de esperar la ida y vuelta al servidor
  // para enterarse (el backend igual vuelve a validar esto, ver
  // `validate_registration_number`; esto es solo para responder más rápido).
  var MATRICULA_FORMAT_RE = /^(?:\\d{3}[A-Z]?|\\d{2}[A-Z])-\\d{5,8}$|^\\d{4,10}$/;

  var matriculaInput = document.getElementById('wizard-registration-number');
  var matriculaError = document.getElementById('error-wizard-registration-number');
  var matriculaContinueButton = document.getElementById('wizard-matricula-continue');
  matriculaInput.addEventListener('input', function () {
    matriculaInput.value = formatMatricula(matriculaInput.value);
    bhSaveState({ wizard: { matricula: matriculaInput.value } });
    setMatriculaError('');
  });

  function setMatriculaError(message) {
    setWizardFieldError(matriculaInput, matriculaError, message);
  }

  matriculaContinueButton.addEventListener('click', function () {
    var value = matriculaInput.value.trim();
    if (!value) {
      setMatriculaError('Cuéntanos la matrícula o el ID del inmueble para continuar.');
      matriculaInput.focus();
      return;
    }
    if (!MATRICULA_FORMAT_RE.test(value)) {
      setMatriculaError('Formato inválido. Ej: 050-123456 (código de oficina, guion, número de folio).');
      matriculaInput.focus();
      return;
    }
    setMatriculaError('');
    matriculaContinueButton.disabled = true;
    var originalButtonText = matriculaContinueButton.textContent;
    matriculaContinueButton.textContent = 'Verificando...';

    var form = document.getElementById('authorization-form');
    var dealIdInput = form.elements.deal_id;
    var tokenInput = form.elements.token;

    fetch('__VERIFY_MATRICULA_PATH__', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        registration_number: value,
        deal_id: dealIdInput ? dealIdInput.value : null,
        token: tokenInput ? tokenInput.value : null
      })
    }).then(function (resp) {
      if (resp.status === 422) {
        setMatriculaError('Matrícula inmobiliaria inválida.');
        return null;
      }
      if (!resp.ok) {
        // No es un problema de formato (eso ya se descartó arriba, antes de
        // llamar a la API) — es un error del servidor o de la consulta a
        // Xposure, hay que decirlo así para que la persona no piense que
        // escribió mal la matrícula. `detail` es el mensaje de FastAPI
        // (ej. el 429 de rate_limit.py trae uno propio ya en español); si no
        // viene ninguno, se usa un mensaje genérico que deja claro que el
        // problema es nuestro, no de lo que escribió.
        return resp.json().catch(function () { return null; }).then(function (body) {
          throw new Error(
            (body && body.detail) ||
            'No pudimos verificar la matrícula en este momento por un problema de nuestro lado. Intenta de nuevo en unos minutos.'
          );
        });
      }
      return resp.json();
    }).then(function (body) {
      matriculaContinueButton.disabled = false;
      matriculaContinueButton.textContent = originalButtonText;
      if (!body) return;
      if (body.duplicate) {
        // El paso guardado se queda en "matricula", nunca en "done" — si la
        // persona recarga la página a mitad de la pregunta "¿es tu
        // inmueble?", debe volver a intentar la matrícula desde cero, no
        // aparecer directo en el formulario completo ni en la pregunta a
        // medias (ver showConfirmMatch/showBlocked, ninguno se restaura solo).
        bhSaveState({ wizard: { step: 'matricula' } });
        showConfirmMatch(value, body.message, body.url, body.exact_match);
        return;
      }
      // No se vuelve a pedir: el valor ya validado pasa directo al campo
      // real del formulario completo (sección "Datos del inmueble"), de solo
      // lectura de ahí en adelante — ya se confirmó contra Xposure, no tiene
      // sentido dejar que se edite sin volver a validar.
      confirmField('registration_number', value);
      bhSaveState({ wizard: { step: 'done', matricula: value } });
      showFullForm();
    }).catch(function (err) {
      matriculaContinueButton.disabled = false;
      matriculaContinueButton.textContent = originalButtonText;
      setMatriculaError(err.message);
    });
  });

  // Respuesta a "¿es este tu inmueble?" — el POST a confirm-matricula-match es
  // best-effort: si falla la sincronización con el CRM, igual se sigue el
  // flujo del cliente (bloquear o dejarlo corregir), que depende de lo que él
  // mismo contestó, no de si Bitrix se pudo actualizar.
  function sendMatchConfirmation(confirmed) {
    var form = document.getElementById('authorization-form');
    var dealIdInput = form.elements.deal_id;
    var tokenInput = form.elements.token;
    return fetch('__CONFIRM_MATRICULA_MATCH_PATH__', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        registration_number: pendingMatch.value,
        url: pendingMatch.url,
        confirmed: confirmed,
        deal_id: dealIdInput ? dealIdInput.value : null,
        token: tokenInput ? tokenInput.value : null
      })
    }).catch(function () { /* best-effort, ver comentario arriba */ });
  }

  document.getElementById('wizard-confirm-match-yes').addEventListener('click', function () {
    var match = pendingMatch;
    sendMatchConfirmation(true).then(function () {
      blockedReturnStep = 'matricula';
      showBlocked(match.message, match.url);
    });
  });
  document.getElementById('wizard-confirm-match-no').addEventListener('click', function () {
    sendMatchConfirmation(false).then(function () {
      hide(stepConfirmMatch);
      show(stepMatricula);
      setMatriculaError('Verifica que el código de oficina y el número de folio estén bien escritos, y vuelve a intentarlo.');
      matriculaInput.focus();
      matriculaInput.select();
    });
  });

"""
