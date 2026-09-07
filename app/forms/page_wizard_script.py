"""JS del wizard previo al formulario completo — separado de page_script.py por tamaño.

Contiene `__VERIFY_MATRICULA_PATH__`, reemplazado por `render_form_html()` en
`page.py` (mismo mecanismo de placeholders que `page_script.py`). Corre en su
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

  function showFullForm() {
    hide(stepLocation);
    hide(stepMatricula);
    show(fullFormCard);
  }

  function showBlocked(message, url) {
    hide(stepLocation);
    hide(stepMatricula);
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

  var locationInput = document.getElementById('field-location');
  var locationError = document.getElementById('error-location');
  var locationContinueButton = document.getElementById('wizard-location-continue');
  locationInput.addEventListener('input', function () {
    bhSaveState({ wizard: { location: locationInput.value } });
  });

  locationContinueButton.addEventListener('click', function () {
    var value = locationInput.value.trim();
    if (!value) {
      locationInput.classList.add('field__input--invalid');
      if (locationError) locationError.textContent = 'Cuéntanos la ubicación del inmueble para continuar.';
      locationInput.focus();
      return;
    }
    locationInput.classList.remove('field__input--invalid');
    if (locationError) locationError.textContent = '';

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

  // Matrícula/ID: dígitos, letras (código de oficina) y guion, en mayúscula
  // — mismo criterio que `field-registration_number` en page_script.py.
  var matriculaInput = document.getElementById('wizard-registration-number');
  var matriculaError = document.getElementById('error-wizard-registration-number');
  var matriculaContinueButton = document.getElementById('wizard-matricula-continue');
  matriculaInput.addEventListener('input', function () {
    matriculaInput.value = matriculaInput.value.toUpperCase().replace(/[^0-9A-Z-]/g, '');
    bhSaveState({ wizard: { matricula: matriculaInput.value } });
  });

  function setMatriculaError(message) {
    matriculaInput.classList.toggle('field__input--invalid', !!message);
    matriculaError.textContent = message || '';
  }

  matriculaContinueButton.addEventListener('click', function () {
    var value = matriculaInput.value.trim();
    if (!value) {
      setMatriculaError('Cuéntanos la matrícula o el ID del inmueble para continuar.');
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
      if (!resp.ok) throw new Error('No se pudo validar la matrícula. Intenta de nuevo en unos minutos.');
      return resp.json();
    }).then(function (body) {
      matriculaContinueButton.disabled = false;
      matriculaContinueButton.textContent = originalButtonText;
      if (!body) return;
      if (body.duplicate) {
        // Bloqueado: el paso guardado se queda en "matricula", nunca en
        // "done" — si la persona recarga la página, debe volver a intentar
        // en ese paso (o corregirlo), no aparecer directo en el formulario
        // completo como si ya hubiera pasado la validación.
        bhSaveState({ wizard: { step: 'matricula' } });
        showBlocked(body.message, body.url);
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

  // Restaura el paso del wizard guardado (recarga de página) — al final de
  // la IIFE porque necesita todas las funciones/variables ya declaradas.
  (function bhRestoreWizard() {
    var state = bhLoadState();
    var w = state.wizard || {};
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
