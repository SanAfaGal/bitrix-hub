"""HTML de la vista de cobertura de ventas por sector — HTML sueltos en
app/admin/templates/coverage.html + app/admin/static/(coverage.css/coverage.js),
sigue el patrón de app/interno/. Fragmentos repetidos (filas, badge, selects)
son macros Jinja en app/admin/jinja_templates/_coverage_fragments.html — este
archivo solo arma los datos y llama a esos macros. Filtros en cascada
(país→departamento→ciudad→zona→sector), texto libre y selección múltiple
corren en el cliente (coverage.js) sobre las filas ya renderizadas; el
filtro por estado (con/sin cobertura) sí recarga la página vía querystring,
porque cambia qué filas llegan del servidor."""
from __future__ import annotations

from pathlib import Path

from app.admin.page import COVERAGE_PATH, render_app_shell
from app.location_catalog.client import Sector
from app.location_catalog.normalize import clean_location_part
from app.shared.html_templates import RawHTML, render_template
from app.shared.jinja_env import get_env

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_JINJA_TEMPLATES_DIR = Path(__file__).parent / "jinja_templates"

_ESTADO_OPTIONS = [
    ("todos", "Todos"),
    ("con_cobertura", "Con cobertura"),
    ("sin_cobertura", "Sin cobertura"),
]

# Orden jerárquico de más amplio a más específico — mismo orden en los
# selects encadenados, en los atributos data-* de cada fila y en las
# columnas de la tabla, para que la relación entre los tres sea obvia.
_CASCADE_LEVELS = [
    ("pais", "País"),
    ("departamento", "Departamento"),
    ("ciudad", "Ciudad"),
    ("zona", "Zona"),
    ("sector", "Sector"),
]


def _fragments():
    return get_env(str(_JINJA_TEMPLATES_DIR)).get_template("_coverage_fragments.html").module


def _shell_fragments():
    """`flash` vive en `_shell_fragments.html` — compartido con `page.py`, no
    se repite acá."""
    return get_env(str(_JINJA_TEMPLATES_DIR)).get_template("_shell_fragments.html").module


def filter_by_estado(sectors: list[Sector], estado: str) -> list[Sector]:
    if estado == "con_cobertura":
        return [s for s in sectors if s.cobertura]
    if estado == "sin_cobertura":
        return [s for s in sectors if not s.cobertura]
    return sectors


def _display(text: str) -> str:
    return clean_location_part(text) if text else ""


def _search_blob(sector: Sector) -> str:
    parts = [sector.sector_code, sector.sector, sector.zona, sector.ciudad, sector.departamento, sector.pais]
    return " ".join(p for p in parts if p).lower()


def _row_context(sector: Sector) -> dict[str, object]:
    displayed = {
        "pais": _display(sector.pais),
        "departamento": _display(sector.departamento),
        "ciudad": _display(sector.ciudad),
        "zona": _display(sector.zona),
        "sector": _display(sector.sector),
    }
    return {
        "sector_code": sector.sector_code,
        "search_blob": _search_blob(sector),
        "cascade": [(level, displayed[level]) for level, _ in _CASCADE_LEVELS],
        "covered": sector.cobertura,
        **displayed,
    }


def render_coverage_html(
    *,
    display_name: str,
    sectors: list[Sector],
    estado: str = "todos",
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    fragments = _fragments()
    rows = [_row_context(sector) for sector in sectors]

    body = render_template(
        _TEMPLATES_DIR / "coverage.html",
        flash_html=RawHTML(_shell_fragments().flash(flash, flash_error)),
        estado=estado,
        cascade_selects_html=RawHTML(fragments.cascade_selects(_CASCADE_LEVELS)),
        estado_select_html=RawHTML(fragments.estado_select(COVERAGE_PATH, _ESTADO_OPTIONS, estado)),
        clear_hidden_attr=RawHTML("" if estado != "todos" else " hidden"),
        table_html=RawHTML(fragments.table(rows)),
    )
    return render_app_shell(
        display_name=display_name,
        active_view="cobertura",
        title="Cobertura de ventas",
        sidebar="",
        body=body,
        extra_head_html=RawHTML('<link rel="stylesheet" href="/static/admin/coverage.css">'),
        extra_body_html=RawHTML('<script src="/static/admin/coverage.js" defer></script>'),
    )
