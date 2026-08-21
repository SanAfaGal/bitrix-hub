"""Fábrica del cliente de CRM activo — único punto a cambiar para swapear de CRM."""
from __future__ import annotations

from app.bitrix.deps import get_bitrix_client
from app.crm.protocol import CrmClient
from app.crm.settings import load_crm_settings

_PROVIDER_BITRIX = "bitrix"


def get_crm_client() -> CrmClient:
    """Crea el cliente del CRM activo, según CRM_PROVIDER.

    Único lugar que necesita cambiar cuando exista un segundo CRM: se
    agrega un `elif` acá — los flows/forms que consumen `CrmClient` no se
    enteran de qué proveedor hay detrás.
    """
    provider = load_crm_settings()

    if provider == _PROVIDER_BITRIX:
        return get_bitrix_client()

    raise RuntimeError(f"CRM_PROVIDER desconocido: {provider!r}")
