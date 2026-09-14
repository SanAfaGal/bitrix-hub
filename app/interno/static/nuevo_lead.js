(function () {
  var form = document.querySelector('.form');

  function collapseSpacesLive(value) {
    return value.replace(/^\s+/, '').replace(/ {2,}/g, ' ');
  }

  // Tipos de <input> (email, number, etc.) no soportan
  // selectionStart/setSelectionRange — acceder tira InvalidStateError. En
  // esos casos se pierde la posición del cursor (el valor igual queda
  // transformado), no hay forma de preservarla.
  function transformPreservingCursor(el, transformFn) {
    var oldValue = el.value;
    var newValue = transformFn(oldValue);
    if (newValue === oldValue) return;
    var cursorPos = null;
    try { cursorPos = el.selectionStart; } catch (e) { /* tipo sin selección */ }
    el.value = newValue;
    if (cursorPos !== null) {
      try {
        var newCursorPos = transformFn(oldValue.slice(0, cursorPos)).length;
        el.setSelectionRange(newCursorPos, newCursorPos);
      } catch (e) { /* tipo sin selección */ }
    }
  }

  function collapseSpacesAndUppercase(value) {
    return collapseSpacesLive(value).toUpperCase();
  }

  ['address', 'location'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', function () { transformPreservingCursor(el, collapseSpacesAndUppercase); clearFieldError(el); });
  });

  // Nombre: solo letras — bloquea números y símbolos al escribir, mismo
  // criterio que `onlyLettersUppercase` en app/forms/static/js/input_formatting.js
  // (misma regla que `validate_person_name` en app/shared/field_specs.py).
  function onlyLettersUppercase(value) {
    return collapseSpacesLive(value.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ'\-\s]/g, '')).toUpperCase();
  }
  var interestedPartyInput = document.getElementById('interested_party');
  if (interestedPartyInput) {
    interestedPartyInput.addEventListener('input', function () {
      transformPreservingCursor(interestedPartyInput, onlyLettersUppercase);
      clearFieldError(interestedPartyInput);
    });
  }

  // Teléfono: solo dígitos — mismo criterio que `validate_phone`
  // (`clean_digits`) en app/shared/field_specs.py.
  var phoneInput = document.getElementById('owner_phone');
  if (phoneInput) {
    phoneInput.addEventListener('input', function () {
      transformPreservingCursor(phoneInput, function (value) { return value.replace(/[^0-9]/g, ''); });
      clearFieldError(phoneInput);
    });
  }

  // Correo: única excepción a la mayúscula del resto del formulario — va
  // siempre en minúscula, mismo criterio que `clean_email`.
  function collapseSpacesLowercase(value) {
    return collapseSpacesLive(value).toLowerCase();
  }
  var emailInput = document.getElementById('email');
  if (emailInput) {
    emailInput.addEventListener('input', function () { transformPreservingCursor(emailInput, collapseSpacesLowercase); });
  }

  // Selector de indicativo de país: desplegable propio (ver
  // app/shared/phone_countries.py para la lista completa, ~245 países ya
  // renderizados server-side en las <li>) — clic en el botón lo abre/cierra,
  // el buscador filtra en cada tecla (necesario con tantas opciones), clic
  // en un país actualiza bandera/código/hidden input, clic afuera o Escape
  // lo cierra.
  var phoneCountryToggle = document.getElementById('phone-country-toggle');
  var phoneCountryDropdown = document.getElementById('phone-country-dropdown');
  var phoneCountrySearch = document.getElementById('phone-country-search');
  var phoneCountryList = document.getElementById('phone-country-list');
  var phoneCountryFlag = document.getElementById('phone-country-flag');
  var phoneCountryLabel = document.getElementById('phone-country-label');
  var phoneCountryCodeInput = document.getElementById('phone_country_code');
  if (phoneCountryToggle && phoneCountryDropdown) {
    var phoneCountryItems = Array.prototype.slice.call(
      phoneCountryList.querySelectorAll('.phone-country-list__item')
    );

    function closePhoneCountryDropdown() {
      phoneCountryDropdown.hidden = true;
      phoneCountryToggle.setAttribute('aria-expanded', 'false');
    }
    function openPhoneCountryDropdown() {
      phoneCountryDropdown.hidden = false;
      phoneCountryToggle.setAttribute('aria-expanded', 'true');
      phoneCountrySearch.value = '';
      phoneCountryItems.forEach(function (el) { el.classList.remove('phone-country-list__item--hidden'); });
      phoneCountrySearch.focus();
    }
    phoneCountryToggle.addEventListener('click', function (event) {
      event.preventDefault();
      if (phoneCountryDropdown.hidden) openPhoneCountryDropdown(); else closePhoneCountryDropdown();
    });

    var COMBINING_MARKS_RE = new RegExp('[\u0300-\u036f]', 'g');
    function normalize(value) {
      return value.normalize('NFKD').replace(COMBINING_MARKS_RE, '').toLowerCase();
    }
    phoneCountrySearch.addEventListener('input', function () {
      var query = normalize(phoneCountrySearch.value.trim());
      phoneCountryItems.forEach(function (item) {
        var name = normalize(item.querySelector('.phone-country-list__name').textContent);
        var matches = !query || name.indexOf(query) !== -1;
        item.classList.toggle('phone-country-list__item--hidden', !matches);
      });
    });

    phoneCountryItems.forEach(function (item) {
      item.addEventListener('click', function () {
        var code = item.getAttribute('data-code');
        var iso2 = item.getAttribute('data-iso2');
        phoneCountryFlag.src = 'https://flagcdn.com/w40/' + iso2 + '.png';
        phoneCountryLabel.textContent = '+' + code;
        phoneCountryCodeInput.value = code;
        phoneCountryItems.forEach(function (el) {
          el.classList.toggle('phone-country-list__item--active', el === item);
        });
        closePhoneCountryDropdown();
      });
    });
    document.addEventListener('click', function (event) {
      if (!phoneCountryToggle.contains(event.target) && !phoneCountryDropdown.contains(event.target)) {
        closePhoneCountryDropdown();
      }
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') closePhoneCountryDropdown();
    });
  }

  // Precio de venta: mismo formato visual "$ 500.000.000" que el público —
  // el backend limpia a solo dígitos (ver app/forms/cleaning.py).
  function formatAsCurrency(el) {
    el.addEventListener('input', function () {
      var digits = el.value.replace(/[^0-9]/g, '');
      el.value = digits ? '$ ' + Number(digits).toLocaleString('es-CO') : '';
    });
  }
  var priceInput = document.getElementById('sale_price');
  if (priceInput) formatAsCurrency(priceInput);

  // Limpia el error de cualquier campo (obligatorio o no) apenas la persona
  // vuelve a tocarlo, y trim final completo al salir del campo.
  Array.prototype.forEach.call(form.querySelectorAll('.field__input'), function (el) {
    el.addEventListener('input', function () { clearFieldError(el); });
    el.addEventListener('blur', function () {
      if (el.type === 'text' || el.type === 'email') el.value = el.value.trim().replace(/ {2,}/g, ' ');
    });
  });

  // Sugerencias de ubicación: desplegable propio (no <datalist> nativo),
  // mismo comportamiento que el público (ver
  // app/forms/static/js/input_formatting.js) — filtro en cada tecla,
  // navegación con flechas/Enter/Escape, y el envío se bloquea si la persona
  // escribió algo sin elegir una sugerencia.
  var locationInput = document.getElementById('location');
  var sectorCodeInput = document.getElementById('location_sector_code');
  var locationList = document.getElementById('location-suggestions');
  var locationSelected = Boolean(sectorCodeInput && sectorCodeInput.value);

  function validateLocationSelection() {
    if (locationInput && locationInput.value.trim() && !locationSelected) {
      showFieldError(locationInput, 'Selecciona una ubicación de la lista de sugerencias.');
      return locationInput;
    }
    return null;
  }

  if (locationInput && sectorCodeInput && locationList) {
    var allLocations = [];

    fetch('/formularios/ubicaciones')
      .then(function (response) { return response.ok ? response.json() : { locations: [] }; })
      .then(function (data) { allLocations = data.locations || []; })
      .catch(function () {
        // Sin sugerencias (DWH caído): el campo sigue funcionando como texto libre.
      });

    var COMBINING_MARKS_RE = new RegExp('[\u0300-\u036f]', 'g');
    function normalize(value) {
      return value.normalize('NFKD').replace(COMBINING_MARKS_RE, '').toLowerCase();
    }

    var currentMatches = [];
    var activeIndex = -1;

    function hideSuggestions() {
      locationList.hidden = true;
      locationList.innerHTML = '';
      currentMatches = [];
      activeIndex = -1;
    }

    function selectLocation(location) {
      locationInput.value = collapseSpacesAndUppercase(location.display_label);
      locationSelected = true;
      sectorCodeInput.value = location.sector_code || '';
      clearFieldError(locationInput);
      hideSuggestions();
    }

    function setActiveIndex(index) {
      var items = locationList.children;
      if (!items.length) {
        activeIndex = -1;
        return;
      }
      activeIndex = (index + items.length) % items.length;
      Array.prototype.forEach.call(items, function (item, i) {
        item.classList.toggle('location-suggest__item--active', i === activeIndex);
      });
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    }

    function showSuggestions() {
      var query = normalize(locationInput.value.trim());
      if (!query) return hideSuggestions();

      currentMatches = allLocations.filter(function (location) {
        return normalize(location.display_label).indexOf(query) !== -1;
      });
      activeIndex = -1;
      if (!currentMatches.length) return hideSuggestions();

      locationList.innerHTML = '';
      currentMatches.forEach(function (location) {
        var item = document.createElement('li');
        item.className = 'location-suggest__item';
        item.textContent = location.display_label;
        item.addEventListener('mousedown', function (event) {
          event.preventDefault();
          selectLocation(location);
        });
        locationList.appendChild(item);
      });
      locationList.hidden = false;
    }

    locationInput.addEventListener('input', function () {
      locationSelected = false;
      sectorCodeInput.value = '';
      showSuggestions();
    });
    locationInput.addEventListener('focus', showSuggestions);

    locationInput.addEventListener('keydown', function (event) {
      if (locationList.hidden) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActiveIndex(activeIndex + 1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveIndex(activeIndex - 1);
      } else if (event.key === 'Enter') {
        if (activeIndex === -1) return;
        event.preventDefault();
        selectLocation(currentMatches[activeIndex]);
      } else if (event.key === 'Escape') {
        hideSuggestions();
      }
    });
    locationInput.addEventListener('blur', hideSuggestions);
  }

  // Wizard de 2 pasos (Contacto / Inmueble) — ambos viven en el mismo <form>,
  // solo se muestra/oculta con CSS; el POST final sigue mandando todos los
  // campos juntos (ver app/interno/router.py). `data-start-step` decide en
  // qué paso abre: "inmueble" si se está re-renderizando tras un intento de
  // submit fallido (ver `_render_nuevo_lead`), "contacto" en un GET normal.
  var stepContacto = document.getElementById('step-contacto');
  var stepInmueble = document.getElementById('step-inmueble');
  var nextButton = document.getElementById('step-contacto-next');
  var backButton = document.getElementById('step-inmueble-back');

  function showStep(name) {
    stepContacto.hidden = name !== 'contacto';
    stepInmueble.hidden = name !== 'inmueble';
  }

  showStep(form.getAttribute('data-start-step') === 'inmueble' ? 'inmueble' : 'contacto');

  // Aviso de contacto existente: al salir del teléfono, consulta
  // /interno/nuevo-lead/contacto (solo lectura, no crea nada) — si ya hay un
  // contacto con ese teléfono, exige el check de confirmación antes de dejar
  // avanzar al paso 2 (ver app/interno/router.py::get_nuevo_lead_contacto).
  var lookupPanel = document.getElementById('contact-lookup-panel');
  var lookupName = document.getElementById('contact-lookup-name');
  var lookupDealLink = document.getElementById('contact-lookup-deal-link');
  var lookupConfirm = document.getElementById('contact-lookup-confirm');
  var lastLookedUpPhone = null;
  var pendingLookupKey = null;
  var pendingLookupPromise = null;
  var contactExists = false;

  function resetLookup() {
    contactExists = false;
    lookupPanel.hidden = true;
    lookupConfirm.checked = false;
  }

  function lookupContact() {
    var digits = (phoneInput ? phoneInput.value : '').trim();
    if (!digits) { resetLookup(); lastLookedUpPhone = null; return Promise.resolve(); }
    var countryCode = phoneCountryCodeInput ? phoneCountryCodeInput.value : '';
    var cacheKey = countryCode + ':' + digits;
    // Ya resuelto para este teléfono: no repetir el fetch.
    if (cacheKey === lastLookedUpPhone) return Promise.resolve();
    // Ya hay un fetch en curso para este mismo teléfono (ej. el del blur
    // todavía no respondió cuando se hizo clic en "Siguiente") — reusar esa
    // misma promesa en vez de marcar el caché de una, que dejaba avanzar con
    // `contactExists` desactualizado antes de que llegara la respuesta real.
    if (cacheKey === pendingLookupKey) return pendingLookupPromise;

    var url = '/interno/nuevo-lead/contacto?phone=' + encodeURIComponent(digits)
      + '&phone_country_code=' + encodeURIComponent(countryCode);
    pendingLookupKey = cacheKey;
    pendingLookupPromise = fetch(url)
      .then(function (response) { return response.ok ? response.json() : { exists: false }; })
      .then(function (data) {
        lastLookedUpPhone = cacheKey;
        contactExists = Boolean(data.exists);
        if (!contactExists) { resetLookup(); return; }
        lookupName.textContent = data.name || '(sin nombre en Bitrix)';
        if (data.existing_deal_id) {
          lookupDealLink.textContent = 'Deal anterior #' + data.existing_deal_id;
          lookupDealLink.href = '/interno/lead/' + encodeURIComponent(data.existing_deal_id);
          lookupDealLink.hidden = false;
        } else {
          lookupDealLink.hidden = true;
        }
        lookupPanel.hidden = false;
        lookupConfirm.checked = false;
      })
      .catch(function () {
        // Sin verificación (backend caído): no bloquea, se avanza igual.
        lastLookedUpPhone = null;
        resetLookup();
      })
      .then(function () {
        pendingLookupKey = null;
        pendingLookupPromise = null;
      });
    return pendingLookupPromise;
  }

  if (phoneInput) phoneInput.addEventListener('blur', lookupContact);

  if (nextButton) {
    nextButton.addEventListener('click', function () {
      var missingField = markMissingRequiredFields(stepContacto, 'Dato obligatorio para crear el lead.');
      if (missingField) { missingField.focus(); return; }
      // Espera a que termine la verificación de contacto duplicado antes de decidir —
      // si se hace clic justo después de escribir el teléfono, el fetch del blur puede
      // seguir en curso; sin este await se podía avanzar de paso con `contactExists`
      // todavía en su valor viejo (antes de que respondiera el backend).
      nextButton.disabled = true;
      lookupContact().then(function () {
        nextButton.disabled = false;
        if (contactExists && !lookupConfirm.checked) {
          lookupConfirm.focus();
          return;
        }
        showStep('inmueble');
      });
    });
  }

  if (backButton) {
    backButton.addEventListener('click', function () { showStep('contacto'); });
  }

  // Bloquea el envío nativo si falta algo obligatorio o la ubicación no fue
  // elegida de la lista — igual criterio que el público
  // (app/forms/static/js/submit.js), pero sin fetch: si todo está bien, deja
  // que el <form> se mande solo.
  // Spinner en el botón mientras se crea el contacto + deal en Bitrix — el
  // POST es un submit normal de HTML (recarga de página, ver
  // app/interno/router.py), así que esto no reemplaza el envío ni lo
  // demora: solo se ve mientras el navegador espera la respuesta antes de
  // navegar a /interno/lead/{id}.
  var submitButton = document.getElementById('submit-button');
  var submitButtonText = document.getElementById('submit-button-text');
  form.addEventListener('submit', function (evt) {
    var missingField = markMissingRequiredFields(form, 'Dato obligatorio para crear el lead.');
    var invalidLocation = !missingField ? validateLocationSelection() : null;
    var firstInvalid = missingField || invalidLocation;
    if (firstInvalid) {
      evt.preventDefault();
      firstInvalid.focus();
      return;
    }
    submitButton.disabled = true;
    submitButtonText.innerHTML = '<span class="status-loading"><span class="spinner"></span>Creando lead...</span>';
  });
})();
