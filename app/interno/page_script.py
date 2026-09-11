"""JS del formulario interno de nuevo lead.

Mismo patrón que `app/forms/page_script.py`: se arma concatenando texto
dentro de una sola IIFE. Reusa `FIELD_VALIDATION_SCRIPT`
(`app/shared/field_validation_script.py`) para que el resaltado de campos
obligatorios y el mensaje sean el mismo código que usa el formulario
público, no una copia a mano — y por eso este archivo es `.py` en vez de un
`.js` estático (JS no puede importar de Python).

A diferencia del público, este formulario no hace envío por `fetch`/JSON: es
un POST normal de HTML con recarga de página (ver `app/interno/router.py`),
así que el único trabajo del `submit` listener acá es bloquear el envío si
algo no pasa la validación en vivo — si todo está bien, deja que el navegador
mande el formulario tal cual.
"""
from __future__ import annotations

from app.shared.field_validation_script import FIELD_VALIDATION_SCRIPT

NUEVO_LEAD_SCRIPT = (
    """<script>
(function () {
  var form = document.querySelector('.form');
"""
    + FIELD_VALIDATION_SCRIPT
    + """
  function collapseSpacesLive(value) {
    return value.replace(/^\\s+/, '').replace(/ {2,}/g, ' ');
  }

  function transformPreservingCursor(el, transformFn) {
    var cursorPos = el.selectionStart;
    var oldValue = el.value;
    var newValue = transformFn(oldValue);
    if (newValue === oldValue) return;
    var newCursorPos = transformFn(oldValue.slice(0, cursorPos)).length;
    el.value = newValue;
    el.setSelectionRange(newCursorPos, newCursorPos);
  }

  function collapseSpacesAndUppercase(value) {
    return collapseSpacesLive(value).toUpperCase();
  }

  ['interested_party', 'address', 'location'].forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', function () { transformPreservingCursor(el, collapseSpacesAndUppercase); clearFieldError(el); });
  });

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
  // app/forms/page_script_inputs.py) — filtro en cada tecla, navegación con
  // flechas/Enter/Escape, y el envío se bloquea si la persona escribió algo
  // sin elegir una sugerencia.
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

    var COMBINING_MARKS_RE = new RegExp('[\\u0300-\\u036f]', 'g');
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

  // Bloquea el envío nativo si falta algo obligatorio o la ubicación no fue
  // elegida de la lista — igual criterio que el público
  // (app/forms/page_script_submit.py), pero sin fetch: si todo está bien,
  // deja que el <form> se mande solo.
  form.addEventListener('submit', function (evt) {
    var missingField = markMissingRequiredFields(form, 'Dato obligatorio para crear el lead.');
    var invalidLocation = !missingField ? validateLocationSelection() : null;
    var firstInvalid = missingField || invalidLocation;
    if (firstInvalid) {
      evt.preventDefault();
      firstInvalid.focus();
    }
  });
})();
</script>"""
)
