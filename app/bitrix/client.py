"""Cliente HTTP mínimo para la REST API de Bitrix24 (vía webhook entrante).

Implementa `app.crm.protocol.CrmClient`: expone tanto las llamadas HTTP
crudas (`get_deal`, `get_contact`, `update_deal`) como los métodos de
negocio (`get_matricula`, `set_duplicado_status`, etc.) que traducen esas
llamadas a los campos custom (`UF_CRM_*`) y convenciones específicas de
esta instancia de Bitrix. Todo ese conocimiento vive en `BitrixClient` — el
resto del hub solo conoce `CrmClient`.

`BitrixClient` se compone de cuatro mixins (límite de 500 líneas del repo,
`client.py` ya pasaba de 650): `client_deals.py` (deal, crudo y de negocio),
`client_contacts.py` (contacto, búsqueda y creación), `client_files.py`
(timeline y Drive) y `client_sectors.py` (Smart Process "Sectores",
sincronizado desde Mobilia DWH — ver `app/location_catalog/sector_sync.py`).
`app/bitrix/_shared.py` tiene los helpers privados que comparten (nunca se
importa fuera de este paquete).
"""
from __future__ import annotations

import logging

import requests

from app.bitrix._shared import REQUEST_TIMEOUT
from app.bitrix.client_contacts import ContactsMixin
from app.bitrix.client_deals import DealsMixin
from app.bitrix.client_files import FilesMixin
from app.bitrix.client_sectors import SectorsMixin

logger = logging.getLogger(__name__)


class BitrixClient(DealsMixin, ContactsMixin, FilesMixin, SectorsMixin):
    """Encapsula las llamadas a la REST API de Bitrix."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url.rstrip("/") + "/"
        self.session = requests.Session()

    def is_reachable(self) -> bool:
        """Chequeo liviano de disponibilidad (ver GET /health/integrations en app/main.py).

        Llama a `profile.json`, el método más barato de la REST API de
        Bitrix (perfil del usuario dueño del webhook, sin parámetros ni
        efectos secundarios) — a diferencia del resto de esta clase, nunca
        lanza: loguea y devuelve False, porque alimenta un indicador de
        estado, no un flujo que deba fallar."""
        try:
            response = self.session.get(f"{self.webhook_url}profile.json", timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            logger.warning("Bitrix no está respondiendo (chequeo de disponibilidad)")
            return False
