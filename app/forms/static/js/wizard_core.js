  var stepAuthorization = document.getElementById('wizard-step-authorization');
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

  // Si el deal ya trae ubicación + sector confirmados por el captador (ver
  // `_location_prefill_from_deal` en app/forms/router.py), el sector ya pasó
  // por cobertura al crear el lead y el consentimiento ya se explicó en
  // persona — ni ese paso ni el de ubicación se le vuelven a pedir al
  // cliente, `bhRestoreWizard` (al final de este archivo) salta directo a
  // matrícula apenas carga la página, este botón nunca llega a mostrarse.
  var locationPrefill = window.__BH_LOCATION_PREFILL__ || null;

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
    refreshServiceStatus();
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
    refreshServiceStatus();
    locationInput.focus();
  });
  document.getElementById('wizard-back-blocked').addEventListener('click', function () {
    // El paso guardado ya queda en 'matricula' o 'location' según el origen
    // del bloqueo (ver showBlocked/blockedReturnStep) — no hace falta volver
    // a guardarlo acá.
    hide(stepBlocked);
    refreshServiceStatus();
    if (blockedReturnStep === 'location') {
      show(stepLocation);
      locationInput.focus();
    } else {
      show(stepMatricula);
      matriculaInput.focus();
    }
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

  // A qué paso volver desde el bloqueo con "Regresar" — lo fija cada llamada
  // a showBlocked() justo antes de llamarla (ver el chequeo de cobertura y
  // "¿es tu inmueble?" más abajo), 'matricula' es el default porque era el
  // único origen posible antes de que existiera el bloqueo por cobertura.
  var blockedReturnStep = 'matricula';

  // Estado de los servicios externos (mobilia_dwh, Xposure) — solo
  // informativo para el puntico de cada paso, nunca bloquea nada (esa
  // decisión ya la toma el backend, ver is_location_covered/
  // check_registration_number_live, que fallan abiertos cuando no pueden
  // determinar algo). Se llama al cargar la página y de nuevo en cada
  // transición hacia el paso de ubicación o matrícula, para reflejar si el
  // servicio se cayó o se recuperó entre pasos, sin necesidad de sondeo continuo.
  function setStatusDot(dot, ok, label) {
    if (!dot) return;
    dot.classList.toggle('wizard-status-dot--ok', ok);
    dot.classList.toggle('wizard-status-dot--down', !ok);
    dot.title = ok
      ? 'Servicio de ' + label + ' disponible.'
      : 'Servicio de ' + label + ' no disponible en este momento — igual puedes continuar.';
  }
  function refreshServiceStatus() {
    fetch(window.BH_CONFIG.estadoServiciosPath)
      .then(function (response) { return response.json(); })
      .then(function (body) {
        setStatusDot(document.getElementById('wizard-status-location'), body.mobilia_dwh, 'ubicaciones');
        setStatusDot(document.getElementById('wizard-status-matricula'), body.xposure, 'matrícula (Xposure)');
      })
      .catch(function () { /* best-effort, no bloquea nada — el punto se queda en gris/pendiente */ });
  }
  refreshServiceStatus();

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
  // (ver .field__error en app/forms/static/css/fields.css, oculto por defecto) — el
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
  var locationSectorCodeInput = document.getElementById('field-location_sector_code');
  var locationContinueButton = document.getElementById('wizard-location-continue');
  locationInput.addEventListener('input', function () {
    bhSaveState({ wizard: { location: locationInput.value, sectorCode: null } });
    setWizardFieldError(locationInput, locationError, '');
  });

  locationContinueButton.addEventListener('click', function () {
    var value = locationInput.value.trim();
    if (!value) {
      setWizardFieldError(locationInput, locationError, 'Cuéntanos la ubicación del inmueble para continuar.');
      locationInput.focus();
      return;
    }
    // Sin esto, el botón "Continuar" del paso nunca verificaba que se
    // hubiera elegido una sugerencia real de la lista (solo lo hacía el
    // submit final, ver validateLocationSelection en page_script_inputs.py)
    // — ahora es obligatorio, porque sin sector_code no hay nada que
    // consultar en el paso siguiente.
    var sectorCode = locationSectorCodeInput ? locationSectorCodeInput.value : '';
    if (!sectorCode) {
      setWizardFieldError(locationInput, locationError, 'Selecciona una ubicación de la lista de sugerencias.');
      locationInput.focus();
      return;
    }
    setWizardFieldError(locationInput, locationError, '');

    locationContinueButton.disabled = true;
    var originalButtonText = locationContinueButton.textContent;
    locationContinueButton.textContent = 'Verificando...';

    var form = document.getElementById('authorization-form');
    var dealIdInput = form.elements.deal_id;
    var tokenInput = form.elements.token;

    fetch(window.BH_CONFIG.verifyCoberturaPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sector_code: sectorCode,
        deal_id: dealIdInput ? dealIdInput.value : null,
        token: tokenInput ? tokenInput.value : null
      })
    }).then(function (resp) {
      if (resp.status === 422) {
        setWizardFieldError(locationInput, locationError, 'Selecciona una ubicación de la lista de sugerencias.');
        return null;
      }
      if (!resp.ok) {
        return resp.json().catch(function () { return null; }).then(function (body) {
          throw new Error(
            (body && body.detail) ||
            'No pudimos verificar la cobertura en este momento por un problema de nuestro lado. Intenta de nuevo en unos minutos.'
          );
        });
      }
      return resp.json();
    }).then(function (body) {
      locationContinueButton.disabled = false;
      locationContinueButton.textContent = originalButtonText;
      if (!body) return;

      if (!body.covered) {
        blockedReturnStep = 'location';
        showBlocked(body.message, null);
        return;
      }

      // Se guarda el valor final tal cual quedó en el campo al confirmar (no
      // el de cada tecla, ver el listener 'input' de más arriba): así el
      // formulario final y una futura recarga muestran exactamente lo mismo
      // que la persona vio y seleccionó acá, incluido el formato en
      // mayúscula que aplica page_script.py y las sugerencias elegidas con
      // el mouse (que no disparan 'input').
      bhSaveState({ wizard: { location: value, sectorCode: sectorCode } });
      confirmField('location_display', value);

      // Si ya se había validado la matrícula (llegó acá corrigiendo la
      // ubicación con el botón "Corregir" del formulario final, no la
      // primera vez), no hace falta volver a consultarla en Xposure — es una
      // validación aparte que no cambió. Directo de vuelta al formulario.
      var registrationInput = document.getElementById('field-registration_number');
      if (registrationInput && registrationInput.readOnly && registrationInput.value) {
        bhSaveState({ wizard: { step: 'done' } });
        showFullForm();
        return;
      }

      // Matrícula/Xposure se pregunta siempre después de la ubicación — es
      // una validación distinta (¿el inmueble ya está publicado en el MLS?),
      // independiente de la cobertura por zona que ya se acaba de confirmar.
      bhSaveState({ wizard: { step: 'matricula' } });
      hide(stepLocation);
      show(stepMatricula);
      refreshServiceStatus();
      matriculaInput.focus();
    }).catch(function (err) {
      locationContinueButton.disabled = false;
      locationContinueButton.textContent = originalButtonText;
      setWizardFieldError(locationInput, locationError, err.message);
    });
  });

