// Sugerencias de ubicación: reusa el mismo endpoint que app/forms/ (no un catálogo
// aparte, ver app/location_catalog/router.py).
(function () {
  var locationInput = document.getElementById("location");
  var sectorCodeInput = document.getElementById("location_sector_code");
  var datalist = document.getElementById("location-suggestions");
  if (!locationInput || !sectorCodeInput || !datalist) return;

  var byLabel = {};

  fetch("/formularios/ubicaciones")
    .then(function (response) { return response.json(); })
    .then(function (data) {
      (data.locations || []).forEach(function (loc) {
        byLabel[loc.display_label] = loc.sector_code;
        var option = document.createElement("option");
        option.value = loc.display_label;
        datalist.appendChild(option);
      });
    })
    .catch(function () {
      // Sin sugerencias (DWH caído): el campo sigue funcionando como texto libre.
    });

  locationInput.addEventListener("input", function () {
    var match = byLabel[locationInput.value];
    sectorCodeInput.value = match || "";
  });
})();
