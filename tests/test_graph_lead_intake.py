from __future__ import annotations

from app.flows.graph_lead_intake import process
from tests.fakes import FakeCrmClient

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


def test_creates_contact_and_deal_for_vender_lead() -> None:
    crm = FakeCrmClient()

    result = process(_VENDER_MESSAGE, crm)

    assert result.status == "created"
    assert result.deal_id is not None
    assert crm.find_or_create_property_seller_contact_calls[-1] == (
        "573217549875",
        None,
        "Diana Herrera",
        "dianahg.seo@gmail.com",
    )
    assert crm.find_or_create_property_seller_deal_calls[-1][1] == "Consignación Web - Diana Herrera"
    listing = crm.property_listings[result.deal_id]
    assert listing.property_type == "Apartamento"
    assert listing.sector_zone_city == "El Poblado"
    assert listing.expected_sale_price == 6500000
    assert crm.comments and "8974dd3b" in crm.comments[-1][1]


def test_skips_non_vender_service_type() -> None:
    crm = FakeCrmClient()
    message = dict(_VENDER_MESSAGE, subject="Nuevo envío: Formulario Servicio: Quiero Comprar")

    result = process(message, crm)

    assert result.status == "skipped"
    assert result.deal_id is None
    assert crm.find_or_create_property_seller_contact_calls == []


def test_missing_phone_yields_error_without_touching_crm() -> None:
    crm = FakeCrmClient()
    message = dict(
        _VENDER_MESSAGE,
        body={"content": _VENDER_MESSAGE["body"]["content"].replace("+573217549875", "123")},
    )

    result = process(message, crm)

    assert result.status == "error"
    assert result.reason == "sin_telefono"
    assert crm.find_or_create_property_seller_contact_calls == []
