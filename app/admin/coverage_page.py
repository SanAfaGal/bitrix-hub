"""HTML de la vista de cobertura de ventas por sector — HTML sueltos en
app/admin/templates/coverage.html + app/admin/static/(coverage.css/coverage.js),
sigue el patrón de app/interno/. Filtros en cascada (país→departamento→ciudad→
zona→sector), texto libre y selección múltiple corren en el cliente
(coverage.js) sobre las filas ya renderizadas; el filtro por estado
(con/sin cobertura) sí recarga la página vía querystring, porque cambia qué
filas llegan del servidor."""
from __future__ import annotations

from html import escape
from pathlib import Path

from app.admin.page import COVERAGE_PATH, render_app_shell
from app.location_catalog.client import Sector
from app.location_catalog.normalize import clean_location_part
from app.shared.html_templates import RawHTML, render_template

_TEMPLATES_DIR = Path(__file__).parent / "templates"

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
    return escape(" ".join(p for p in parts if p).lower())


def _badge(covered: bool) -> str:
    if covered:
        return '<span class="coverage-badge coverage-badge--on">Con cobertura</span>'
    return '<span class="coverage-badge coverage-badge--off">Sin cobertura</span>'


def _row_html(sector: Sector) -> str:
    displayed = {
        "pais": _display(sector.pais),
        "departamento": _display(sector.departamento),
        "ciudad": _display(sector.ciudad),
        "zona": _display(sector.zona),
        "sector": _display(sector.sector),
    }
    cascade_attrs = " ".join(f'data-{level}="{escape(displayed[level])}"' for level, _ in _CASCADE_LEVELS)
    return f"""
      <tr data-coverage-row data-search="{_search_blob(sector)}" {cascade_attrs}>
        <td class="coverage-table__checkbox-col">
          <input type="checkbox" name="sector_code" value="{escape(sector.sector_code)}" data-coverage-checkbox>
        </td>
        <td class="coverage-table__muted">{escape(sector.sector_code)}</td>
        <td>{escape(displayed["sector"])}</td>
        <td class="coverage-table__muted">{escape(displayed["zona"])}</td>
        <td>{escape(displayed["ciudad"])}</td>
        <td class="coverage-table__muted">{escape(displayed["departamento"])}</td>
        <td>{escape(displayed["pais"])}</td>
        <td>{_badge(sector.cobertura)}</td>
      </tr>
    """


def _estado_select_html(estado: str) -> str:
    # Sin <form> propio a propósito: este select vive dentro del <form> de batch
    # (para quedar junto al resto de la barra de filtros) y un <form> anidado
    # dentro de otro es HTML inválido — el navegador ignora el de adentro y el
    # select terminaría enviándose con el form de batch (POST) en vez de
    # recargar la lista. Navega por JS en su lugar.
    options = "".join(
        f'<option value="{value}"{" selected" if value == estado else ""}>{label}</option>'
        for value, label in _ESTADO_OPTIONS
    )
    return (
        f'<select class="coverage-select" data-coverage-estado '
        f"onchange=\"window.location.href='{COVERAGE_PATH}?estado=' + encodeURIComponent(this.value)\">"
        f"{options}</select>"
    )


def _cascade_selects_html() -> str:
    """Los <option> reales los arma coverage_script.py en el cliente a partir
    de las filas ya renderizadas — acá solo va el placeholder "Todos", para
    no duplicar la lista de valores distintos en Python y en JS."""
    selects = []
    for level, label in _CASCADE_LEVELS:
        selects.append(
            f'<select class="coverage-select" data-coverage-cascade="{level}" title="{label}">'
            f'<option value="">{label}: todos</option>'
            f"</select>"
        )
    return '<div class="coverage-toolbar__cascade">' + "".join(selects) + "</div>"


def render_coverage_html(
    *,
    display_name: str,
    sectors: list[Sector],
    estado: str = "todos",
    flash: str | None = None,
    flash_error: bool = False,
) -> str:
    flash_html = ""
    if flash:
        kind = "alert--error" if flash_error else "alert--info"
        flash_html = f'<div class="alert {kind}">{escape(flash)}</div>'

    if not sectors:
        table_html = '<div class="coverage-empty">No hay sectores para mostrar con este filtro.</div>'
    else:
        rows_html = "".join(_row_html(sector) for sector in sectors)
        table_html = f"""
        <div class="coverage-table-wrap">
          <table class="coverage-table" data-coverage-table>
            <thead>
              <tr>
                <th class="coverage-table__checkbox-col">
                  <input type="checkbox" data-coverage-select-all title="Seleccionar todo lo visible">
                </th>
                <th>Código</th>
                <th>Sector</th>
                <th>Zona</th>
                <th>Ciudad</th>
                <th>Departamento</th>
                <th>País</th>
                <th>Cobertura</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        """

    body = render_template(
        _TEMPLATES_DIR / "coverage.html",
        flash_html=RawHTML(flash_html),
        estado=estado,
        cascade_selects_html=RawHTML(_cascade_selects_html()),
        estado_select_html=RawHTML(_estado_select_html(estado)),
        clear_hidden_attr=RawHTML("" if estado != "todos" else " hidden"),
        table_html=RawHTML(table_html),
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
