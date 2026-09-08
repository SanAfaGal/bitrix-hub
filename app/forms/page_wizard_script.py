"""JS del wizard previo al formulario completo — separado de page_script.py por tamaño.

Contiene `__VERIFY_MATRICULA_PATH__` y `__CONFIRM_MATRICULA_MATCH_PATH__`,
reemplazados por `render_form_html()` en `page.py` (mismo mecanismo de
placeholders que `page_script.py`). Corre en su
propia IIFE, después del `<script>` de `page_script.py` en el HTML final —
no depende de sus funciones internas; solo comparte elementos del DOM por id
(`field-location`, `field-registration_number`, `authorization-form`) y los
helpers de storage de `page_storage_script.py` (única fuente de esa lógica,
compartida en tiempo de compilación de la plantilla, no en tiempo de
ejecución — ver el docstring de ese módulo).
"""
from __future__ import annotations

from app.forms.page_storage_script import STORAGE_SCRIPT

WIZARD_SCRIPT = (
    """<script>
(function () {
"""
    + STORAGE_SCRIPT
    + """  var stepAuthorization = document.getElementById('wizard-step-authorization');
  var stepDeclined = document.getElementById('wizard-step-declined');
  var stepLocation = document.getElementById('wizard-step-location');
  var stepMatricula = document.getElementById('wizard-step-matricula');
  var stepConfirmMatch = document.getElementById('wizard-step-confirm-match');
  var stepBlocked = document.getElementById('wizard-step-blocked');
  var fullFormCard = document.getElementById('full-form-card');

  function hide(el) { el.classList.add('card--hidden'); }
  function show(el) { el.classList.remove('card--hidden'); }

  var dataConsentCheckbox = document.getElementById('wizard-data-consent');
  var dataConsentError = document.getElementById('error-wizard-data-consent');
  dataConsentCheckbox.addEventListener('change', function () {
    if (dataConsentCheckbox.checked) {
      dataConsentCheckbox.classList.remove('field__input--invalid');
      dataConsentError.textContent = '';
      dataConsentError.classList.remove('field__error--visible');
    }
    bhSaveState({ wizard: { consentAccepted: dataConsentCheckbox.checked } });
  });

  document.getElementById('wizard-authorize-yes').addEventListener('click', function () {
    if (!dataConsentCheckbox.checked) {
      dataConsentCheckbox.classList.add('field__input--invalid');
      dataConsentError.textContent = 'Debes autorizar el tratamiento de tus datos personales para continuar.';
      dataConsentError.classList.add('field__error--visible');
      dataConsentCheckbox.focus();
      return;
    }
    dataConsentCheckbox.classList.remove('field__input--invalid');
    dataConsentError.textContent = '';
    bhSaveState({ wizard: { consentAccepted: true, step: 'location' } });
    hide(stepAuthorization);
    show(stepLocation);
    locationInput.focus();
  });
  document.getElementById('wizard-authorize-no').addEventListener('click', function () {
    hide(stepAuthorization);
    show(stepDeclined);
  });

  // Botones "‹ Regresar": nunca perdiendo lo tecleado (bhSaveState ya guarda
  // cada input al vuelo, ver más abajo) — solo cambian qué paso se ve y, si
  // hace falta, qué paso queda guardado para que una recarga no vuelva a
  // mostrar el paso que se acaba de abandonar.
  document.getElementById('wizard-back-declined').addEventListener('click', function () {
    hide(stepDeclined);
    show(stepAuthorization);
  });
  document.getElementById('wizard-back-location').addEventListener('click', function () {
    bhSaveState({ wizard: { step: 'authorization' } });
    hide(stepLocation);
    show(stepAuthorization);
  });
  document.getElementById('wizard-back-matricula').addEventListener('click', function () {
    bhSaveState({ wizard: { step: 'location' } });
    hide(stepMatricula);
    show(stepLocation);
    locationInput.focus();
  });
  document.getElementById('wizard-back-blocked').addEventListener('click', function () {
    // El paso guardado ya queda en 'matricula' cuando se bloquea (ver
    // showBlocked más abajo, llamado desde el handler de verify-matricula)
    // — no hace falta volver a guardarlo acá.
    hide(stepBlocked);
    show(stepMatricula);
    matriculaInput.focus();
  });

  function showFullForm() {
    hide(stepLocation);
    hide(stepMatricula);
    hide(stepConfirmMatch);
    show(fullFormCard);
  }

  function showBlocked(message, url) {
    hide(stepLocation);
    hide(stepMatricula);
    hide(stepConfirmMatch);
    document.getElementById('wizard-blocked-message').textContent = message;
    var link = document.getElementById('wizard-blocked-link');
    if (url) {
      link.href = url;
      link.classList.remove('wizard-blocked-link--hidden');
    } else {
      link.classList.add('wizard-blocked-link--hidden');
    }
    show(stepBlocked);
  }

  // Antes de bloquear por duplicado, se le pregunta al cliente si el inmueble
  // encontrado es el suyo — folios de matrícula no son únicos entre oficinas
  // distintas, así que incluso una búsqueda exacta puede, en teoría, no ser el
  // inmueble correcto; se pregunta siempre, no solo cuando la búsqueda tuvo
  // que reintentarse sin código de oficina. `pendingMatch` guarda lo que hace
  // falta para bloquear si contesta que sí (mismo mensaje/url que ya calculó
  // el backend) o para avisar al CRM con el POST a confirm-matricula-match.
  var pendingMatch = null;
  function showConfirmMatch(value, message, url, exactMatch) {
    pendingMatch = { value: value, message: message, url: url };
    hide(stepLocation);
    hide(stepMatricula);
    document.getElementById('wizard-confirm-match-link').href = url;

    // Le muestra a la persona cómo se hizo la búsqueda que encontró esto —
    // si no fue exacta (código de oficina + folio), que sepa que el match
    // salió solo por el folio, para que tenga una pista de dónde puede
    // estar el error si resulta que no es su inmueble (código de oficina
    // mal escrito, o de plano otro inmueble con el mismo folio).
    var dashIndex = value.indexOf('-');
    var officeCode = dashIndex === -1 ? null : value.slice(0, dashIndex);
    var folio = dashIndex === -1 ? value : value.slice(dashIndex + 1);
    var searchNote = exactMatch
      ? 'Lo encontramos buscando con matrícula completa: código de oficina "' + officeCode + '" y folio "' + folio + '".'
      : (
        officeCode
          ? 'No encontramos nada buscando con el código de oficina "' + officeCode + '" — esto salió al '
            + 'buscar solo por el folio "' + folio + '", sin código de oficina. Si no es tu inmueble, revisa '
            + 'si el código de oficina que escribiste es el correcto.'
          : 'Lo encontramos buscando solo por el folio "' + folio + '" (no escribiste código de oficina).'
      );
    document.getElementById('wizard-confirm-match-search-note').textContent = searchNote;
    show(stepConfirmMatch);
  }

  // Copia el valor ya confirmado al campo de solo lectura del formulario
  // final y muestra el ✓ verde debajo — se llama tanto al pasar el paso en
  // vivo como al restaurar desde localStorage (bhRestoreWizard), para que el
  // cliente vea ahí lo que ya confirmó, en vez de que "desaparezca" al
  // ocultarse el paso del wizard.
  function confirmField(name, value) {
    var display = document.getElementById('field-' + name);
    if (display) {
      display.value = value;
      display.readOnly = true;
    }
    var confirmEl = document.getElementById('field-' + name + '-confirm');
    if (confirmEl) confirmEl.classList.remove('field__confirm--hidden');
    var correctBtn = document.getElementById('field-' + name + '-correct');
    if (correctBtn) correctBtn.classList.remove('field__correct-btn--hidden');
  }

  // Helper local para los errores del wizard (equivalente a
  // showFieldError/clearFieldError de page_script_submit.py, pero ese vive
  // en el otro <script> — módulo con su propia IIFE, no accesible desde acá,
  // ver el docstring de este archivo). Antes estos pasos solo ponían el
  // texto del error sin la clase `field__error--visible` que lo muestra
  // (ver .field__error en page_styles_fields.py, oculto por defecto) — el
  // mensaje quedaba escrito pero invisible, el cliente solo veía el borde
  // rojo del campo sin saber qué corregir.
  function setWizardFieldError(input, errorEl, message) {
    input.classList.toggle('field__input--invalid', !!message);
    if (errorEl) {
      errorEl.textContent = message || '';
      errorEl.classList.toggle('field__error--visible', !!message);
    }
  }

  var locationInput = document.getElementById('field-location');
  var locationError = document.getElementById('error-location');
  var locationContinueButton = document.getElementById('wizard-location-continue');
  locationInput.addEventListener('input', function () {
    bhSaveState({ wizard: { location: locationInput.value } });
    setWizardFieldError(locationInput, locationError, '');
  });

  locationContinueButton.addEventListener('click', function () {
    var value = locationInput.value.trim();
    if (!value) {
      setWizardFieldError(locationInput, locationError, 'Cuéntanos la ubicación del inmueble para continuar.');
      locationInput.focus();
      return;
    }
    setWizardFieldError(locationInput, locationError, '');

    // Se guarda el valor final tal cual quedó en el campo al confirmar (no el
    // de cada tecla, ver el listener 'input' de más arriba): así el
    // formulario final y una futura recarga muestran exactamente lo mismo
    // que la persona vio y seleccionó acá, incluido el formato en mayúscula
    // que aplica page_script.py y las sugerencias elegidas con el mouse (que
    // no disparan 'input').
    bhSaveState({ wizard: { location: value } });
    confirmField('location_display', value);

    // Si ya se había validado la matrícula (llegó acá corrigiendo la
    // ubicación con el botón "Corregir" del formulario final, no la primera
    // vez), no hace falta volver a consultarla en Xposure — es una
    // validación aparte que no cambió. Directo de vuelta al formulario.
    var registrationInput = document.getElementById('field-registration_number');
    if (registrationInput && registrationInput.readOnly && registrationInput.value) {
      bhSaveState({ wizard: { step: 'done' } });
      showFullForm();
      return;
    }

    // Matrícula/Xposure se pregunta siempre después de la ubicación — es una
    // validación distinta (¿el inmueble ya está publicado en el MLS?), no
    // depende de si la ubicación tiene cobertura (`app/forms/coverage.py`,
    // hoy un placeholder sin usar, reservado para un chequeo aparte a futuro).
    bhSaveState({ wizard: { step: 'matricula' } });
    hide(stepLocation);
    show(stepMatricula);
    matriculaInput.focus();
  });

  // Botones "Corregir" del formulario final: reabren el paso del wizard
  // correspondiente si la persona se equivocó, en vez de obligarla a pedir
  // un enlace nuevo al asesor (los pasos no tienen "atrás" una vez pasados).
  var locationCorrectButton = document.getElementById('field-location_display-correct');
  if (locationCorrectButton) {
    locationCorrectButton.addEventListener('click', function () {
      // Se baja el paso guardado ANTES de que la persona vuelva a tocar
      // nada: si recarga a mitad de la corrección, no debe restaurar el
      // formulario completo con un dato que quedó a medio corregir.
      bhSaveState({ wizard: { step: 'location' } });
      hide(fullFormCard);
      document.getElementById('field-location_display-confirm').classList.add('field__confirm--hidden');
      locationCorrectButton.classList.add('field__correct-btn--hidden');
      show(stepLocation);
      locationInput.focus();
      locationInput.select();
    });
  }
  var registrationCorrectButton = document.getElementById('field-registration_number-correct');
  if (registrationCorrectButton) {
    registrationCorrectButton.addEventListener('click', function () {
      bhSaveState({ wizard: { step: 'matricula' } });
      hide(fullFormCard);
      document.getElementById('field-registration_number-confirm').classList.add('field__confirm--hidden');
      registrationCorrectButton.classList.add('field__correct-btn--hidden');
      show(stepMatricula);
      matriculaInput.focus();
      matriculaInput.select();
    });
  }

  // Matrícula/ID: "código de oficina - folio", dígitos, letras (código de
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

  // Botón "Empezar de nuevo": solo visible si hay progreso guardado (se
  // decide en bhRestoreWizard, más abajo, que ya carga el estado). Borra
  // todo el localStorage del formulario y recarga — no intenta resetear el
  // DOM a mano, más simple y evita dejar algún campo a medias.
  var startOverButton = document.getElementById('start-over-btn');
  startOverButton.addEventListener('click', function () {
    if (!confirm('¿Seguro que quieres empezar de nuevo? Se perderá lo que llevas.')) return;
    bhClearState();
    location.reload();
  });

  // Restaura el paso del wizard guardado (recarga de página) — al final de
  // la IIFE porque necesita todas las funciones/variables ya declaradas.
  (function bhRestoreWizard() {
    var state = bhLoadState();
    var w = state.wizard || {};
    if (Object.keys(state).length > 0) startOverButton.classList.remove('start-over-btn--hidden');
    if (w.consentAccepted) dataConsentCheckbox.checked = true;
    if (w.location) locationInput.value = w.location;
    if (w.matricula) matriculaInput.value = w.matricula;
    if (w.step === 'done') {
      if (w.location) confirmField('location_display', w.location);
      if (w.matricula) confirmField('registration_number', w.matricula);
      hide(stepAuthorization);
      showFullForm();
    } else if (w.step === 'matricula') {
      if (w.location) confirmField('location_display', w.location);
      hide(stepAuthorization);
      show(stepMatricula);
    } else if (w.step === 'location') {
      hide(stepAuthorization);
      show(stepLocation);
    }
  })();
})();
</script>"""
)
