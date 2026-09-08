"""Cliente HTTP que inicia sesión en Xposure y busca inmuebles."""
from __future__ import annotations

import logging
import re
import threading
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests import Session

from app.xposure.models import PropertySearchResult

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36"
)

# Valores del <select name="status" multiple> del formulario real de búsqueda
# en Xposure (/portal/colombia/MlsFullSearch) — ver search_property() para el
# porqué de filtrar solo por estos dos.
_STATUS_ACTIVO = "1"
_STATUS_OPCIONADO = "3"

# Catálogo {código de oficina en mayúscula -> id interno de Xposure} para
# tax_roll_area_code, ver resolve_area_code() — a nivel de módulo porque
# get_xposure_client() (app/xposure/deps.py) crea un XposureClient nuevo por
# request, así que cachear en la instancia no serviría de nada. Sin TTL: la
# lista de oficinas de registro es esencialmente estática, se recarga sola en
# cada reinicio del proceso.
_area_code_cache: dict[str, str] | None = None
_area_code_cache_lock = threading.Lock()


class XposureClient:
    """Encapsula el login y la búsqueda de inmuebles en el portal Xposure."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-ES,es;q=0.9",
        })

    def login(self) -> None:
        """Autentica la sesión contra el portal de Xposure."""
        response = self._get("/portal/Login")
        response.raise_for_status()

        payload = {
            "username": self.username,
            "password": self.password,
            "cookieEnabled": "true",
            "httpObj": "false",
            "currentContactID": "",
            "currentSearchID": "",
            "presetUsername": "",
            "presetCreaBoard": "",
            "action_url": "",
            "responsive_ui": "true",
            "controlCenterUI": "true",
        }

        response = self._post("/portal/colombia/DoLogin", data=payload, allow_redirects=True)
        response.raise_for_status()

        if "/Login" in response.url:
            raise RuntimeError("No se pudo iniciar sesión en Xposure")

        logger.info("Sesión iniciada")

    def resolve_area_code(self, office_code: str) -> str | None:
        """Traduce un código de oficina en texto (ej. "001N", "50C") al id interno que
        Xposure espera en `tax_roll_area_code` (ver search_property) — NO es el mismo
        texto: `tax_roll_area_code` es el `value` de un `<select>` cuyo id interno no
        tiene relación con el código visible (ej. "001N" -> "2", "50C" -> "36",
        confirmado contra el portal real). Mandar el texto tal cual ahí revienta la
        búsqueda con 500 casi siempre — por eso hay que resolverlo antes.

        Cachea el catálogo completo a nivel de módulo la primera vez que se llama
        (ver `_area_code_cache`). Nunca revienta por fallo de red: si no se pudo
        traer/parsear el catálogo, loguea y devuelve `None` — quien llama debe tratar
        eso igual que "código no encontrado" (ir directo a buscar solo por folio, ver
        `check_matricula_in_xposure`), no como un error fatal.
        """
        global _area_code_cache
        with _area_code_cache_lock:
            if _area_code_cache is None:
                try:
                    response = self._get("/portal/colombia/MlsFullSearch")
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "html.parser")
                    select = soup.find("select", attrs={"name": "tax_roll_area_code"})
                    options = select.find_all("option") if select else []
                    _area_code_cache = {
                        option.get_text(strip=True).upper(): option["value"]
                        for option in options
                        if option.get("value", "").strip()
                    }
                except (requests.exceptions.RequestException, AttributeError, KeyError):
                    logger.exception("No se pudo traer/parsear el catálogo de códigos de oficina de Xposure")
                    return None
            return _area_code_cache.get(office_code.strip().upper())

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None, **_: Any) -> PropertySearchResult:
        """Busca un inmueble por número de matrícula y devuelve el resultado.

        `tax_roll_area_code`, si se da, debe ser el id interno ya resuelto por
        `resolve_area_code()` — no el código de oficina en texto (ver ese método).

        Sin filtrar por `status`, Xposure busca en TODOS los estados del inmueble
        (Activo, Suspendido, Opcionado, Con Contrato, Vendido, Cancelado, Vencido,
        No Aprobado) — el formulario real de búsqueda en el portal trae por
        defecto solo "Activo" (1) y "Opcionado" (3) preseleccionados, que es lo
        único que debería bloquear una nueva Autorización de Corretaje. Sin este
        filtro se encuentran falsos positivos: un inmueble con matrícula X que ya
        se canceló/vendió/venció no debería impedir que alguien la vuelva a
        publicar. Confirmado contra el portal real: la misma búsqueda por folio
        sin este filtro encuentra 1 resultado (un listado Cancelado), con el
        filtro encuentra 0 — igual que la búsqueda manual en el sitio.
        """
        payload = {
            "currentPage": "MlsFullSearch",
            "searchType": "1",
            "listingType": "mls",
            "tax_roll": tax_roll,
            "saveSearchHistory": "true",
            "showMoreFields": "true",
            "status": [_STATUS_ACTIVO, _STATUS_OPCIONADO],
        }
        if tax_roll_area_code:
            payload["tax_roll_area_code"] = tax_roll_area_code

        response = self._post(
            "/portal/colombia/MlsDoFullSearch",
            data=payload,
            headers={"Referer": urljoin(self.base_url, "/portal/colombia/MlsFullSearch")},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        total = self._parse_total_listings(soup)

        if total == 0:
            return PropertySearchResult(
                tax_roll=tax_roll,
                exists=False,
                reason="No se encontraron resultados",
            )

        mls = self._extract_mls(soup)
        if not mls:
            return PropertySearchResult(
                tax_roll=tax_roll,
                exists=True,
                reason="No se encontró MLS en la página",
            )

        detail_url = urljoin(self.base_url, f"/portal/colombia/ViewDetail?mlsForDisplay={mls}")
        return PropertySearchResult(
            tax_roll=tax_roll,
            exists=True,
            mls=mls,
            url=detail_url,
        )

    def _get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.session.get(urljoin(self.base_url, path), timeout=REQUEST_TIMEOUT, **kwargs)

    def _post(self, path: str, data: dict[str, Any] | None = None, **kwargs: Any) -> requests.Response:
        return self.session.post(urljoin(self.base_url, path), data=data, timeout=REQUEST_TIMEOUT, **kwargs)

    @staticmethod
    def _parse_total_listings(soup: BeautifulSoup) -> int:
        total_element = soup.find(id="total-listings-count")
        if not total_element:
            return 0

        text = total_element.get_text(strip=True)
        return int(text) if text.isdigit() else 0

    @staticmethod
    def _extract_mls(soup: BeautifulSoup) -> str | None:
        candidate = soup.find(string=lambda value: value and "MLS#" in value)
        if not candidate:
            return None

        container = candidate.parent
        while container is not None:
            text = container.get_text(" ", strip=True)
            match = re.search(r"MLS#\s*(\S+)", text)
            if match:
                return match.group(1)
            container = container.parent

        return None
