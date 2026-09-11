"""JS de formato/validación en vivo de los campos de texto del formulario.

Fragmento de FORM_SCRIPT (ver page_script.py) — separado por tamaño. Corre
dentro de la misma IIFE que el resto de los fragmentos, no tiene scope
propio: declara funciones y variables (`locationInput`, `locationSelected`,
`validateLocationSelection`) que usan tanto page_script_submit.py (validación
al enviar, restaurar campos) como page_wizard_script.py (que comparte
`field-location` por id, no por variable JS).
"""
from __future__ import annotations

INPUT_FORMATTING_SCRIPT = """  // Sin espacios al principio, y nunca más de uno seguido — se aplica en
  // cada tecla, no solo al salir del campo, para que la persona nunca vea
  // "   dfdfdfd   " mientras escribe. Deja un espacio final suelto (para
  // poder seguir escribiendo la siguiente palabra); el trim final completo
  // pasa al salir del campo (ver el listener 'blur' más abajo).
  function collapseSpacesLive(value) {
    return value.replace(/^\s+/, '').replace(/ {2,}/g, ' ');
  }

  // Aplica `transformFn` al valor y reubica el cursor donde debería quedar,
  // en vez de dejar que el navegador lo mande al final del campo (lo que
  // pasa siempre que se reasigna `el.value` a mano) — así se puede seguir
  // corrigiendo en medio de un nombre o dirección sin que el cursor salte.
  // Funciona porque estas transformaciones son "estables por prefijo": el
  // resultado de transformar todo el texto hasta el cursor no cambia según
  // lo que venga después (quitar caracteres o colapsar espacios cumple esto;
  // el formato de moneda no, por eso los montos no usan este helper).
  function transformPreservingCursor(el, transformFn) {
    var oldValue = el.value;
    var newValue = transformFn(oldValue);
    if (newValue === oldValue) return;
    // Tipos de <input> (email, number, etc.) no soportan
    // selectionStart/setSelectionRange — acceder tira InvalidStateError
    // (ej. el campo de correo, más abajo). En esos casos se pierde la
    // posición del cursor, no hay forma de preservarla.
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

  // Formato visual "$ 500.000.000" mientras se escribe — el backend igual
  // limpia a solo dígitos (ver app/forms/cleaning.py), esto es solo display.
  // Mismo criterio para precio de venta y saldo de la deuda: son el mismo
  // tipo de dato (un monto en pesos), deben verse igual. El cursor se deja
  // al final: los separadores de miles se recalculan enteros con cada
  // dígito, no hay una posición "estable" que preservar como en el resto de
  // los campos (típico también en inputs de moneda de otros formularios).
  function formatAsCurrency(el) {
    el.addEventListener('input', function () {
      var digits = el.value.replace(/[^0-9]/g, '');
      el.value = digits ? '$ ' + Number(digits).toLocaleString('es-CO') : '';
    });
  }
  ['field-sale_price', 'field-outstanding_debt'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) formatAsCurrency(el);
  });

  // Solo letras en el nombre — bloquea números y símbolos al escribir, en
  // vez de dejar que se note hasta que el backend lo rechace al enviar
  // (misma regla que `_NAME_RE` en app/forms/models.py). Todo el formulario
  // va en mayúscula, salvo el correo.
  function onlyLettersUppercase(value) {
    return collapseSpacesLive(value.replace(/[^A-Za-zÀ-ÖØ-öø-ÿ'\-\s]/g, '')).toUpperCase();
  }
  ['field-interested_party'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', function () { transformPreservingCursor(el, onlyLettersUppercase); });
  });

  // Documento de identidad: letras, números y guion (cédula, cédula de
  // extranjería o pasaporte) — el guion se deja tal cual, sin puntos ni
  // espacios (mismo criterio que app.forms.cleaning.clean_id_number).
  function onlyAlnumHyphenUppercase(value) {
    return value.replace(/[^A-Za-z0-9-]/g, '').toUpperCase();
  }
  ['field-id_number'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', function () { transformPreservingCursor(el, onlyAlnumHyphenUppercase); });
  });

  // Dirección y ubicación: sin espacios al principio ni dobles, y en
  // mayúscula. Ubicación no se restringe a solo letras (a diferencia del
  // nombre) porque su valor real incluye coma y punto (ej. "EL POBLADO,
  // MEDELLÍN, ANTIOQUIA", "BOGOTÁ D.C.") — mismo criterio que `_LOCATION_RE`
  // en app/forms/models.py; las sugerencias del datalist ya guían el formato.
  function collapseSpacesAndUppercase(value) {
    return collapseSpacesLive(value).toUpperCase();
  }
  ['field-address', 'field-location'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', function () { transformPreservingCursor(el, collapseSpacesAndUppercase); });
  });

  // Sugerencias de ubicación: desplegable propio (no <datalist> nativo, para
  // poder limitarlo a 5 filas y usar la tipografía de marca — ver
  // .location-suggest en page_styles_fields.py). El catálogo completo se
  // trae una sola vez al abrir el formulario desde /formularios/ubicaciones
  // (backend cachea en memoria, ver app/location_catalog/) y se filtra en
  // el cliente en cada tecla. Si el fetch falla (red caída, backend sin
  // conexión a la base externa), el campo sigue siendo texto libre sin
  // sugerencias — nunca bloquea el resto del formulario.
  var locationInput = document.getElementById('field-location');
  var locationList = document.getElementById('location-suggestions');
  // true solo entre el momento en que se hace clic en una sugerencia y el
  // siguiente cambio manual del campo — el envío se bloquea si no está en
  // true (ver validateLocationSelection más abajo, usado por el submit).
  var locationSelected = false;
  function validateLocationSelection() {
    if (locationInput && locationInput.value.trim() && !locationSelected) {
      showFieldError(locationInput, 'Selecciona una ubicación de la lista de sugerencias.');
      return locationInput;
    }
    return null;
  }
  if (locationInput && locationList) {
    var allLocations = [];

    fetch('/formularios/ubicaciones')
      .then(function (response) { return response.ok ? response.json() : { locations: [] }; })
      .then(function (data) { allLocations = data.locations || []; })
      .catch(function () { /* sin sugerencias, el campo sigue siendo texto libre */ });

    // Regex construido con new RegExp() (en vez de /literal/) a propósito:
    // evita que el archivo fuente tenga que llevar el propio carácter Unicode
    // combinante en medio del código.
    var COMBINING_MARKS_RE = new RegExp('[\\u0300-\\u036f]', 'g');
    function normalize(value) {
      return value.normalize('NFKD').replace(COMBINING_MARKS_RE, '').toLowerCase();
    }

    // Coincidencias visibles y cuál está resaltada con las flechas — se
    // recalculan en cada showSuggestions()/hideSuggestions(), las usa el
    // manejador de teclado de más abajo para saber qué seleccionar con Enter.
    var currentMatches = [];
    var activeIndex = -1;

    function hideSuggestions() {
      locationList.hidden = true;
      locationList.innerHTML = '';
      currentMatches = [];
      activeIndex = -1;
    }

    function selectLocation(location) {
      // Mayúsculas igual que si la persona lo hubiera tecleado (mismo
      // criterio que el resto del formulario) — se aplica acá en vez de
      // disparar un evento 'input' sintético, porque ese evento también
      // dispararía el listener de abajo que invalida `locationSelected`.
      locationInput.value = collapseSpacesAndUppercase(location.display_label);
      locationSelected = true;
      // sector_code viaja en un input oculto propio (ver page_wizard.py) en
      // vez de una variable JS: así page_wizard_script.py (otra IIFE
      // independiente, ver su docstring) lo puede leer sin acoplarse a este
      // archivo, y ya queda listo para viajar tal cual en el submit final.
      var sectorCodeInput = document.getElementById('field-location_sector_code');
      if (sectorCodeInput) sectorCodeInput.value = location.sector_code || '';
      clearFieldError(locationInput);
      hideSuggestions();
    }

    // Mueve el resaltado a `index` (con wraparound) y lo refleja en el DOM
    // (clase .location-suggest__item--active) y con scroll si queda fuera
    // de las ~5 filas visibles del contenedor.
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

      // Sin límite acá: se muestran todas las coincidencias, el contenedor
      // (.location-suggest en page_styles_fields.py) es el que fija la
      // altura a 5 filas y hace scroll para el resto.
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
        // 'mousedown' (no 'click'): dispara antes que el 'blur' del input,
        // así el desplegable no se esconde antes de registrar la selección.
        item.addEventListener('mousedown', function (event) {
          event.preventDefault();
          selectLocation(location);
        });
        locationList.appendChild(item);
      });
      locationList.hidden = false;
    }

    locationInput.addEventListener('input', function () {
      // Cualquier edición manual invalida la selección anterior — solo
      // vuelve a quedar válida si la persona elige de nuevo una sugerencia.
      locationSelected = false;
      var sectorCodeInput = document.getElementById('field-location_sector_code');
      if (sectorCodeInput) sectorCodeInput.value = '';
      showSuggestions();
    });
    locationInput.addEventListener('focus', showSuggestions);

    // Flechas para moverse entre sugerencias sin soltar el teclado, Enter
    // para elegir la resaltada (sin enviar el formulario de paso) y Escape
    // para cerrar el desplegable sin perder lo ya escrito.
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

  // Matrícula: dígitos, letras (código de oficina, ej. "50C") y guion, sin
  // ningún espacio — no es texto libre como la dirección, es un código
  // (misma regla que `_REGISTRATION_NUMBER_RE` en app/forms/models.py).
  function onlyAlnumAndHyphen(value) {
    return value.toUpperCase().replace(/[^0-9A-Z-]/g, '');
  }
  var registrationNumberInput = document.getElementById('field-registration_number');
  if (registrationNumberInput) {
    registrationNumberInput.addEventListener('input', function () {
      transformPreservingCursor(registrationNumberInput, onlyAlnumAndHyphen);
    });
  }

  // Correo: única excepción a la mayúscula del resto del formulario — va
  // siempre en minúscula, en vivo mientras se escribe (mismo criterio que
  // `clean_email` en app/forms/cleaning.py).
  function collapseSpacesLowercase(value) {
    return collapseSpacesLive(value).toLowerCase();
  }
  var emailInput = document.getElementById('field-email');
  if (emailInput) {
    emailInput.addEventListener('input', function () {
      transformPreservingCursor(emailInput, collapseSpacesLowercase);
    });
  }

  // Trim final completo en todos los campos de texto al salir del campo —
  // el backend igual limpia esto (`app/forms/cleaning.py`), pero así la
  // persona ve el dato limpio antes de enviar, no solo después.
  Array.prototype.forEach.call(document.querySelectorAll('input[type="text"], input[type="email"]'), function (el) {
    el.addEventListener('blur', function () {
      el.value = el.value.trim().replace(/ {2,}/g, ' ');
    });
  });

"""
