from __future__ import annotations

from sqlalchemy import create_engine, text

from app.location_catalog import client, db
from app.location_catalog.settings import LocationCatalogSettings


def _sqlite_engine_with_locations() -> object:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE cat_mobilia_sectores "
                "(sector_code TEXT, sector TEXT, zona TEXT, ciudad TEXT, departamento TEXT, pais TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO cat_mobilia_sectores (sector_code, sector, zona, ciudad, departamento, pais) VALUES "
                "('00081', 'PIEDECUESTA', 'PIEDECUESTA', 'Piedecuesta', 'Santander', 'Colombia'), "
                "('00062', 'SAN CAYETANO', 'Suba', 'Bogotá', 'Distrito capital de Bogota', 'Colombia')"
            )
        )
    return engine


def test_fetch_all_locations_builds_display_label(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_locations())
    monkeypatch.setattr(
        client,
        "load_location_catalog_settings",
        lambda: LocationCatalogSettings(
            db_host="", db_port=3306, db_name="", db_user="", db_password="",
            view_name="cat_mobilia_sectores",
        ),
    )

    locations = client.fetch_all_locations()

    assert locations == [
        # "PIEDECUESTA" (sector) y "PIEDECUESTA" (zona) y "Piedecuesta" (ciudad)
        # son la misma parte repetida tres veces en la fuente — se dedupe a una.
        client.LocationSuggestion(sector_code="00081", display_label="Piedecuesta, Santander, Colombia"),
        client.LocationSuggestion(
            sector_code="00062", display_label="San Cayetano, Suba, Bogotá, Distrito Capital de Bogota, Colombia"
        ),
    ]


def _sqlite_engine_with_duplicate_display_labels() -> object:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE cat_mobilia_sectores "
                "(sector_code TEXT, sector TEXT, zona TEXT, ciudad TEXT, departamento TEXT, pais TEXT)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO cat_mobilia_sectores (sector_code, sector, zona, ciudad, departamento, pais) VALUES "
                "('41001', 'NEIVA', 'Neiva', 'Neiva', 'Huila', 'Colombia'), "
                "('41013', 'HUILA', 'Huila', 'Neiva', 'Huila', 'Colombia')"
            )
        )
    return engine


def test_fetch_all_locations_dedupes_sector_codes_that_produce_the_same_display_label(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_duplicate_display_labels())
    monkeypatch.setattr(
        client,
        "load_location_catalog_settings",
        lambda: LocationCatalogSettings(
            db_host="", db_port=3306, db_name="", db_user="", db_password="",
            view_name="cat_mobilia_sectores",
        ),
    )

    locations = client.fetch_all_locations()

    # 41001 y 41013 arman el mismo texto "Neiva, Huila, Colombia" tras
    # build_location_label (distintos sector_code, misma ubicación real) —
    # solo se ofrece una vez, se queda con la primera aparición.
    assert locations == [
        client.LocationSuggestion(sector_code="41001", display_label="Neiva, Huila, Colombia")
    ]


def test_fetch_all_locations_returns_empty_list_when_query_fails(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))
    monkeypatch.setattr(
        client,
        "load_location_catalog_settings",
        lambda: LocationCatalogSettings(
            db_host="", db_port=3306, db_name="", db_user="", db_password="",
            view_name="tabla_que_no_existe",
        ),
    )

    assert client.fetch_all_locations() == []
