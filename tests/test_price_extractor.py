from src.analysis.price_extractor import extract_best_price, extract_priced_amounts, extract_trailing_bare_price


def test_bare_trailing_number_treated_as_price():
    result = extract_best_price("Classic Martini 13")
    assert result == {"value": 13.0, "currency": "EUR", "raw": "13"}


def test_german_decimal_comma_with_euro_symbol():
    result = extract_best_price("Aperol Spritz 9,50€")
    assert result["value"] == 9.5
    assert result["currency"] == "EUR"


def test_decimal_point_bare_number():
    result = extract_best_price("Poiré (Birnen-Cidre), Normandie 5.5")
    assert result["value"] == 5.5


def test_multi_size_wine_pricing_returns_all_in_order():
    result = extract_priced_amounts("RIESLING THÖRNICHER 10 € 15 € 65 €")
    assert [r["value"] for r in result] == [10.0, 15.0, 65.0]


def test_best_price_takes_first_of_multiple():
    result = extract_best_price("RIESLING THÖRNICHER 10 € 15 € 65 €")
    assert result["value"] == 10.0


def test_implausible_bare_number_rejected_as_price():
    # e.g. a year or a volume marker, not a realistic drink price
    assert extract_trailing_bare_price("Vintage from 2026") is None


def test_no_price_present_returns_none():
    assert extract_best_price("an item with no price at all in it") is None


def test_bare_number_not_at_line_end_is_not_treated_as_price():
    # a number appearing mid-sentence (not trailing) shouldn't be grabbed
    assert extract_trailing_bare_price("Serves 2 people generously") is None


def test_dollar_and_pound_symbols_recognized():
    assert extract_best_price("Old Fashioned $14")["currency"] == "USD"
    assert extract_best_price("Old Fashioned £14")["currency"] == "GBP"
