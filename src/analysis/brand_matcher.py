"""Matches known spirit brands in menu text.

Whole-text scanning (scan_text_for_brands) is the robust path: it works
regardless of how well the line-item parser did, since keyword matching
doesn't depend on correct line/column reconstruction. This is deliberately
the primary source of brand-mention data - per-item attribution (which
specific drink calls which brand) is a nice-to-have layered on top where
the parser was confident enough to produce a clean item, not the only way
brand data gets captured.
"""
from __future__ import annotations

import re
from functools import lru_cache

from src.utils.config import REPO_ROOT, load_yaml


@lru_cache(maxsize=1)
def brand_dictionary() -> dict[str, list[str]]:
    return load_yaml("config/brands.yaml")


@lru_cache(maxsize=1)
def _compiled_brand_patterns() -> list[tuple[str, str, re.Pattern]]:
    """Returns [(brand_name, spirit_category, compiled_regex), ...], sorted
    longest-name-first so e.g. "Martini Rosso" matches before a hypothetical
    bare "Martini" entry would."""
    patterns = []
    for category, brands in brand_dictionary().items():
        for brand in brands:
            escaped = re.escape(brand)
            # allow a straight apostrophe to also match a curly one, and vice versa
            escaped = escaped.replace(r"\'", "['’]")
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
            patterns.append((brand, category, pattern))
    patterns.sort(key=lambda p: len(p[0]), reverse=True)
    return patterns


def scan_text_for_brands(text: str) -> list[dict]:
    """Returns [{"brand_name", "spirit_category", "mention_count"}, ...] for
    every distinct brand found anywhere in the text, case-insensitive."""
    if not text:
        return []
    results = []
    for brand, category, pattern in _compiled_brand_patterns():
        count = len(pattern.findall(text))
        if count > 0:
            results.append({"brand_name": brand, "spirit_category": category, "mention_count": count})
    return results


def find_brand_in_text(text: str) -> tuple[str, str] | None:
    """Returns (brand_name, spirit_category) for the first/best brand match
    in a short text (e.g. a single item's name+ingredients), or None."""
    if not text:
        return None
    for brand, category, pattern in _compiled_brand_patterns():
        if pattern.search(text):
            return brand, category
    return None
