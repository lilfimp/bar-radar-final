import pytest

from db.database import get_conn
from db.migrate import run as run_migrations
from src.pipeline.import_manual_venues import (
    _group_rows_by_venue,
    _is_wide_format,
    _normalize_rows,
    _read_csv_rows,
    _read_csv_rows_from_url,
    _sniff_delimiter,
    _wide_row_to_long_rows,
    import_venue_group,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.database.db_path", lambda: tmp_path / "test.db")
    run_migrations()


def test_single_menu_venue_creates_one_venue_and_one_menu_source(db):
    rows = [{
        "venue_name": "Solo Bar", "city": "Berlin", "tier": "1",
        "website_url": "https://solobar.de",
        "menu_url": "https://solobar.de/menu.pdf",
        "menu_name": "Cocktail Menu", "menu_category": "COCKTAIL",
        "menu_source_type": "PDF", "is_primary": "true",
    }]
    groups = _group_rows_by_venue(rows)
    assert len(groups) == 1
    (name, city), venue_rows = groups[0]
    result = import_venue_group(name, city, venue_rows)
    assert result["status"] == "OK"

    with get_conn() as conn:
        venue = conn.execute("SELECT status FROM venues WHERE venue_name = ?", ("Solo Bar",)).fetchone()
        sources = conn.execute("SELECT * FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)", ("Solo Bar",)).fetchall()
    assert venue["status"] == "ENRICHED"
    assert len(sources) == 1
    assert sources[0]["menu_category"] == "COCKTAIL"
    assert sources[0]["menu_source_type"] == "PDF"
    assert sources[0]["is_primary"] == 1
    assert sources[0]["discovery_method"] == "manual_curated"
    assert sources[0]["extraction_status"] == "PENDING"


def test_multi_menu_venue_groups_rows_into_one_venue(db):
    rows = [
        {"venue_name": "Multi Bar", "city": "Hamburg", "menu_url": "https://multibar.de/drinks", "menu_name": "Drinks", "is_primary": "true"},
        {"venue_name": "Multi Bar", "city": "Hamburg", "menu_url": "https://multibar.de/wine.pdf", "menu_name": "Wine List"},
        {"venue_name": "Multi Bar", "city": "Hamburg", "menu_url": "https://multibar.de/happy-hour", "menu_name": "Happy Hour"},
    ]
    groups = _group_rows_by_venue(rows)
    assert len(groups) == 1  # all three rows collapse into ONE venue
    (name, city), venue_rows = groups[0]
    assert len(venue_rows) == 3

    result = import_venue_group(name, city, venue_rows)
    assert result["status"] == "OK"
    assert "3 new menu source" in result["detail"]

    with get_conn() as conn:
        venue_count = conn.execute("SELECT COUNT(*) AS n FROM venues WHERE venue_name = ?", ("Multi Bar",)).fetchone()["n"]
        sources = conn.execute(
            "SELECT menu_url, is_primary FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)",
            ("Multi Bar",),
        ).fetchall()
    assert venue_count == 1
    assert len(sources) == 3
    primary_rows = [s for s in sources if s["is_primary"] == 1]
    assert len(primary_rows) == 1
    assert primary_rows[0]["menu_url"] == "https://multibar.de/drinks"


def test_multi_image_menu_pages_all_attach_to_same_venue(db):
    rows = [
        {"venue_name": "Photo Menu Bar", "city": "Munich", "menu_url": f"https://photobar.de/img/menu{i}.jpg", "menu_name": f"Drinks Menu ({i}/4)", "is_primary": "true" if i == 1 else ""}
        for i in range(1, 5)
    ]
    groups = _group_rows_by_venue(rows)
    (name, city), venue_rows = groups[0]
    result = import_venue_group(name, city, venue_rows)
    assert result["status"] == "OK"

    with get_conn() as conn:
        sources = conn.execute(
            "SELECT menu_source_type, menu_name FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)",
            ("Photo Menu Bar",),
        ).fetchall()
    assert len(sources) == 4
    assert all(s["menu_source_type"] == "IMAGE" for s in sources)


def test_primary_defaults_to_first_menu_row_when_unspecified(db):
    rows = [
        {"venue_name": "No Explicit Primary Bar", "city": "Berlin", "menu_url": "https://npbar.de/a"},
        {"venue_name": "No Explicit Primary Bar", "city": "Berlin", "menu_url": "https://npbar.de/b"},
    ]
    groups = _group_rows_by_venue(rows)
    (name, city), venue_rows = groups[0]
    import_venue_group(name, city, venue_rows)

    with get_conn() as conn:
        primary = conn.execute(
            "SELECT menu_url FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?) AND is_primary = 1",
            ("No Explicit Primary Bar",),
        ).fetchone()
    assert primary["menu_url"] == "https://npbar.de/a"


def test_menu_source_type_and_category_auto_detected_when_blank(db):
    rows = [{"venue_name": "Auto Detect Bar", "city": "Cologne", "menu_url": "https://autobar.de/cocktails.pdf"}]
    groups = _group_rows_by_venue(rows)
    (name, city), venue_rows = groups[0]
    import_venue_group(name, city, venue_rows)

    with get_conn() as conn:
        source = conn.execute(
            "SELECT menu_source_type, menu_category FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)",
            ("Auto Detect Bar",),
        ).fetchone()
    assert source["menu_source_type"] == "PDF"
    assert source["menu_category"] == "COCKTAIL"


def test_rows_missing_name_or_city_are_dropped_during_grouping(db):
    rows = [
        {"venue_name": "", "city": "Berlin", "menu_url": "https://x.de/a"},
        {"venue_name": "Valid Bar", "city": "", "menu_url": "https://x.de/b"},
        {"venue_name": "Valid Bar", "city": "Berlin", "menu_url": "https://x.de/c"},
    ]
    groups = _group_rows_by_venue(rows)
    assert len(groups) == 1
    (name, city), venue_rows = groups[0]
    assert name == "Valid Bar" and city == "Berlin"
    assert len(venue_rows) == 1


def test_rerunning_import_does_not_duplicate_menu_sources(db):
    rows = [{"venue_name": "Idempotent Bar", "city": "Berlin", "menu_url": "https://idem.de/menu"}]
    groups = _group_rows_by_venue(rows)
    (name, city), venue_rows = groups[0]

    first = import_venue_group(name, city, venue_rows)
    second = import_venue_group(name, city, venue_rows)

    assert first["status"] == "OK"
    assert "0 new menu source" in second["detail"]
    assert "already existed" in second["detail"]

    with get_conn() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)",
            ("Idempotent Bar",),
        ).fetchone()["n"]
    assert count == 1  # re-running the same import never creates a duplicate row


