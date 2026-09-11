"""Flujo: formulario interno de creación de lead -> contacto + deal en Bitrix.

Combina app.crm (crear/actualizar contacto+deal) con app.forms.coverage (la
única validación con matiz interno/público, ver su docstring) — vive en
app/flows/ por el mismo motivo que welcome_authorization.py: compone más de
una responsabilidad, aunque acá solo toque un integración (CRM) además de la
regla de cobertura.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.crm.protocol import CrmClient, PropertyListing
from app.forms.coverage import check_coverage
from app.interno.models import NuevoLeadPayload


@dataclass(frozen=True)
class NuevoLeadResult:
    ok: bool
    deal_id: str | None
    contact_id: str | None
    blocked: bool
    message: str | None
    used_coverage_exception: bool


def process_nuevo_lead(payload: NuevoLeadPayload, crm_client: CrmClient, staff_email: str) -> NuevoLeadResult:
    coverage = check_coverage(
        payload.location_sector_code, is_internal=True, override=payload.coverage_override
    )
    if coverage.blocked:
        return NuevoLeadResult(
            ok=False, deal_id=None, contact_id=None, blocked=True, message=coverage.message, used_coverage_exception=False
        )

    contact_id = crm_client.find_or_create_property_seller_contact(
        payload.owner_phone,
        display_name=payload.interested_party,
        email=payload.email,
    )
    if not contact_id:
        return NuevoLeadResult(
            ok=False,
            deal_id=None,
            contact_id=None,
            blocked=False,
            message="No se pudo crear el contacto en Bitrix.",
            used_coverage_exception=coverage.used_exception,
        )

    deal_id = crm_client.find_or_create_property_seller_deal(
        contact_id, title=f"Consignación - {payload.interested_party}", source="interno"
    )
    if not deal_id:
        return NuevoLeadResult(
            ok=False,
            deal_id=None,
            contact_id=contact_id,
            blocked=False,
            message="No se pudo crear el deal en Bitrix.",
            used_coverage_exception=coverage.used_exception,
        )

    crm_client.update_property_listing(
        deal_id,
        PropertyListing(
            property_type=payload.property_type,
            address=payload.address,
            sector_zone_city=payload.location,
            expected_sale_price=payload.sale_price or None,
        ),
    )

    if coverage.used_exception:
        crm_client.add_comment(
            deal_id,
            f"Continuó fuera de cobertura (sector {payload.location_sector_code}) — "
            f"autorizado por {staff_email} el {datetime.now().strftime('%Y-%m-%d %H:%M')}.",
        )

    return NuevoLeadResult(
        ok=True, deal_id=deal_id, contact_id=contact_id, blocked=False, message=None, used_coverage_exception=coverage.used_exception
    )
