# Agregar un CRM nuevo

Si el CRM cambia (o se necesita soportar uno adicional), el resto del hub
(`app/flows/*`, `app/forms/*`, `app/waha/*`) no debería tocarse. Solo hace
falta:

1. Crear `app/<crm>/` con el mismo patrón que `app/bitrix/`: `client.py`
   (HTTP, nunca lanza en fallo de red — retorna `{}`/`None`),
   `settings.py` (env vars), `deps.py`.
2. Implementar en `client.py` todos los métodos de `CrmClient`
   (`app/crm/protocol.py`) — es un `Protocol`, no hace falta heredar de
   él, solo tener los mismos métodos con la misma firma. Ahí es donde
   vive todo el conocimiento específico del CRM nuevo: nombres de campos
   custom, IDs de picklist, forma del contacto, etc.
3. Agregar un `elif` en `get_crm_client()` (`app/crm/deps.py`) para el
   valor nuevo de `CRM_PROVIDER` (ver `app/crm/settings.py`). Setear
   `CRM_PROVIDER=<nombre>` en `.env` activa ese CRM sin tocar código.

Las rutas de webhook (`app/flows/router.py`) siguen siendo específicas del
CRM que las dispara — eso es intencional, ver README.md raíz ("Cómo
agregar una integración nueva"). Lo que cambia de CRM es qué hay *detrás*
de esas rutas, no la forma de los webhooks en sí.
