"""Classifies a parsed menu item's beverage category, spirit category, and
alcoholic/non-alcoholic status from its name + ingredients text.

Two-step approach:
1. Check for a known brand (src/analysis/brand_matcher.py) - if found, its
   spirit_category is authoritative (a Bombay Sapphire drink IS gin).
2. Otherwise fall back to generic keyword matching for the spirit/beverage
   type itself (the item might say "gin" without naming a specific brand).
"""
from __future__ import annotations

import re

from src.analysis.brand_matcher import find_brand_in_text

# Generic spirit/category keywords, checked when no specific brand is named.
# Order matters: more specific terms are checked first so e.g. "mezcal"
# isn't swallowed by a broader "tequila" pass if both were combined.
SPIRIT_KEYWORDS: dict[str, list[str]] = {
    "GIN": ["gin"],
    "VODKA": ["vodka", "wodka"],
    "RUM": ["rum"],
    "TEQUILA_MEZCAL": ["tequila", "mezcal"],
    "WHISKY": ["whisky", "whiskey", "bourbon", "scotch"],
    "COGNAC_BRANDY": ["cognac", "brandy", "armagnac"],
    "LIQUEUR_APERITIF": [
        "liqueur", "likör", "vermouth", "wermut", "amaro", "aperitif",
        "bitters", "campari", "aperol",
    ],
    "SPARKLING_WINE": ["prosecco", "champagne", "cava", "crémant", "cremant", "sekt"],
    "WINE": ["wine", "wein", "riesling", "chardonnay", "pinot", "sauvignon", "merlot", "grauburgunder"],
    "BEER": ["beer", "bier", "lager", "pils", "ipa", "weizen"],
}

NON_ALCOHOLIC_KEYWORDS = [
    # Explicit markers only - these override everything else, including a
    # named spirit, because a "virgin" version of a cocktail is genuinely
    # non-alcoholic even if it references the spirit by name.
    "alkoholfrei", "alcohol-free", "non-alcoholic", "non alcoholic",
    "mocktail", "virgin", "n/a", "alkoholfreie",
]

# Used only as a fallback signal for beverage_category when NO spirit is
# named - NOT used to override is_alcoholic, since "lemon juice" and
# "orange juice" are extremely common cocktail ingredients (a gin cocktail
# containing juice is still alcoholic; only the presence/absence of a named
# spirit should drive that call).
SOFT_DRINK_KEYWORDS = [
    "saft", "juice", "limonade", "lemonade", "cola", "wasser", "water",
    "schorle", "tee", "tea", "kaffee", "coffee",
]

MIXER_KEYWORDS = ["tonic", "ginger beer", "ginger ale", "soda water", "fever-tree"]

COCKTAIL_HINT_KEYWORDS = ["cocktail", "mixed with", "shaken", "stirred", "muddled"]


def _contains_word(text: str, phrase: str) -> bool:
    """Strict word-boundary match. Used for short English spirit stems that
    are prone to accidental substring collisions inside unrelated words -
    "virgin" contains "gin", "forum"/"drum" contain "rum", etc."""
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _contains_substring(text: str, phrase: str) -> bool:
    """Plain substring match. Used for German soft-drink/beverage terms,
    where strict word-boundary matching actively breaks things: German
    compounds glue words together with no space or internal boundary
    ("Tomatensaft" = tomato+juice; \\bsaft\\b would never match inside it).
    These particular terms aren't prone to the same kind of accidental
    mid-word collision that the English spirit stems are."""
    return phrase in text


def classify_item(item_name: str, ingredients_text: str, menu_category_hint: str | None = None) -> dict:
    """Returns {"beverage_category", "spirit_category", "is_alcoholic"}.
    menu_category_hint is the parent menu_source's menu_category (e.g.
    'COCKTAIL', 'WINE') - used as a weak prior when the item text itself is
    ambiguous, never overridden by it when the text gives a clear signal."""
    combined = f"{item_name or ''} {ingredients_text or ''}".lower()

    brand_match = find_brand_in_text(combined)
    spirit_category = brand_match[1] if brand_match else None

    if not spirit_category:
        for category, keywords in SPIRIT_KEYWORDS.items():
            if any(_contains_word(combined, kw) for kw in keywords):
                spirit_category = category
                break

    is_non_alcoholic = any(_contains_word(combined, kw) for kw in NON_ALCOHOLIC_KEYWORDS)
    is_soft_drink = any(_contains_substring(combined, kw) for kw in SOFT_DRINK_KEYWORDS)
    is_mixer = any(_contains_substring(combined, kw) for kw in MIXER_KEYWORDS)

    # beverage_category
    if is_soft_drink and not spirit_category:
        beverage_category = "SOFT_DRINK"
    elif is_mixer and not spirit_category:
        beverage_category = "MIXER"
    elif spirit_category == "BEER":
        beverage_category = "BEER"
    elif spirit_category in ("WINE", "SPARKLING_WINE"):
        beverage_category = "WINE"
    elif spirit_category:
        # A named spirit with multiple ingredients reads as a cocktail; a
        # single named spirit with no other ingredients reads as a straight
        # SPIRIT pour. Use ingredient-list density as the signal.
        ingredient_count = len([p for p in (ingredients_text or "").split(",") if p.strip()]) or \
                            len([p for p in (ingredients_text or "").split(".") if p.strip()])
        if any(_contains_word(combined, kw) for kw in COCKTAIL_HINT_KEYWORDS) or ingredient_count >= 2:
            beverage_category = "COCKTAIL"
        elif menu_category_hint == "COCKTAIL":
            beverage_category = "COCKTAIL"
        else:
            beverage_category = "SPIRIT"
    elif menu_category_hint in ("COCKTAIL", "WINE", "BEER", "SPIRITS"):
        beverage_category = "COCKTAIL" if menu_category_hint == "COCKTAIL" else menu_category_hint.rstrip("S")
    else:
        beverage_category = "OTHER"

    # is_alcoholic - explicit non-alcoholic markers always win (a "virgin"
    # cocktail may still name the spirit it's imitating); a named spirit or
    # alcoholic beverage_category wins next; soft drinks/mixers are non-
    # alcoholic; otherwise genuinely unknown rather than guessed.
    if is_non_alcoholic:
        is_alcoholic = False
    elif spirit_category or beverage_category in ("COCKTAIL", "BEER", "WINE", "SPIRIT"):
        is_alcoholic = True
    elif beverage_category in ("SOFT_DRINK", "MIXER"):
        is_alcoholic = False
    else:
        is_alcoholic = None  # genuinely unknown - don't guess

    return {
        "beverage_category": beverage_category,
        "spirit_category": spirit_category or "OTHER",
        "is_alcoholic": is_alcoholic,
    }
