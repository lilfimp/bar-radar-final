from src.analysis.text_normalize import fix_letter_spacing, normalize_menu_text


def test_fix_letter_spacing_recovers_name_and_price():
    # Real sample from Monkey Bar's extracted PDF text - this is the
    # actual pattern that motivated building this module.
    text = "M A I T A I 1 6"
    assert fix_letter_spacing(text) == "MAITAI 16"


def test_fix_letter_spacing_leaves_normal_text_untouched():
    text = "Negroni 12€ with Campari and Vermouth"
    assert fix_letter_spacing(text) == text


def test_fix_letter_spacing_does_not_fuse_price_into_name():
    text = "C L A S S I C M A R T I N I 1 3"
    result = fix_letter_spacing(text)
    assert "13" in result
    assert "MARTINI13" not in result  # a real word-boundary space must survive


def test_fix_letter_spacing_ignores_short_legitimate_single_letters():
    # "a" and "I" appearing naturally shouldn't get glued to neighbors
    text = "Ask a bartender for a recommendation"
    assert fix_letter_spacing(text) == text


def test_normalize_menu_text_collapses_excess_whitespace():
    text = "Negroni    12€\n\n\n\nAperol Spritz   9€"
    result = normalize_menu_text(text)
    assert "    " not in result
    assert "\n\n\n\n" not in result


def test_normalize_menu_text_handles_empty_input():
    assert normalize_menu_text("") == ""
    assert normalize_menu_text(None) == ""
