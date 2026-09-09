from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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


def _sqlite_engine_with_cobertura() -> object:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE cat_mobilia_sectores "
                "(sector_code TEXT, sector TEXT, zona TEXT, ciudad TEXT, departamento TEXT, pais TEXT, "
                "cobertura_ventas INTEGER)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO cat_mobilia_sectores "
                "(sector_code, sector, zona, ciudad, departamento, pais, cobertura_ventas) VALUES "
                "('00081', 'PIEDECUESTA', 'PIEDECUESTA', 'Piedecuesta', 'Santander', 'Colombia', 0), "
                "('41001', 'NEIVA', 'Neiva', 'Neiva', 'Huila', 'Colombia', 1), "
                "('41013', 'HUILA', 'Huila', 'Neiva', 'Huila', 'Colombia', 1)"
            )
        )
    return engine


def _settings_for(view_name: str) -> LocationCatalogSettings:
    return LocationCatalogSettings(
        db_host="", db_port=3306, db_name="", db_user="", db_password="", view_name=view_name
    )


def test_fetch_all_sectores_returns_every_row_without_dedupe(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_cobertura())
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    sectores = client.fetch_all_sectores()

    # 41001 y 41013 comparten ciudad/departamento (mismo display_label que
    # fetch_all_locations dedupe) pero acá son sector_code distintos y deben
    # aparecer los dos, cada uno administrable por separado.
    assert [s.sector_code for s in sectores] == ["41013", "41001", "00081"]
    assert [s.cobertura for s in sectores] == [True, True, False]


def test_fetch_all_sectores_returns_empty_list_when_query_fails(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("tabla_que_no_existe"))

    assert client.fetch_all_sectores() == []


def test_set_cobertura_activates_selected_sectores(monkeypatch) -> None:
    engine = _sqlite_engine_with_cobertura()
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.set_cobertura(["00081"], covered=True) is True

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT cobertura_ventas FROM cat_mobilia_sectores WHERE sector_code = '00081'")
        ).one()
    assert row.cobertura_ventas == 1


def test_set_cobertura_deactivates_selected_sectores(monkeypatch) -> None:
    engine = _sqlite_engine_with_cobertura()
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.set_cobertura(["41001", "41013"], covered=False) is True

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT cobertura_ventas FROM cat_mobilia_sectores WHERE sector_code IN ('41001', '41013')")
        ).all()
    assert all(row.cobertura_ventas == 0 for row in rows)


def test_set_cobertura_with_empty_list_is_a_noop(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.set_cobertura([], covered=True) is True


def test_set_cobertura_returns_false_when_update_fails(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("tabla_que_no_existe"))

    assert client.set_cobertura(["00081"], covered=True) is False


def test_get_sector_coverage_returns_true_for_covered_sector(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_cobertura())
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.get_sector_coverage("41001") is True


def test_get_sector_coverage_returns_false_for_uncovered_sector(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_cobertura())
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.get_sector_coverage("00081") is False


def test_get_sector_coverage_returns_none_for_unknown_sector_code(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", _sqlite_engine_with_cobertura())
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("cat_mobilia_sectores"))

    assert client.get_sector_coverage("no-existe") is None


def test_get_sector_coverage_returns_none_when_query_fails(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))
    monkeypatch.setattr(client, "load_location_catalog_settings", lambda: _settings_for("tabla_que_no_existe"))

    assert client.get_sector_coverage("00081") is None


def test_is_reachable_returns_true_when_connection_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(db, "engine", create_engine("sqlite:///:memory:", future=True))

    assert client.is_reachable() is True


def test_is_reachable_returns_false_when_connection_fails(monkeypatch) -> None:
    broken_engine = create_engine("sqlite:///:memory:", future=True)
    broken_engine.dispose()

    def _raise(*_a, **_k):
        raise SQLAlchemyError("sin conexión")

    monkeypatch.setattr(db, "engine", broken_engine)
    monkeypatch.setattr(broken_engine, "connect", _raise)

    assert client.is_reachable() is False

    assert client.set_cobertura(["00081"], covered=True) is False