def test_venue_only_row_with_no_menu_url_stays_new(db):
    rows = [{"venue_name": "Website Only Bar", "city": "Berlin", "website_url": "https://webonly.de"}]
    groups = _group_rows_by_venue(rows)
    (name, city), venue_rows = groups[0]
    result = import_venue_group(name, city, venue_rows)
    assert result["status"] == "OK"

    with get_conn() as conn:
        venue = conn.execute("SELECT status, website_url FROM venues WHERE venue_name = ?", ("Website Only Bar",)).fetchone()
    assert venue["status"] == "NEW"
    assert venue["website_url"] == "https://webonly.de"


def test_flags_possible_duplicate_of_existing_venue(db):
    rows1 = [{"venue_name": "Buck and Breck", "city": "Berlin", "menu_url": "https://buckandbreck.com/menu"}]
    groups1 = _group_rows_by_venue(rows1)
    import_venue_group(*groups1[0][0], groups1[0][1])

    rows2 = [{"venue_name": "Buck and Breck Bar", "city": "Berlin", "menu_url": "https://buckandbreck.com/other"}]
    groups2 = _group_rows_by_venue(rows2)
    result = import_venue_group(*groups2[0][0], groups2[0][1])

    assert result["status"] == "OK"
    assert "WARNING" in result["detail"]


# ---------------------------------------------------------------------------
# Wide format (menu_url_1..5) and delimiter auto-detection
# ---------------------------------------------------------------------------

def test_wide_format_is_detected():
    rows = [{"venue_name": "X", "city": "Berlin", "menu_url_1": "https://x.de/a"}]
    assert _is_wide_format(rows) is True


def test_long_format_is_not_detected_as_wide():
    rows = [{"venue_name": "X", "city": "Berlin", "menu_url": "https://x.de/a"}]
    assert _is_wide_format(rows) is False


def test_wide_row_expands_to_multiple_long_rows_with_menu_url_1_as_primary():
    row = {
        "venue_name": "Multi Slot Bar", "city": "Berlin", "tier": "1",
        "address": "Teststr. 1", "website_url": "https://multislot.de",
        "menu_url_1": "https://multislot.de/drinks", "menu_name_1": "Drinks",
        "menu_url_2": "https://multislot.de/wine.pdf", "menu_name_2": "Wine",
        "menu_url_3": "", "menu_url_4": "", "menu_url_5": "",
    }
    long_rows = _wide_row_to_long_rows(row)
    assert len(long_rows) == 2
    assert long_rows[0]["menu_url"] == "https://multislot.de/drinks"
    assert long_rows[0]["is_primary"] == "true"
    assert long_rows[1]["menu_url"] == "https://multislot.de/wine.pdf"
    assert long_rows[1]["is_primary"] == ""
    # shared fields carried onto every expanded row
    assert all(r["website_url"] == "https://multislot.de" for r in long_rows)


