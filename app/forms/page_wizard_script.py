"""JS del wizard previo al formulario completo — separado de page_script.py por tamaño.

Contiene `__VERIFY_MATRICULA_PATH__`, reemplazado por `render_form_html()` en
`page.py` (mismo mecanismo de placeholders que `page_script.py`). Corre en su
propia IIFE, después del `<script>` de `page_script.py` en el HTML final —
no depende de sus funciones internas; solo comparte elementos del DOM por id
(`field-location`, `field-registration_number`, `authorization-form`).
"""
from __future__ import annotations

WIZARD_SCRIPT = """<script>
(function () {
  var stepAuthorization = document.getElementById('wizard-step-authorization');
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

  function showBlocked(message) {
    hide(stepLocation);
    hide(stepMatricula);
    document.getElementById('wizard-blocked-message').textContent = message;
    show(stepBlocked);
  }

  var locationInput = document.getElementById('field-location');
  var locationError = document.getElementById('error-location');
  var locationContinueButton = document.getElementById('wizard-location-continue');

  // Cobertura por ubicación: placeholder (`app/forms/coverage.py`, listado
  // real todavía pendiente) que hoy siempre deja pasar — de ahí que este
  // paso lleve directo al formulario completo en vez de al paso de
  // matrícula. Es el único punto a cambiar del lado del cliente cuando el
  // chequeo real de cobertura exista (hoy resuelto sin llamada al backend,
  // ver app/forms/router.py).
  function isLocationCovered() {
    return true;
  }

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

    if (isLocationCovered()) {
      showFullForm();
    } else {
      hide(stepLocation);
      show(stepMatricula);
      matriculaInput.focus();
    }
  });

  // Matrícula/ID: dígitos, letras (código de oficina) y guion, en mayúscula
  // — mismo criterio que `field-registration_number` en page_script.py.
  var matriculaInput = document.getElementById('wizard-registration-number');
  var matriculaError = document.getElementById('error-wizard-registration-number');
  var matriculaContinueButton = document.getElementById('wizard-matricula-continue');
  matriculaInput.addEventListener('input', function () {
    matriculaInput.value = matriculaInput.value.toUpperCase().replace(/[^0-9A-Z-]/g, '');
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
        showBlocked(body.message);
        return;
      }
      // No se vuelve a pedir: el valor ya validado pasa directo al campo
      // real del formulario completo (sección "Datos del inmueble").
      var realRegistrationNumberInput = document.getElementById('field-registration_number');
      if (realRegistrationNumberInput) realRegistrationNumberInput.value = value;
      showFullForm();
    }).catch(function (err) {
      matriculaContinueButton.disabled = false;
      matriculaContinueButton.textContent = originalButtonText;
      setMatriculaError(err.message);
    });
  });
})();
</script>"""
