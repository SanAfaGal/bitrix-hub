from __future__ import annotations

from fastapi.testclient import TestClient

from app.admin.deps import require_login
from app.graph.deps import get_graph_client
from app.main import app
from tests.fakes import FakeCrmClient

client = TestClient(app)

_VENDER_MESSAGE = {
    "id": "msg-1",
    "subject": "Nuevo envío: Formulario Servicio: Quiero Vender",
    "body": {
        "content": """Nombre Completo
Diana Herrera
Correo Electrónico
dianahg.seo@gmail.com
Teléfono
+573217549875
Zona / Sector / Barrio
El Poblado
Tipo de Inmueble
apartamento
Valor Estimado
6500000
Mensaje
Busco asesoría para vender.
ID de Seguimiento: 8974dd3b-d4e8-4e5f-8e29-420b8d26665c
"""
    },
}


class _FakeGraphClient:
    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages

    def list_messages(self, sender: str | None = None, top: int = 25) -> list[dict]:
        return self._messages


def test_inbox_requires_login() -> None:
    app.dependency_overrides[get_graph_client] = lambda: _FakeGraphClient([])
    try:
        response = client.get("/graph/inbox", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_graph_client, None)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_process_leads_requires_login() -> None:
    app.dependency_overrides[get_graph_client] = lambda: _FakeGraphClient([])
    try:
        response = client.post("/graph/process-leads", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_graph_client, None)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_process_leads_creates_deal_and_dedupes_on_second_call(monkeypatch, tmp_path) -> None:
    fake_crm = FakeCrmClient()
    monkeypatch.setattr("app.graph.router.get_crm_client", lambda: fake_crm)
    app.dependency_overrides[get_graph_client] = lambda: _FakeGraphClient([_VENDER_MESSAGE])
    app.dependency_overrides[require_login] = lambda: "test-admin"

    processed: dict[str, dict] = {}
    monkeypatch.setattr(
        "app.graph.router.processed_store.get_processed", lambda message_id, **kw: processed.get(message_id)
    )

    def fake_mark_processed(message_id, *, status, deal_id=None, detail=None, **kw):
        processed[message_id] = {"status": status, "deal_id": deal_id, "detail": detail}

    monkeypatch.setattr("app.graph.router.processed_store.mark_processed", fake_mark_processed)

    try:
        first = client.post("/graph/process-leads")
        second = client.post("/graph/process-leads")
    finally:
        app.dependency_overrides.pop(get_graph_client, None)
        app.dependency_overrides.pop(require_login, None)

    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 1
    assert len(body["created"]) == 1
    assert body["created"][0]["deal_id"] is not None

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["total"] == 1
    assert second_body["created"] == []
    assert second_body["skipped"] == []
    assert second_body["errors"] == []
    assert len(second_body["already_processed"]) == 1
    assert second_body["already_processed"][0]["message_id"] == "msg-1"
