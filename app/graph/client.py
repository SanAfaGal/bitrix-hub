"""Cliente HTTP para Microsoft Graph (client credentials, app-only)."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests
from requests import Session

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


class GraphClient:
    """Encapsula la autenticación app-only y la lectura del inbox vía Microsoft Graph."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, mailbox: str) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.mailbox = mailbox
        self.session = Session()
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_reachable(self) -> bool:
        """Chequeo liviano de disponibilidad (ver GET /health/integrations en app/main.py).

        Solo confirma que se puede autenticar (obtener token OAuth) contra
        Graph — no hace una llamada real al inbox. Cubre la falla más común
        (secreto vencido/rotado, app registration deshabilitada) sin el
        costo de traer mensajes. Nunca lanza: loguea y devuelve False."""
        try:
            self._get_token()
            return True
        except RuntimeError:
            logger.warning("Microsoft Graph no está respondiendo (chequeo de disponibilidad)")
            return False

    def list_messages(self, sender: str | None = None, top: int = 25) -> list[dict[str, Any]]:
        """Lista mensajes del Inbox de la bandeja configurada, opcionalmente filtrados por remitente.

        El filtro por remitente se aplica acá, no vía `$filter` de Graph:
        combinar `$filter=from/emailAddress/address eq '...'` con
        `$orderby=receivedDateTime desc` en mensajes hace que Graph responda
        400 `InefficientFilter` ("The restriction or sort order is too
        complex for this operation") — confirmado a mano contra la API real.
        En vez de perder el orden por fecha (la alternativa sin `$orderby`
        no garantiza traer los más recientes), se trae un lote más grande ya
        ordenado y se filtra en Python.
        """
        fetch_top = top
        if sender:
            fetch_top = min(max(top * 5, 50), 999)

        params: dict[str, Any] = {
            "$select": "subject,from,receivedDateTime,id,body",
            "$top": fetch_top,
            "$orderby": "receivedDateTime desc",
        }

        url = f"{GRAPH_BASE_URL}/users/{self.mailbox}/mailFolders/Inbox/messages"
        try:
            response = self.session.get(
                url,
                headers={
                    "Authorization": f"Bearer {self._get_token()}",
                    # Fuerza texto plano en body.content — sin esto Graph
                    # devuelve HTML, que habría que parsear aparte.
                    "Prefer": 'outlook.body-content-type="text"',
                },
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Fallo al consultar el inbox de Graph (mailbox=%s)", self.mailbox)
            return []

        messages = response.json().get("value", [])
        if not sender:
            return messages

        sender_lower = sender.strip().lower()
        matches = [
            m for m in messages
            if ((m.get("from") or {}).get("emailAddress") or {}).get("address", "").lower() == sender_lower
        ]
        return matches[:top]

    def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": GRAPH_SCOPE,
        }

        try:
            response = self.session.post(token_url, data=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("No se pudo obtener el token de Microsoft Graph: %s", exc)
            raise RuntimeError("No se pudo autenticar contra Microsoft Graph") from exc

        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            logger.error("Respuesta de Microsoft Graph sin access_token: %s", token_data)
            raise RuntimeError("No se pudo autenticar contra Microsoft Graph")

        self._token = access_token
        # Renueva un poco antes de que expire de verdad, para no correr con un token al filo.
        self._token_expires_at = time.monotonic() + max(int(token_data.get("expires_in", 0)) - 60, 0)
        return self._token
