"""HTML de la vista de gestión de la sesión de WhatsApp (Waha) — HTML sueltos en
app/admin/templates/whatsapp.html + app/admin/static/(whatsapp.css/whatsapp.js), sigue el
patrón de app/interno/. Fragmentos repetidos (los distintos estados de la sesión) son
macros Jinja en app/admin/jinja_templates/_whatsapp_fragments.html — este archivo solo
arma los datos y llama a esos macros.

Solo una sesión (`WAHA_SESSION`) por ahora — no hay selector de línea. El fragmento de
estado (`render_whatsapp_status_fragment_html`) es lo que `whatsapp.js` pide en bucle
(cada 3-4s) y reemplaza vía `outerHTML` mientras la sesión esté en un estado transitorio
(STARTING/SCAN_QR_CODE/PASSKEY_*) — mismo patrón que `prospects.js` con
`.prospect-thread-pane`. El QR en sí se pide aparte (`GET {WHATSAPP_PATH}/qr`, JSON, no
HTML) para no decodificar el PNG en cada poll de estado cuando todavía no toca
refrescarlo (ver `app.waha.client.WahaClient.get_qr_code`, que expira cada ~20s).
"""
from __future__ import annotations

from pathlib import Path

from app.admin.page import WHATSAPP_PATH, render_app_shell
from app.shared.html_templates import RawHTML, render_template
from app.shared.jinja_env import get_env

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_JINJA_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"

# Estados en los que la sesión todavía no terminó de resolverse — mientras esté en
# alguno de estos, whatsapp.js sigue haciendo poll de estado (ver data-status en el
# wrapper que devuelven los macros).
TRANSIENT_STATUSES = {"STARTING", "SCAN_QR_CODE", "PASSKEY_REQUIRED", "PASSKEY_CONFIRMATION_REQUIRED"}


def _fragments():
    return get_env(str(_JINJA_TEMPLATES_DIR)).get_template("_whatsapp_fragments.html").module


def render_whatsapp_status_fragment_html(*, status_payload: dict | None) -> str:
    """Fragmento AJAX (wrapper `.whatsapp-status-panel` + su contenido según el estado) —
    usado tanto en la carga inicial de la página como en la respuesta del poll de
    `whatsapp.js` (`GET {WHATSAPP_PATH}/status`)."""
    fragments = _fragments()
    if status_payload is None:
        return fragments.error_panel(WHATSAPP_PATH)

    status = status_payload.get("status")
    if status == "STOPPED":
        return fragments.stopped_panel(WHATSAPP_PATH)
    if status in TRANSIENT_STATUSES:
        return fragments.qr_panel(WHATSAPP_PATH, status)
    if status == "WORKING":
        me = status_payload.get("me") if isinstance(status_payload.get("me"), dict) else {}
        phone = me.get("pushName") or me.get("id") or None
        return fragments.connected_panel(WHATSAPP_PATH, phone)
    if status == "FAILED":
        # Waha recomienda "restart" para recuperar una sesión fallida — volver a llamar
        # "start" sobre ella no alcanza (ver app.waha.client.WahaClient.restart_session).
        return fragments.failed_panel(WHATSAPP_PATH)
    # Cualquier otro valor no contemplado — mismo tratamiento que "no respondió".
    return fragments.error_panel(WHATSAPP_PATH)


def render_whatsapp_html(*, display_name: str, status_payload: dict | None) -> str:
    body = render_template(
        _TEMPLATES_DIR / "whatsapp.html",
        status_panel_html=RawHTML(render_whatsapp_status_fragment_html(status_payload=status_payload)),
    )
    return render_app_shell(
        display_name=display_name,
        active_view="whatsapp",
        title="WhatsApp",
        sidebar="",
        body=body,
        extra_head_html=RawHTML('<link rel="stylesheet" href="/static/admin/whatsapp.css">'),
        extra_body_html=RawHTML('<script src="/static/admin/whatsapp.js" defer></script>'),
    )
