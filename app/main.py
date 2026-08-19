"""API FastAPI: punto único de webhooks de Bitrix hacia integraciones externas."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.flows.router import router as flows_router
from app.waha.router import router as waha_router
from app.xposure.router import router as xposure_router

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

tags_metadata = [
    {"name": "Salud", "description": "Chequeo de disponibilidad del servicio."},
    {
        "name": "Xposure",
        "description": "Consulta de inmuebles en el portal Xposure por número de matrícula (tax roll).",
    },
    {
        "name": "Bitrix Webhooks",
        "description": (
            "Endpoints que reciben eventos de Bitrix y disparan flujos — "
            "posiblemente multi-integración (ej. Bitrix + Xposure + Waha). "
            "Ver app/flows/README.md para el patrón."
        ),
    },
    {
        "name": "Waha",
        "description": (
            "Envío de WhatsApp vía Waha. Todavía sin flujo de negocio real "
            "cableado — ver app/flows/README.md."
        ),
    },
]

app = FastAPI(
    title="Bitrix Integration Hub",
    version="0.1.0",
    description=(
        "Recibe webhooks de Bitrix y dispara acciones en sistemas externos: "
        "consulta de inmuebles en Xposure y envío de WhatsApp vía Waha. "
        "Cada integración vive en su propio paquete bajo `app/` — ver el "
        "README del repo para el patrón de cómo agregar una integración nueva."
    ),
    openapi_tags=tags_metadata,
)

app.include_router(xposure_router)
app.include_router(flows_router)
app.include_router(waha_router)


@app.get("/health", tags=["Salud"], summary="Estado del servicio")
def health() -> dict[str, str]:
    """Verifica que la API esté corriendo."""
    return {"status": "ok"}
