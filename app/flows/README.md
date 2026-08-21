# Flujos encadenados (multi-integración)

Un flujo que orquesta más de una integración (ej. "cliente creado → se
consulta Xposure → según el resultado se le notifica por WhatsApp") vive
acá, no dentro del paquete de una integración individual (`waha/`,
`mobilia/`, etc.) — esos paquetes no se importan entre sí.

Cada flujo es un módulo con una función que recibe los clientes ya
construidos (inyección explícita, no imports cruzados entre paquetes de
integración) y ejecuta la secuencia. El cliente de CRM siempre se recibe
tipado como `app.crm.protocol.CrmClient`, nunca como `BitrixClient` — así
un flujo no sabe (ni necesita saber) qué CRM hay detrás.

Forma esperada:

```python
# app/flows/cliente_creado.py
from app.crm.protocol import CrmClient
from app.waha.client import WahaClient
# from app.xposure.client import XposureClient  (cuando exista en el hub)


def process(
    deal_id: str,
    crm_client: CrmClient,
    waha_client: WahaClient,
    # xposure_client: XposureClient,
) -> dict:
    deal = crm_client.get_deal(deal_id)
    # resultado = xposure_client.search_property(...)
    # if resultado.exists: waha_client.send_text(...)
    ...
```

El endpoint correspondiente vive en `app/flows/router.py` (las rutas
mismas siguen siendo específicas del CRM que las dispara, ver README.md
raíz), arma los clientes vía `app.crm.deps.get_crm_client()` (y uno por
cada otra integración involucrada) y llama a `process(...)`. Cada
integración sigue siendo testeable de forma aislada (mock de su propio
cliente); el flujo se testea con todos los clientes mockeados usando
`tests/fakes.py::FakeCrmClient`, igual que `MLS/tests/test_deal_event.py`.

Flujos reales existentes: `deal_duplicado.py` (CRM + Xposure),
`notify_contact.py` y `welcome_authorization.py` (CRM + Waha).
