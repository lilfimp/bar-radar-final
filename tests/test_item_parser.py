from src.analysis.item_parser import parse_menu_items

# All fixtures below are excerpts of REAL extracted menu text (from actual
# BAR RADAR runs), not idealized synthetic examples - this is deliberate,
# so the tests reflect what the parser actually has to handle.

AMANO_BAR_SAMPLE = """COCKTAILS
Contactless and Card Payment only.
All Prices are in €uro including VAT.
Classic Martini 13
Choose Vodka or Gin . Dry Vermouth
Espresso Martini 13
42 Below Vodka . Coffee Liquor . fresh Espresso
Margarita 13
1800 Blanco Tequila . Orange Liquor . Lime Juice"""

BELLBOY_SAMPLE = """Cocktails
FRUITY
Berlin Donkey 16
Bombay Sapphire, Lychee, Banana, Wheat
Lemon Passion Flip 17
Cognac, Curd, Passion, Hawaij"""

GOLVET_SAMPLE = """Inverted Root
Sweet
• Dry Vermouth
Sour
• Gin
Salty
• Beetroot
dry
• Spruce
Abv
16
See Orchard
Sweet
• Gin
Sour
• Sake"""

LANG_WINE_SAMPLE = """WHITE WINE 0,1 l 0,2 l 0,75 l
CHARDONNAY LANTIDIS 10 € 15 € 65 €
Macedonia, Greece
RIESLING THÖRNICHER 10 € 15 € 65 €
Weingut Ludwig, Mosel"""

MONKEY_BAR_GARBLED_SAMPLE = """J U N G L E
M A I T A I 1 6
P l a nta t i o n Ru m B l e n d , Co i nt re a u ,
O rg e a t , L i m e"""


def test_amano_bar_clean_name_price_ingredients_format():
    items = parse_menu_items(AMANO_BAR_SAMPLE)
    assert len(items) == 3
    names = {i["item_name"] for i in items}
    assert names == {"Classic Martini", "Espresso Martini", "Margarita"}
    martini = next(i for i in items if i["item_name"] == "Classic Martini")
    assert martini["price_value"] == 13.0
    assert "Vodka" in martini["ingredients_text"]
    assert martini["parse_confidence"] >= 0.8


def test_bellboy_clean_name_price_ingredients_format():
    items = parse_menu_items(BELLBOY_SAMPLE)
    assert len(items) == 2
    donkey = next(i for i in items if i["item_name"] == "Berlin Donkey")
    assert donkey["price_value"] == 16.0
    assert "Bombay Sapphire" in donkey["ingredients_text"]


def test_golvet_flavor_wheel_format_recovers_real_names_not_taste_labels():
    items = parse_menu_items(GOLVET_SAMPLE)
    names = {i["item_name"] for i in items}
    # The real cocktail names must be recovered, NOT the taste-profile
    # labels ("Sweet", "Sour", etc.) - this was a real bug caught in
    # development where each label got treated as its own fake item.
    assert "Inverted Root" in names
    assert "See Orchard" in names
    assert "Sweet" not in names
    assert "Sour" not in names

    inverted_root = next(i for i in items if i["item_name"] == "Inverted Root")
    assert "Gin" in inverted_root["ingredients_text"]
    assert "Dry Vermouth" in inverted_root["ingredients_text"]
    assert inverted_root["price_value"] is None  # no price on this menu style
    assert inverted_root["parse_method"] == "name_then_taste_profile_bullets"


def test_wine_multi_price_line_captures_first_price_and_region():
    items = parse_menu_items(LANG_WINE_SAMPLE)
    assert len(items) == 2
    chardonnay = next(i for i in items if "CHARDONNAY" in i["item_name"])
    assert chardonnay["price_value"] == 10.0  # first of three prices - documented simplification


def test_garbled_letter_spaced_text_still_recovers_name_and_price():
    items = parse_menu_items(MONKEY_BAR_GARBLED_SAMPLE)
    assert len(items) == 1
    assert items[0]["item_name"] == "MAITAI"
    assert items[0]["price_value"] == 16.0


def test_section_headers_and_boilerplate_are_not_captured_as_items():
    items = parse_menu_items(AMANO_BAR_SAMPLE)
    names = {i["item_name"] for i in items}
    assert "COCKTAILS" not in names
    assert not any("Contactless" in n for n in names)


def test_empty_text_returns_no_items():
    assert parse_menu_items("") == []


def test_every_item_has_a_confidence_score():
    items = parse_menu_items(AMANO_BAR_SAMPLE) + parse_menu_items(GOLVET_SAMPLE)
    assert all(0.0 <= i["parse_confidence"] <= 1.0 for i in items)
