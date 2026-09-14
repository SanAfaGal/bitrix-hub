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
    // Se restaura junto con `location` (no solo en el paso 'location'):
    // sin esto, un cliente que recarga después de pasar el chequeo de
    // cobertura y luego usa "Corregir" se encontraría el sector_code vacío
    // aunque la ubicación ya esté confirmada.
    if (w.sectorCode && locationSectorCodeInput) locationSectorCodeInput.value = w.sectorCode;
    if (w.matricula) matriculaInput.value = w.matricula;
    if (!w.step && locationPrefill) {
      // Primer visita con un deal que ya trae ubicación confirmada por el
      // captador (ver más arriba) — ni consentimiento ni ubicación se le
      // vuelven a pedir, arranca directo en matrícula. Se guarda igual que
      // si hubiera pasado por los pasos a mano, para que una recarga
      // restaure este mismo punto (rama `w.step === 'matricula'` de abajo)
      // en vez de volver a correr este atajo.
      locationInput.value = locationPrefill.location;
      if (locationSectorCodeInput) locationSectorCodeInput.value = locationPrefill.sector_code;
      confirmField('location_display', locationPrefill.location);
      bhSaveState({
        wizard: {
          consentAccepted: true,
          location: locationPrefill.location,
          sectorCode: locationPrefill.sector_code,
          step: 'matricula'
        }
      });
      hide(stepAuthorization);
      show(stepMatricula);
      refreshServiceStatus();
    } else if (w.step === 'done') {
      if (w.location) confirmField('location_display', w.location);
      if (w.matricula) confirmField('registration_number', w.matricula);
      hide(stepAuthorization);
      showFullForm();
    } else if (w.step === 'matricula') {
      if (w.location) confirmField('location_display', w.location);
      hide(stepAuthorization);
      show(stepMatricula);
      refreshServiceStatus();
    } else if (w.step === 'location') {
      hide(stepAuthorization);
      show(stepLocation);
      refreshServiceStatus();
    }
  })();
