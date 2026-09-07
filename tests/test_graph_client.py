from __future__ import annotations

import requests

from app.graph.client import GraphClient


class FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200) -> None:
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}", response=self)

    def json(self) -> dict:
        return self._json_data


def _client() -> GraphClient:
    client = GraphClient("tenant", "client-id", "secret", "gestionventas@albertoalvarez.com")
    client._token = "fake-token"
    client._token_expires_at = float("inf")
    return client


def test_list_messages_without_sender_does_not_filter(monkeypatch) -> None:
    client = _client()
    raw = [{"id": "1", "from": {"emailAddress": {"address": "a@x.com"}}}]

    def fake_get(url, headers, params, timeout):
        assert "$filter" not in params
        return FakeResponse({"value": raw})

    monkeypatch.setattr(client.session, "get", fake_get)

    assert client.list_messages(top=5) == raw


def test_list_messages_filters_by_sender_client_side(monkeypatch) -> None:
    client = _client()
    raw = [
        {"id": "1", "from": {"emailAddress": {"address": "comunicados@albertoalvarez.com"}}},
        {"id": "2", "from": {"emailAddress": {"address": "otro@dominio.com"}}},
        {"id": "3", "from": {"emailAddress": {"address": "Comunicados@AlbertoAlvarez.com"}}},
    ]

    def fake_get(url, headers, params, timeout):
        # No manda $filter a Graph — evita el 400 InefficientFilter real
        # (from/emailAddress/address eq combinado con $orderby).
        assert "$filter" not in params
        assert params["$top"] == 50  # min(max(top*5, 50), 999) con top=5
        return FakeResponse({"value": raw})

    monkeypatch.setattr(client.session, "get", fake_get)

    result = client.list_messages(sender="comunicados@albertoalvarez.com", top=5)

    assert [m["id"] for m in result] == ["1", "3"]


def test_list_messages_sender_filter_respects_top_after_filtering(monkeypatch) -> None:
    client = _client()
    raw = [
        {"id": str(i), "from": {"emailAddress": {"address": "comunicados@albertoalvarez.com"}}} for i in range(10)
    ]

    def fake_get(url, headers, params, timeout):
        return FakeResponse({"value": raw})

    monkeypatch.setattr(client.session, "get", fake_get)

    result = client.list_messages(sender="comunicados@albertoalvarez.com", top=3)

    assert len(result) == 3


def test_list_messages_returns_empty_list_on_request_error(monkeypatch) -> None:
    client = _client()

    def fake_get(url, headers, params, timeout):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(client.session, "get", fake_get)

    assert client.list_messages(sender="comunicados@albertoalvarez.com") == []
