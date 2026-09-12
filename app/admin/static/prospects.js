// Prospectos: cambiar de chat sin recargar la página completa.
//
// Antes, cada clic en la lista navegaba a `/admin/prospects/{key}` — una
// página completa que reconstruye la lista entera del lado del servidor
// (scan completo de mensajes) además del hilo seleccionado. Con clics
// rápidos, esas requests pesadas se acumulaban y el pool de conexiones a la
// base de datos se agotaba, bloqueando toda la UI admin.
//
// Ahora el clic hace fetch de `/admin/prospects/{key}/detail` (solo el
// fragmento del hilo, sin la lista) y reemplaza `.prospect-thread-pane` en
// el DOM. Un `AbortController` cancela la request anterior si el usuario
// hace clic en otro chat antes de que la primera responda, así clics
// rápidos no dejan requests huérfanas corriendo en el servidor.
//
// Solo se intercepta el canal WhatsApp (`data-channel="whatsapp"`) — los
// leads de correo no tienen endpoint `/detail` (no tienen `chat_id`) y
// siguen navegando de la forma clásica.
(() => {
  const listPane = document.querySelector(".prospect-list-pane");
  if (!listPane) return;

  let pendingController = null;

  function setActiveRow(key) {
    listPane.querySelectorAll(".prospect-row").forEach((row) => {
      row.classList.toggle("prospect-row--active", row.dataset.rowKey === key);
    });
  }

  async function loadThread(key, url) {
    if (pendingController) pendingController.abort();
    const controller = new AbortController();
    pendingController = controller;

    let html;
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      html = await response.text();
    } catch (err) {
      if (err.name === "AbortError") return; // el usuario ya hizo clic en otro chat
      console.error("No se pudo cargar el prospecto", err);
      return;
    }
    if (pendingController !== controller) return; // una request más nueva ya ganó

    const currentPane = document.querySelector(".prospect-thread-pane");
    if (currentPane) currentPane.outerHTML = html;

    setActiveRow(key);
    document.querySelector(".prospects-layout")?.classList.add("prospects-layout--has-selection");
    history.pushState({ prospectKey: key }, "", `/admin/prospects/${encodeURIComponent(key)}`);
  }

  listPane.addEventListener("click", (event) => {
    const row = event.target.closest(".prospect-row");
    if (!row || row.dataset.channel !== "whatsapp") return;

    event.preventDefault();
    const key = row.dataset.rowKey;
    loadThread(key, `/admin/prospects/${encodeURIComponent(key)}/detail`);
  });

  window.addEventListener("popstate", () => {
    // Volver/avanzar del navegador: más simple y confiable recargar la
    // página completa que reconstruir el estado del lado del cliente.
    location.reload();
  });
})();
