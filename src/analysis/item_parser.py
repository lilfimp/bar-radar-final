"""Splits raw extracted menu text into candidate line items.

This is explicitly best-effort, not a guaranteed-correct parser - real menu
layouts vary enormously (confirmed against actual data): some are clean
"Name Price / ingredients" pairs, some are wine lists with three prices per
line (glass/carafe/bottle), some are taste-profile bullet lists with no
visible price at all, and some extract as scrambled multi-column text where
line-level parsing can't reliably recover which price belongs to which item.

Every item gets a parse_confidence score and a parse_method tag so
downstream consumers (the report, or a human) can tell a clean high-
confidence parse from a shaky one, rather than treating all output as
equally trustworthy.
"""
from __future__ import annotations

import re

from src.analysis.price_extractor import extract_best_price
from src.analysis.text_normalize import normalize_menu_text

MAX_PLAUSIBLE_NAME_LENGTH = 70
INGREDIENT_JOINER_PATTERN = re.compile(r"[,.]|(?:\bund\b)|(?:\bwith\b)|(?:\bmit\b)", re.IGNORECASE)
BULLET_PATTERN = re.compile(r"^[•\-*]\s*")

# Some upscale cocktail menus use a "flavor wheel" format instead of an
# ingredient list: a drink name, then a repeating sequence of taste
# categories each with one bulleted ingredient, ending in an ABV line
# (confirmed against real data - Golvet Bar's menu). This is a closed,
# standard mixology vocabulary, not something a generic heuristic would
# reliably infer, so it's matched explicitly.
TASTE_LABELS = {"sweet", "sour", "salty", "bitter", "dry", "umami", "spicy"}


def _is_taste_label(line: str) -> bool:
    return line.strip().lower() in TASTE_LABELS


def _is_abv_label(line: str) -> bool:
    return line.strip().lower() == "abv"


def _strip_price_from_line(line: str, price: dict) -> str:
    idx = line.rfind(price["raw"])
    name = line[:idx] if idx != -1 else line
    return name.strip(" .-–—:")


def _looks_like_ingredients_line(line: str) -> bool:
    if len(line) > 160:
        return False
    return bool(INGREDIENT_JOINER_PATTERN.search(line))


def _looks_garbled(name: str) -> bool:
    """Flags residual letter-spacing artifacts that normalize_menu_text
    couldn't fully clean up (irregular partial spacing, not the clean
    uniform single-letter case). Not a hard filter - just lowers
    confidence so it's visible in the output rather than trusted blindly."""
    tokens = name.split()
    if not tokens:
        return True
    short_tokens = sum(1 for t in tokens if len(t) <= 2)
    return len(name) > MAX_PLAUSIBLE_NAME_LENGTH or (short_tokens / len(tokens)) > 0.5


def parse_menu_items(text: str) -> list[dict]:
    """Returns a list of candidate items: {"item_name", "raw_line",
    "ingredients_text", "price_value", "price_currency", "parse_confidence",
    "parse_method"}. Lines that don't match any recognizable item pattern
    (section headers, boilerplate, payment notes, etc.) are simply skipped -
    they aren't menu items and shouldn't be reported as low-confidence ones."""
    normalized = normalize_menu_text(text)
    lines = [l.strip() for l in normalized.split("\n") if l.strip()]
    items: list[dict] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Pattern A: "flavor wheel" block - a name line followed by a
        # repeating (taste-label, bullet) sequence, ending in an ABV value.
        # Checked before the generic bullet pattern below, since a generic
        # lookahead would wrongly treat each taste-label line as its own
        # item name (that was a real bug caught against actual data).
        if (
            not _is_taste_label(line)
            and not BULLET_PATTERN.match(line)
            and i + 1 < len(lines)
            and _is_taste_label(lines[i + 1])
        ):
            name = line
            bullets = []
            abv_value = None
            j = i + 1
            while j < len(lines) and _is_taste_label(lines[j]):
                label = lines[j]
                if _is_abv_label(label) and j + 1 < len(lines) and re.match(r"^\d+%?$", lines[j + 1]):
                    abv_value = lines[j + 1]
                    j += 2
                    continue
                if j + 1 < len(lines) and BULLET_PATTERN.match(lines[j + 1]):
                    bullets.append(BULLET_PATTERN.sub("", lines[j + 1]).strip())
                    j += 2
                    continue
                break  # sequence broken - stop the block here

            ingredients_text = "; ".join(bullets) if bullets else None
            confidence = 0.7 if not _looks_garbled(name) else 0.25
            items.append({
                "item_name": name,
                "raw_line": " / ".join([line] + [lines[k] for k in range(i + 1, j)]),
                "ingredients_text": ingredients_text,
                "price_value": None,
                "price_currency": None,
                "parse_confidence": confidence,
                "parse_method": "name_then_taste_profile_bullets",
            })
            i = j
            continue

        # Pattern B: a plain name line followed by generic (non-taste-label)
        # bullets - a simpler ingredient/feature list with no price.
        if i + 1 < len(lines) and BULLET_PATTERN.match(lines[i + 1]):
            name = line
            bullets = []
            j = i + 1
            while j < len(lines) and BULLET_PATTERN.match(lines[j]):
                bullets.append(BULLET_PATTERN.sub("", lines[j]).strip())
                j += 1
            ingredients_text = "; ".join(b for b in bullets if b and not b.lower().startswith("abv"))
            price = extract_best_price(name)  # rare, but check in case price is on the name line itself
            confidence = 0.65 if not _looks_garbled(name) else 0.25
            items.append({
                "item_name": name if not price else _strip_price_from_line(name, price),
                "raw_line": " / ".join([line] + [lines[k] for k in range(i + 1, j)]),
                "ingredients_text": ingredients_text or None,
                "price_value": price["value"] if price else None,
                "price_currency": price["currency"] if price else None,
                "parse_confidence": confidence,
                "parse_method": "name_then_bullets",
            })
            i = j
            continue

        # Pattern C: name + price on the same line, optionally followed by
        # an ingredients line.
        price = extract_best_price(line)
        if price:
            name = _strip_price_from_line(line, price)
            if name and len(name) >= 2:
                ingredients_text = None
                method = "name_price_same_line"
                consumed_next = False
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if not extract_best_price(next_line) and _looks_like_ingredients_line(next_line):
                        ingredients_text = next_line
                        method = "name_then_ingredients_line"
                        consumed_next = True

                confidence = 0.85 if method == "name_then_ingredients_line" else 0.6
                if _looks_garbled(name):
                    confidence = min(confidence, 0.25)

                items.append({
                    "item_name": name,
                    "raw_line": line + (f" / {ingredients_text}" if ingredients_text else ""),
                    "ingredients_text": ingredients_text,
                    "price_value": price["value"],
                    "price_currency": price["currency"],
                    "parse_confidence": confidence,
                    "parse_method": method,
                })
                i += 2 if consumed_next else 1
                continue

        i += 1  # unrecognized line (header, boilerplate, etc.) - skip, not an item

    return items
