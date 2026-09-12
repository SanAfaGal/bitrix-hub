// Filtros en cascada (país→departamento→ciudad→zona→sector), búsqueda de
// texto, selección masiva (incluido clic en cualquier parte de la fila) y
// contadores — vainilla, sin build step.
//
// Todo corre sobre las filas ya renderizadas por el servidor, sin red. Los
// datos de cada fila se leen del DOM una sola vez al cargar (_buildRecords)
// y se guardan en un arreglo plano — filtrar/recalcular cascada después solo
// toca ese arreglo en memoria, no vuelve a leer atributos del DOM fila por
// fila, que es lo que hacía pesado escribir en el buscador con ~2000 filas.
(function () {
  var table = document.querySelector('[data-coverage-table]');
  if (!table) return;

  var LEVELS = ['pais', 'departamento', 'ciudad', 'zona', 'sector'];

  var searchInput = document.querySelector('[data-coverage-search]');
  var selectAllVisible = document.querySelector('[data-coverage-select-all]');
  var visibleCountLabel = document.querySelector('[data-coverage-visible-count]');
  var selectedCountLabel = document.querySelector('[data-coverage-selected-count]');
  var actionButtons = Array.prototype.slice.call(document.querySelectorAll('[data-coverage-action]'));
  var clearButton = document.querySelector('[data-coverage-clear]');
  var estadoSelect = document.querySelector('[data-coverage-estado]');
  var cascadeSelects = {};
  Array.prototype.slice.call(document.querySelectorAll('[data-coverage-cascade]')).forEach(function (select) {
    cascadeSelects[select.getAttribute('data-coverage-cascade')] = select;
  });

  var selections = { pais: '', departamento: '', ciudad: '', zona: '', sector: '' };
  var searchTerm = '';

  // Leído una sola vez del DOM — filtrar/cascada después solo recorre este arreglo.
  var records = Array.prototype.slice.call(table.querySelectorAll('[data-coverage-row]')).map(function (row) {
    var record = { row: row, checkbox: row.querySelector('[data-coverage-checkbox]'), search: row.getAttribute('data-search') || '' };
    LEVELS.forEach(function (level) { record[level] = row.getAttribute('data-' + level) || ''; });
    return record;
  });

  function matchesUpstream(record, level) {
    for (var i = 0; i < LEVELS.indexOf(level); i++) {
      var upperLevel = LEVELS[i];
      if (selections[upperLevel] && record[upperLevel] !== selections[upperLevel]) return false;
    }
    return true;
  }

  function populateSelect(level) {
    var select = cascadeSelects[level];
    if (!select) return;
    var values = {};
    records.forEach(function (record) {
      if (matchesUpstream(record, level) && record[level]) values[record[level]] = true;
    });
    var sorted = Object.keys(values).sort(function (a, b) { return a.localeCompare(b, 'es'); });
    var placeholder = select.options.length ? select.options[0].textContent : level;
    select.innerHTML = '';
    var placeholderOption = document.createElement('option');
    placeholderOption.value = '';
    placeholderOption.textContent = placeholder;
    select.appendChild(placeholderOption);
    sorted.forEach(function (value) {
      var option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
    select.value = selections[level] && sorted.indexOf(selections[level]) !== -1 ? selections[level] : '';
    selections[level] = select.value;
  }

  function recomputeCascadeFrom(level) {
    var startIndex = LEVELS.indexOf(level) + 1;
    for (var i = startIndex; i < LEVELS.length; i++) {
      selections[LEVELS[i]] = '';
      populateSelect(LEVELS[i]);
    }
  }

  function recordMatches(record) {
    for (var i = 0; i < LEVELS.length; i++) {
      var level = LEVELS[i];
      if (selections[level] && record[level] !== selections[level]) return false;
    }
    return searchTerm === '' || record.search.indexOf(searchTerm) !== -1;
  }

  function applyFilters() {
    var visible = 0;
    records.forEach(function (record) {
      var matches = recordMatches(record);
      record.row.hidden = !matches;
      if (matches) visible++;
    });
    if (visibleCountLabel) visibleCountLabel.textContent = visible + ' de ' + records.length;
    updateSelectAllState();
    updateClearButtonVisibility();
  }

  function updateClearButtonVisibility() {
    if (!clearButton) return;
    var hasCascade = LEVELS.some(function (level) { return !!selections[level]; });
    var hasEstado = estadoSelect && estadoSelect.value !== 'todos';
    clearButton.hidden = !(hasCascade || searchTerm || hasEstado);
  }

  function updateSelectAllState() {
    if (!selectAllVisible) return;
    var visibleRecords = records.filter(function (r) { return !r.row.hidden; });
    var allChecked = visibleRecords.length > 0 && visibleRecords.every(function (r) { return r.checkbox && r.checkbox.checked; });
    selectAllVisible.checked = allChecked;
  }

  function updateSelectedCount() {
    var checked = records.filter(function (r) { return r.checkbox && r.checkbox.checked; }).length;
    if (selectedCountLabel) selectedCountLabel.textContent = checked + ' seleccionados';
    actionButtons.forEach(function (btn) { btn.disabled = checked === 0; });
  }

  var searchDebounce = null;
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      if (searchDebounce) clearTimeout(searchDebounce);
      searchDebounce = setTimeout(function () {
        searchTerm = searchInput.value.trim().toLowerCase();
        applyFilters();
      }, 150);
    });
  }

  LEVELS.forEach(function (level) {
    var select = cascadeSelects[level];
    if (!select) return;
    select.addEventListener('change', function () {
      selections[level] = select.value;
      recomputeCascadeFrom(level);
      applyFilters();
    });
  });

  if (selectAllVisible) {
    selectAllVisible.addEventListener('change', function () {
      records.forEach(function (record) {
        if (record.row.hidden || !record.checkbox) return;
        record.checkbox.checked = selectAllVisible.checked;
      });
      updateSelectedCount();
    });
  }

  records.forEach(function (record) {
    if (!record.checkbox) return;
    record.checkbox.addEventListener('change', function () {
      updateSelectedCount();
      updateSelectAllState();
    });
    record.checkbox.addEventListener('click', function (e) { e.stopPropagation(); });
    record.row.addEventListener('click', function (e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'A' || e.target.tagName === 'BUTTON') return;
      record.checkbox.checked = !record.checkbox.checked;
      record.checkbox.dispatchEvent(new Event('change'));
    });
  });

  if (clearButton) {
    clearButton.addEventListener('click', function () {
      if (searchInput) searchInput.value = '';
      searchTerm = '';
      // Si estado (con/sin cobertura) no es el default, resetearlo implica
      // recargar la página (esos datos viven del lado del servidor) — el
      // propio onchange del select ya sabe navegar, solo hace falta dispararlo.
      // Eso también descarta la selección de checkboxes, igual que ya pasa
      // hoy al cambiar estado a mano: es un efecto esperado, no un bug nuevo.
      if (estadoSelect && estadoSelect.value !== 'todos') {
        estadoSelect.value = 'todos';
        estadoSelect.dispatchEvent(new Event('change'));
        return;
      }
      LEVELS.forEach(function (level) { selections[level] = ''; });
      LEVELS.forEach(function (level) { populateSelect(level); });
      applyFilters();
    });
  }

  LEVELS.forEach(function (level) { populateSelect(level); });
  applyFilters();
  updateSelectedCount();
})();
