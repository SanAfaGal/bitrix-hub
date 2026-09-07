from __future__ import annotations

from app.graph.lead_email_parser import parse_lead_email

_VENDER_SUBJECT = "Nuevo envío: Formulario Servicio: Quiero Vender"
_VENDER_BODY = """NOTIFICACIÓN DE FORMULARIO
Formulario Servicio: Quiero Vender

Se ha recibido un nuevo envío desde el sitio web:

Nombre Completo
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
Hola Busco asesoría para alquilar (con o sin muebles) o vender apartamento en el Poblado. Por favor contáctame.
Acepta Política
on
ID de Seguimiento: 8974dd3b-d4e8-4e5f-8e29-420b8d26665c
"""


def test_parses_full_vender_email() -> None:
    lead = parse_lead_email(_VENDER_SUBJECT, _VENDER_BODY)

    assert lead.service_type == "vender"
    assert lead.nombre == "Diana Herrera"
    assert lead.correo == "dianahg.seo@gmail.com"
    assert lead.telefono == "573217549875"
    assert lead.zona == "El Poblado"
    assert lead.tipo_inmueble == "Apartamento"
    assert lead.valor_estimado == 6500000
    assert lead.mensaje.startswith("Hola Busco asesoría")
    assert lead.tracking_id == "8974dd3b-d4e8-4e5f-8e29-420b8d26665c"


def test_detects_comprar_service_type() -> None:
    lead = parse_lead_email("Nuevo envío: Formulario Servicio: Quiero Comprar", _VENDER_BODY)
    assert lead.service_type == "comprar"


def test_detects_arrendar_service_type() -> None:
    lead = parse_lead_email("Nuevo envío: Formulario Servicio: Quiero Arrendar", _VENDER_BODY)
    assert lead.service_type == "arrendar"


def test_unrecognized_subject_yields_none_service_type() -> None:
    lead = parse_lead_email("Asunto random sin tipo de servicio", _VENDER_BODY)
    assert lead.service_type is None


def test_missing_field_stays_none_without_breaking_others() -> None:
    body_without_email = _VENDER_BODY.replace("Correo Electrónico\ndianahg.seo@gmail.com\n", "")

    lead = parse_lead_email(_VENDER_SUBJECT, body_without_email)

    assert lead.correo is None
    assert lead.nombre == "Diana Herrera"
    assert lead.telefono == "573217549875"


def test_price_with_thousands_separators_is_sanitized_to_int() -> None:
    body = _VENDER_BODY.replace("6500000", "$6.500.000")
    lead = parse_lead_email(_VENDER_SUBJECT, body)
    assert lead.valor_estimado == 6500000


def test_invalid_phone_yields_none() -> None:
    body = _VENDER_BODY.replace("+573217549875", "123")
    lead = parse_lead_email(_VENDER_SUBJECT, body)
    assert lead.telefono is None


def test_property_type_not_in_catalog_is_kept_capitalized() -> None:
    body = _VENDER_BODY.replace("apartamento", "oficina compartida")
    lead = parse_lead_email(_VENDER_SUBJECT, body)
    assert lead.tipo_inmueble == "Oficina compartida"