def test_wide_row_with_all_five_slots_filled():
    row = {"venue_name": "Five Slot Bar", "city": "Berlin"}
    for i in range(1, 6):
        row[f"menu_url_{i}"] = f"https://fiveslot.de/menu{i}"
    long_rows = _wide_row_to_long_rows(row)
    assert len(long_rows) == 5
    assert long_rows[0]["is_primary"] == "true"
    assert all(r["is_primary"] == "" for r in long_rows[1:])


def test_wide_row_with_no_menu_urls_still_registers_venue():
    row = {"venue_name": "No Menus Yet Bar", "city": "Berlin", "website_url": "https://nomenu.de"}
    long_rows = _wide_row_to_long_rows(row)
    assert len(long_rows) == 1
    assert long_rows[0]["menu_url"] == ""
    assert long_rows[0]["website_url"] == "https://nomenu.de"


def test_normalize_rows_end_to_end_wide_format_import(db):
    row = {
        "venue_name": "Wide Import Bar", "city": "Munich",
        "menu_url_1": "https://wideimport.de/cocktails", "menu_name_1": "Cocktails",
        "menu_url_2": "https://wideimport.de/wine.pdf", "menu_name_2": "Wine",
        "menu_url_3": "", "menu_url_4": "", "menu_url_5": "",
    }
    normalized = _normalize_rows([row])
    groups = _group_rows_by_venue(normalized)
    assert len(groups) == 1
    (name, city), venue_rows = groups[0]
    result = import_venue_group(name, city, venue_rows)
    assert result["status"] == "OK"

    with get_conn() as conn:
        sources = conn.execute(
            "SELECT menu_url, is_primary FROM menu_sources WHERE venue_id = (SELECT venue_id FROM venues WHERE venue_name = ?)",
            ("Wide Import Bar",),
        ).fetchall()
    assert len(sources) == 2
    primary = [s for s in sources if s["is_primary"] == 1]
    assert len(primary) == 1
    assert primary[0]["menu_url"] == "https://wideimport.de/cocktails"


def test_sniff_delimiter_detects_semicolon():
    sample = "venue_name;city;menu_url_1\r\nSome Bar;Berlin;https://x.de\r\n"
    assert _sniff_delimiter(sample) == ";"


def test_sniff_delimiter_detects_comma():
    sample = "venue_name,city,menu_url_1\r\nSome Bar,Berlin,https://x.de\r\n"
    assert _sniff_delimiter(sample) == ","


def test_read_csv_rows_handles_semicolon_delimited_utf8_bom_file(tmp_path):
    content = (
        "venue_name;city;tier;menu_url_1\r\n"
        "Kr\u00e4uter Bar;Berlin;1;https://kraeuterbar.de/menu\r\n"
    )
    path = tmp_path / "excel_export.csv"
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))  # UTF-8 BOM, matches real Excel export

    rows = _read_csv_rows(path)
    assert len(rows) == 1
    assert rows[0]["venue_name"] == "Kr\u00e4uter Bar"  # umlaut survived correctly
    assert rows[0]["menu_url_1"] == "https://kraeuterbar.de/menu"


def test_read_csv_rows_from_url_fetches_and_parses_google_sheets_export(monkeypatch):
    import src.pipeline.import_manual_venues as import_module

    class FakeResponse:
        status_code = 200
        text = "venue_name,city,menu_url_1\r\nSheet Bar,Berlin,https://sheetbar.de/menu\r\n"

    monkeypatch.setattr("src.utils.http_utils.get", lambda url, **kwargs: FakeResponse())

    rows = import_module._read_csv_rows_from_url("https://docs.google.com/spreadsheets/d/FAKE/export?format=csv")
    assert len(rows) == 1
    assert rows[0]["venue_name"] == "Sheet Bar"
    assert rows[0]["menu_url_1"] == "https://sheetbar.de/menu"


def test_read_csv_rows_from_url_raises_on_failure(monkeypatch):
    monkeypatch.setattr("src.utils.http_utils.get", lambda url, **kwargs: None)

    with pytest.raises(RuntimeError):
        _read_csv_rows_from_url("https://example.com/nonexistent.csv")
