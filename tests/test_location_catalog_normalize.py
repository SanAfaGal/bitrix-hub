from __future__ import annotations

from app.location_catalog.normalize import (
    _strip_trailing_word_block,
    build_location_label,
    clean_location_part,
    dedupe_parts,
    normalize_key,
)


def test_normalize_key_strips_accents_case_and_whitespace() -> None:
    assert normalize_key("  Bogotá D.C.  ") == "bogota d.c."


def test_clean_location_part_title_cases_and_lowercases_articles() -> None:
    assert clean_location_part("DISTRITO CAPITAL DE BOGOTA") == "Distrito Capital de Bogota"


def test_clean_location_part_keeps_article_uppercase_when_first_word() -> None:
    assert clean_location_part("LA ESTRELLA") == "La Estrella"


def test_dedupe_parts_removes_repeats_anywhere_keeping_last_occurrence() -> None:
    assert dedupe_parts(["Usa", "Usa", "Usa", "Estados Unidos"]) == ["Usa", "Estados Unidos"]


def test_dedupe_parts_prefers_the_later_occurrences_text_on_conflicting_casing() -> None:
    # Cuando el mismo valor aparece con distinta forma (mayúsculas vs. bien
    # escrito), se queda con la de la última aparición.
    assert dedupe_parts(["HUILA", "Huila"]) == ["Huila"]


def test_build_location_label_dedupes_and_joins() -> None:
    assert build_location_label("SALAMINA", "SALAMINA", "Salamina", "Caldas", "Colombia") == "Salamina, Caldas, Colombia"


def test_build_location_label_skips_blank_parts() -> None:
    assert (
        build_location_label("El Poblado", "", "Medellín", "Antioquia", "Colombia")
        == "El Poblado, Medellín, Antioquia, Colombia"
    )


def test_build_location_label_keeps_city_before_department_when_sector_repeats_department_name() -> None:
    # Caso real: sector_code 41013 en cat_mobilia_sectores — sector="HUILA" y
    # zona="Huila" repiten el nombre del departamento como relleno (no tiene
    # subdivisión propia); ciudad="Neiva" y departamento="Huila" ya vienen en
    # el orden correcto. Sin el fix, el relleno de sector/zona se adelantaba
    # y el resultado quedaba "Huila, Neiva" (departamento antes que ciudad).
    assert build_location_label("HUILA", "Huila", "Neiva", "Huila", "Colombia") == "Neiva, Huila, Colombia"


def test_build_location_label_drops_sector_that_only_repeats_the_country_name() -> None:
    # Caso real: sector_code 2156 en cat_mobilia_sectores — sector="ESTADOS
    # UNIDOS" repite el país directamente (mal cargado en sector en vez de
    # dejarlo vacío), y zona/ciudad/departamento repiten "Whashington". Con
    # país incluido en el pipeline, ambos rellenos se quitan/deduplican.
    assert (
        build_location_label("ESTADOS UNIDOS", "Whashington", "Whashington", "WHASHINGTON", "estados unidos")
        == "Whashington, Estados Unidos"
    )


def test_strip_trailing_word_block_removes_trailing_city_name() -> None:
    assert _strip_trailing_word_block("San Gabriel Itagui", "itagui") == "San Gabriel"


def test_strip_trailing_word_block_removes_multi_word_block() -> None:
    assert _strip_trailing_word_block("Distrito Norte de Santander", "norte de santander") == "Distrito"


def test_strip_trailing_word_block_does_not_touch_partial_word_matches() -> None:
    # "Itagui" no debe tocar una palabra que solo lo contiene como substring
    # (ej. un hipotético "Itaguicito") — solo bloques de palabra completos.
    assert _strip_trailing_word_block("Barrio Itaguicito", "itagui") == "Barrio Itaguicito"


def test_strip_trailing_word_block_does_not_touch_leading_match() -> None:
    # Caso real: sector "San Pedro de los Milagros" con ciudad "San pedro" —
    # coincide al INICIO, no al final, así que no es relleno, es un nombre
    # propio distinto y no se toca.
    assert (
        _strip_trailing_word_block("San Pedro de los Milagros", "san pedro")
        == "San Pedro de los Milagros"
    )


def test_build_location_label_removes_city_name_embedded_in_sector() -> None:
    # Caso real: sector_code 105 en cat_mobilia_sectores — sector="San
    # Gabriel Itagui" y zona="Itagui" repiten el nombre de la ciudad.
    assert (
        build_location_label("San Gabriel Itagui", "Itagui", "Itagui", "Antioquia", "Colombia")
        == "San Gabriel, Itagui, Antioquia, Colombia"
    )


def test_build_location_label_removes_city_and_department_names_embedded_in_sector() -> None:
    # Caso real: sector_code 0981 en cat_mobilia_sectores — sector="IPIALES
    # NARIÑO" concatena ciudad y departamento; zona="Ipiales" repite la ciudad.
    assert (
        build_location_label("IPIALES NARIÑO", "Ipiales", "Ipiales", "Nariño", "Colombia")
        == "Ipiales, Nariño, Colombia"
    )


def test_build_location_label_keeps_sector_when_city_name_is_a_prefix_not_a_suffix() -> None:
    # Caso real: sector_code 00083 en cat_mobilia_sectores — sector="SAN
    # PEDRO DE LOS MILAGROS" con ciudad="San pedro": "San pedro" es el
    # inicio de un nombre propio más largo, no relleno pegado a la coma —
    # no se debe tocar.
    assert (
        build_location_label(
            "SAN PEDRO DE LOS MILAGROS", "San pedro de los milagros", "San pedro", "Antioquia", "Colombia"
        )
        == "San Pedro de los Milagros, San Pedro, Antioquia, Colombia"
    )
