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

import requests

from app.bitrix.client_contacts import ContactsMixin
from app.bitrix.client_deals import DealsMixin
from app.bitrix.client_files import FilesMixin
from app.bitrix.client_sectors import SectorsMixin


class BitrixClient(DealsMixin, ContactsMixin, FilesMixin, SectorsMixin):
    """Encapsula las llamadas a la REST API de Bitrix."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url.rstrip("/") + "/"
        self.session = requests.Session()
