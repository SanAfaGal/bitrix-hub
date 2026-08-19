"""Cliente HTTP que inicia sesión en Xposure y busca inmuebles."""
from __future__ import annotations

import logging
import re
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

    def search_property(self, tax_roll: str, tax_roll_area_code: str | None = None, **_: Any) -> PropertySearchResult:
        """Busca un inmueble por número de matrícula y devuelve el resultado."""
        payload = {
            "currentPage": "MlsFullSearch",
            "searchType": "1",
            "listingType": "mls",
            "tax_roll": tax_roll,
            "saveSearchHistory": "true",
            "showMoreFields": "true",
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
