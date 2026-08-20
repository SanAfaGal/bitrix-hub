# Flujos encadenados (multi-integración)

Un flujo que orquesta más de una integración (ej. "cliente creado → se
consulta Xposure → según el resultado se le notifica por WhatsApp") vive
acá, no dentro del paquete de una integración individual (`waha/`,
`mobilia/`, etc.) — esos paquetes no se importan entre sí.

Cada flujo es un módulo con una función que recibe los clientes ya
construidos (inyección explícita, no imports cruzados entre paquetes de
integración) y ejecuta la secuencia, siguiendo el mismo patrón que
`MLS/app/deal_event.py::process_deal_event` ya usa para Bitrix + Xposure.

Forma esperada:

```python
# app/flows/cliente_creado.py
from app.bitrix.client import BitrixClient
from app.waha.client import WahaClient
# from app.xposure.client import XposureClient  (cuando exista en el hub)


def process(
    deal_id: str,
    bitrix_client: BitrixClient,
    waha_client: WahaClient,
    # xposure_client: XposureClient,
) -> dict:
    deal = bitrix_client.get_deal(deal_id)
    # resultado = xposure_client.search_property(...)
    # if resultado.exists: waha_client.send_text(...)
    ...
```

El endpoint correspondiente en `app/main.py` arma los clientes (uno por
integración involucrada) y llama a `process(...)`. Cada integración sigue
siendo testeable de forma aislada (mock de su propio cliente); el flujo se
testea con todos los clientes mockeados, igual que
`MLS/tests/test_deal_event.py`.

Flujos reales existentes: `deal_duplicado.py` (Bitrix + Xposure),
`notify_contact.py` y `welcome_authorization.py` (Bitrix + Waha).
