// Panel de WhatsApp: poll de estado de la sesión de Waha + refresco del QR mientras
// espera a que alguien escanee — sin recargar la página.
//
// Dos temporizadores independientes, arrancados solo si la sesión no está en un
// estado final (WORKING/STOPPED/FAILED) al cargar la página:
// - pollStatus(): cada pocos segundos, pide el fragmento de estado a
//   {WHATSAPP_PATH}/status, pero solo reemplaza .whatsapp-status-panel
//   (outerHTML) si el data-status realmente cambió — si sigue igual (ej.
//   sigue en SCAN_QR_CODE) no toca el DOM. De lo contrario, cada poll volvía
//   a montar un <img> nuevo con src="" y borraba el QR que fetchQr ya había
//   puesto, así que el QR se veía parpadear y desaparecer en vez de quedarse
//   fijo hasta el siguiente refresco real.
// - pollQr(): cada ~15-18s mientras el estado sea SCAN_QR_CODE (el QR de Waha
//   expira a los 20s), pide uno nuevo a {WHATSAPP_PATH}/qr (JSON, no HTML) y
//   solo reemplaza el atributo src de la imagen — evita reflow del resto del panel.
//
// Un AbortController por fetch en vuelo, igual que prospects.js, para que un poll
// lento no se pise con el siguiente.
(() => {
  const WHATSAPP_PATH = "/admin/whatsapp";
  const STATUS_POLL_MS = 4000;
  const QR_POLL_MS = 15000;

  const TRANSIENT_STATUSES = new Set(["STARTING", "SCAN_QR_CODE", "PASSKEY_REQUIRED", "PASSKEY_CONFIRMATION_REQUIRED"]);

  let statusTimer = null;
  let qrTimer = null;
  let statusController = null;
  let qrController = null;

  function stopPolling() {
    if (statusTimer) clearInterval(statusTimer);
    if (qrTimer) clearInterval(qrTimer);
    statusTimer = null;
    qrTimer = null;
    if (statusController) statusController.abort();
    if (qrController) qrController.abort();
  }

  async function fetchQr() {
    if (qrController) qrController.abort();
    const controller = new AbortController();
    qrController = controller;

    let data;
    try {
      const response = await fetch(`${WHATSAPP_PATH}/qr`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (err) {
      if (err.name === "AbortError") return;
      console.error("No se pudo obtener el QR de WhatsApp", err);
      return;
    }
    const img = document.querySelector("[data-whatsapp-qr]");
    if (img && data.qr) img.src = data.qr;
  }

  function startQrPolling() {
    if (qrTimer) return;
    fetchQr();
    qrTimer = setInterval(fetchQr, QR_POLL_MS);
  }

  async function pollStatus() {
    if (statusController) statusController.abort();
    const controller = new AbortController();
    statusController = controller;

    let html;
    try {
      const response = await fetch(`${WHATSAPP_PATH}/status`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      html = await response.text();
    } catch (err) {
      if (err.name === "AbortError") return;
      console.error("No se pudo consultar el estado de WhatsApp", err);
      return;
    }

    const panel = document.querySelector(".whatsapp-status-panel");
    if (!panel) return;

    const parsed = new DOMParser().parseFromString(html, "text/html");
    const parsedPanel = parsed.querySelector(".whatsapp-status-panel");
    const status = parsedPanel ? parsedPanel.dataset.status : "";

    if (status === panel.dataset.status) return; // sin cambios — no pisar el QR ya cargado

    panel.outerHTML = html;
    if (!TRANSIENT_STATUSES.has(status)) {
      stopPolling();
      return;
    }
    if (status === "SCAN_QR_CODE") {
      startQrPolling();
    } else if (qrTimer) {
      clearInterval(qrTimer);
      qrTimer = null;
    }
  }

  function init() {
    const panel = document.querySelector(".whatsapp-status-panel");
    const status = panel ? panel.dataset.status : "";
    if (!TRANSIENT_STATUSES.has(status)) return;

    statusTimer = setInterval(pollStatus, STATUS_POLL_MS);
    if (status === "SCAN_QR_CODE") startQrPolling();
  }

  window.addEventListener("beforeunload", stopPolling);
  init();
})();
