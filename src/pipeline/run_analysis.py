"""Batch 4 (Phase 3): turns extracted_text (Phase 2's output) into
structured menu_items and brand_mentions.

For each not-yet-analyzed menu source with real extracted text:
1. Parse the text into candidate line items (name, price, ingredients) -
   best-effort, confidence-scored (see src/analysis/item_parser.py).
2. Classify each item's beverage_category, spirit_category, is_alcoholic
   (see src/analysis/item_classifier.py).
3. Scan the WHOLE text for known brand mentions, independent of how well
   item-level parsing went - this is the robust path for brand data (see
   src/analysis/brand_matcher.py). Also attempts to link a brand mention to
   a specific parsed item when the brand appears in that item's text.

Resumable: a menu_source is only ever analyzed once (tracked in
menu_source_analysis_status) unless you clear that table's row for it.

Usage:
    python -m src.pipeline.run_analysis
    python -m src.pipeline.run_analysis --batch-size 200
"""
from __future__ import annotations

import argparse
import uuid

from db.database import (
    get_unanalyzed_menu_sources,
    insert_brand_mentions,
    insert_menu_items,
    mark_menu_source_analyzed,
)
from db.migrate import run as run_migrations
from src.analysis.brand_matcher import scan_text_for_brands
from src.analysis.item_classifier import classify_item
from src.analysis.item_parser import parse_menu_items
from src.utils.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_BATCH_SIZE = 300


def analyze_menu_source(source: dict) -> tuple[list[dict], list[dict]]:
    """Returns (menu_item_rows, brand_mention_rows) ready for DB insertion."""
    menu_source_id = source["menu_source_id"]
    venue_id = source["venue_id"]
    text = source["extracted_text"] or ""
    menu_category_hint = source.get("menu_category")

    parsed_items = parse_menu_items(text)

    item_rows = []
    item_id_by_index: list[str] = []
    for parsed in parsed_items:
        item_id = str(uuid.uuid4())
        item_id_by_index.append(item_id)
        classification = classify_item(
            parsed["item_name"], parsed.get("ingredients_text") or "", menu_category_hint
        )
        item_rows.append({
            "item_id": item_id,
            "menu_source_id": menu_source_id,
            "venue_id": venue_id,
            "item_name": parsed["item_name"],
            "raw_line": parsed["raw_line"],
            "price_value": parsed["price_value"],
            "price_currency": parsed["price_currency"],
            "beverage_category": classification["beverage_category"],
            "spirit_category": classification["spirit_category"],
            "is_alcoholic": classification["is_alcoholic"],
            "ingredients_text": parsed.get("ingredients_text"),
            "parse_confidence": parsed["parse_confidence"],
            "parse_method": parsed["parse_method"],
        })

    # Whole-text brand scan - robust regardless of item-parsing quality.
    whole_text_brands = scan_text_for_brands(text)
    mention_rows = []
    for brand in whole_text_brands:
        # Try to link to a specific item that also mentions this brand, for
        # richer downstream queries - not required, just a nice-to-have.
        linked_item_id = None
        for parsed, item_id in zip(parsed_items, item_id_by_index):
            haystack = f"{parsed['item_name']} {parsed.get('ingredients_text') or ''}".lower()
            if brand["brand_name"].lower() in haystack:
                linked_item_id = item_id
                break
        mention_rows.append({
            "mention_id": str(uuid.uuid4()),
            "menu_source_id": menu_source_id,
            "venue_id": venue_id,
            "item_id": linked_item_id,
            "brand_name": brand["brand_name"],
            "spirit_category": brand["spirit_category"],
            "mention_count": brand["mention_count"],
            "confidence": 0.9,  # whole-text keyword match - high confidence by design
        })

    return item_rows, mention_rows


def run(batch_size: int | None = None) -> None:
    run_migrations()
    batch_size = batch_size or DEFAULT_BATCH_SIZE
    sources = get_unanalyzed_menu_sources(batch_size)
    log.info("Analyzing %d menu source(s)", len(sources))

    total_items = 0
    total_mentions = 0
    for source in sources:
        source = dict(source)
        try:
            item_rows, mention_rows = analyze_menu_source(source)
        except Exception as exc:  # noqa: BLE001 - keep the batch alive on per-source errors
            log.exception("Analysis failed for menu_source %s: %s", source["menu_source_id"], exc)
            mark_menu_source_analyzed(source["menu_source_id"], 0, 0)
            continue

        insert_menu_items(item_rows)
        insert_brand_mentions(mention_rows)
        mark_menu_source_analyzed(source["menu_source_id"], len(item_rows), len(mention_rows))
        total_items += len(item_rows)
        total_mentions += len(mention_rows)

    log.info(
        "Analysis batch complete: %d menu source(s) processed, %d items extracted, %d brand mentions found",
        len(sources), total_items, total_mentions,
    )


def main():
    parser = argparse.ArgumentParser(description="BAR RADAR Phase 3 - menu item / brand analysis batch runner")
    parser.add_argument("--batch-size", type=int, default=None)
    args = parser.parse_args()
    run(batch_size=args.batch_size)


if __name__ == "__main__":
    main()
