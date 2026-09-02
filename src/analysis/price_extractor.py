"""Extracts price values (and currency, where identifiable) from menu text.

Real menu prices come in several formats, all confirmed against actual
extracted data:
    "13"                    - bare number, no currency symbol (very common)
    "13€" / "€13" / "13 €"  - explicit euro symbol, either side
    "12,50€"                - German decimal comma
    "10 € 15 € 65 €"        - multiple sizes on one line (glass/carafe/bottle)
"""
from __future__ import annotations

import re

CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}

_PRICED_PATTERN = re.compile(
    r"(?P<value1>\d+(?:[.,]\d{1,2})?)\s?(?P<currency1>[€$£])"
    r"|(?P<currency2>[€$£])\s?(?P<value2>\d+(?:[.,]\d{1,2})?)"
)

_BARE_NUMBER_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\b")

# Bare numbers only count as a plausible price within this range - filters
# out things like "0.3l" size markers or a year, while covering the actual
# range seen on real cocktail/wine menus.
BARE_PRICE_MIN = 2.0
BARE_PRICE_MAX = 120.0


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def extract_priced_amounts(text: str) -> list[dict]:
    """Finds every value with an explicit currency symbol. Returns
    [{"value": float, "currency": "EUR", "raw": "12,50€"}, ...] in order of
    appearance. This is the high-confidence path - no guessing involved."""
    results = []
    for m in _PRICED_PATTERN.finditer(text):
        if m.group("value1"):
            value_raw, currency_symbol = m.group("value1"), m.group("currency1")
        else:
            value_raw, currency_symbol = m.group("value2"), m.group("currency2")
        results.append({
            "value": _to_float(value_raw),
            "currency": CURRENCY_SYMBOLS.get(currency_symbol, "EUR"),
            "raw": m.group(0),
        })
    return results


def extract_trailing_bare_price(text: str, default_currency: str = "EUR") -> dict | None:
    """For a short line/fragment with no currency symbol (e.g. "Classic
    Martini 13"), returns the trailing number as a price IF it falls in a
    plausible price range - otherwise None rather than guessing. Only
    intended for use on a single candidate item line, not a whole page."""
    matches = list(_BARE_NUMBER_PATTERN.finditer(text))
    if not matches:
        return None
    last = matches[-1]
    # Only trust it if it's at (or very near) the end of the line - a price
    # elsewhere in the middle of descriptive text is far more likely to be
    # something else (a volume, a year, an ABV percentage).
    trailing_slice = text[last.end():].strip()
    if trailing_slice and not trailing_slice.startswith(("%", "abv", "ABV")):
        return None
    value = _to_float(last.group(1))
    if not (BARE_PRICE_MIN <= value <= BARE_PRICE_MAX):
        return None
    return {"value": value, "currency": default_currency, "raw": last.group(0)}


def extract_best_price(text: str) -> dict | None:
    """Best single price for a short item line: prefer an explicit currency
    symbol if present, else fall back to a plausible trailing bare number."""
    priced = extract_priced_amounts(text)
    if priced:
        return priced[0]
    return extract_trailing_bare_price(text)
