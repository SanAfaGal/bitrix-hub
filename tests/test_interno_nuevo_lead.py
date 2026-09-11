from __future__ import annotations

import app.flows.interno_nuevo_lead as flow_module
from app.flows.interno_nuevo_lead import process_nuevo_lead
from app.interno.models import NuevoLeadPayload
from tests.fakes import FakeCrmClient


def _payload(**overrides) -> NuevoLeadPayload:
    defaults = dict(
        interested_party="Ana Pérez",
        owner_phone="3001112233",
        email=None,
        property_type="Apartamento",
        address="Calle 10 # 20-30",
        location="El Poblado, Medellín",
        location_sector_code="00081",
        sale_price=0,
        coverage_override=False,
        idempotency_token="tok-1",
    )
    defaults.update(overrides)
    return NuevoLeadPayload(**defaults)


def test_process_nuevo_lead_creates_contact_and_deal(monkeypatch) -> None:
    monkeypatch.setattr(flow_module, "check_coverage", lambda *a, **k: _covered_result())
    crm = FakeCrmClient()

    result = process_nuevo_lead(_payload(), crm, "asesor@albertoalvarez.com")

    assert result.ok is True
    assert result.blocked is False
    assert result.deal_id is not None
    assert result.contact_id is not None
    assert crm.property_listings[result.deal_id].address == "CALLE 10 # 20-30"


def test_process_nuevo_lead_blocked_does_not_touch_crm(monkeypatch) -> None:
    from app.forms.coverage import CoverageResult

    monkeypatch.setattr(
        flow_module, "check_coverage", lambda *a, **k: CoverageResult(covered=False, blocked=True, used_exception=False, message="fuera de cobertura")
    )
    crm = FakeCrmClient()

    result = process_nuevo_lead(_payload(), crm, "asesor@albertoalvarez.com")

    assert result.ok is False
    assert result.blocked is True
    assert result.message == "fuera de cobertura"
    assert crm.find_or_create_property_seller_contact_calls == []


def test_process_nuevo_lead_records_coverage_exception_as_comment(monkeypatch) -> None:
    from app.forms.coverage import CoverageResult

    monkeypatch.setattr(
        flow_module, "check_coverage", lambda *a, **k: CoverageResult(covered=False, blocked=False, used_exception=True, message=None)
    )
    crm = FakeCrmClient()

    result = process_nuevo_lead(_payload(), crm, "asesor@albertoalvarez.com")

    assert result.used_coverage_exception is True
    assert len(crm.comments) == 1
    deal_id, comment = crm.comments[0]
    assert deal_id == result.deal_id
    assert "asesor@albertoalvarez.com" in comment
    assert "00081" in comment


def _covered_result():
    from app.forms.coverage import CoverageResult

    return CoverageResult(covered=True, blocked=False, used_exception=False, message=None)
