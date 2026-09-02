from src.analysis.item_classifier import classify_item


def test_gin_cocktail_with_juice_ingredient_is_still_alcoholic():
    # Regression: "juice" is a soft-drink keyword AND an extremely common
    # cocktail ingredient. A gin cocktail containing lemon juice must not
    # be misclassified as non-alcoholic just because it lists juice.
    result = classify_item("Gin Basil Smash", "Bombay Sapphire Gin, Lemon Juice, Simple Syrup, Basil")
    assert result["is_alcoholic"] is True
    assert result["spirit_category"] == "GIN"
    assert result["beverage_category"] == "COCKTAIL"


def test_virgin_prefix_does_not_false_match_gin():
    # Regression: naive substring matching found "gin" inside "virgin".
    result = classify_item("Virgin Mojito", "Rum-free, Lime, Mint, Soda")
    assert result["is_alcoholic"] is False  # explicit "virgin" marker wins


def test_german_compound_word_juice_still_detected():
    # Regression: word-boundary matching (needed to fix the virgin/gin
    # collision) must not break German compound nouns, which have no
    # internal word boundary at all.
    result = classify_item("Tomatensaft", "")
    assert result["beverage_category"] == "SOFT_DRINK"
    assert result["is_alcoholic"] is False


def test_german_compound_schorle_detected():
    result = classify_item("Apfelschorle", "")
    assert result["beverage_category"] == "SOFT_DRINK"


def test_known_brand_sets_spirit_category_authoritatively():
    result = classify_item("Berlin Donkey", "Bombay Sapphire, Lychee, Banana, Wheat")
    assert result["spirit_category"] == "GIN"
    assert result["is_alcoholic"] is True


def test_wine_from_name_and_region():
    result = classify_item("Riesling Thörnicher", "Weingut Ludwig, Mosel")
    assert result["beverage_category"] == "WINE"
    assert result["is_alcoholic"] is True


def test_beer_brand_classified_correctly():
    result = classify_item("Heineken", "0.3l")
    assert result["beverage_category"] == "BEER"
    assert result["spirit_category"] == "BEER"
    assert result["is_alcoholic"] is True


def test_single_spirit_no_ingredients_reads_as_spirit_not_cocktail():
    result = classify_item("Herradura Blanco", "")
    assert result["beverage_category"] == "SPIRIT"
    assert result["spirit_category"] == "TEQUILA_MEZCAL"


def test_multi_ingredient_spirit_reads_as_cocktail():
    result = classify_item("House Special", "Vodka, Elderflower, Lime, Soda, Mint")
    assert result["beverage_category"] == "COCKTAIL"


def test_ambiguous_item_with_no_signal_is_unknown_not_guessed():
    result = classify_item("Chef's Choice", "")
    assert result["is_alcoholic"] is None
