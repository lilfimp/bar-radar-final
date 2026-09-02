-- Migration 002: Phase 3 - structured menu item + brand extraction
--
-- The original menu_items/brand_mentions tables (in schema.sql) were
-- scaffolded around a menu_snapshots concept that was never actually built
-- (nothing writes to menu_snapshots). Since those two tables have zero rows
-- in every deployment - no code has ever written to them - it's safe to
-- redesign them properly now, before first use, rather than bolt nullable
-- workarounds onto a shape that doesn't fit the real data.
--
-- New design: menu_items and brand_mentions reference menu_sources
-- directly (the thing we actually populate), not a snapshot layer.

DROP TABLE IF EXISTS brand_mentions;
DROP TABLE IF EXISTS menu_items;

CREATE TABLE menu_items (
    item_id             TEXT PRIMARY KEY,
    menu_source_id      TEXT NOT NULL REFERENCES menu_sources(menu_source_id),
    venue_id            TEXT NOT NULL REFERENCES venues(venue_id),
    item_name           TEXT,
    raw_line            TEXT,      -- the original text this item was parsed from - always kept for auditing
    price_value         REAL,
    price_currency      TEXT,      -- EUR, USD, GBP, etc.
    beverage_category   TEXT,      -- COCKTAIL, BEER, WINE, SPIRIT, SOFT_DRINK, MIXER, OTHER
    spirit_category      TEXT,      -- GIN, VODKA, RUM, TEQUILA_MEZCAL, WHISKY, COGNAC_BRANDY,
                                     -- LIQUEUR_APERITIF, WINE, SPARKLING_WINE, BEER, NON_ALCOHOLIC, OTHER
    is_alcoholic          INTEGER,   -- 1 = yes, 0 = no, NULL = unknown
    ingredients_text        TEXT,
    parse_confidence          REAL,    -- 0-1, how confident the line-parser is in this item's name/price split
    parse_method                TEXT,    -- name_price_same_line, name_then_ingredients_line, multi_price_line, unparsed_fallback
    created_at                    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE brand_mentions (
    mention_id       TEXT PRIMARY KEY,
    menu_source_id     TEXT NOT NULL REFERENCES menu_sources(menu_source_id),
    venue_id             TEXT NOT NULL REFERENCES venues(venue_id),
    item_id                TEXT REFERENCES menu_items(item_id),  -- nullable: whole-text
                                                                   -- scanning finds brands even
                                                                   -- when line-item parsing fails
    brand_name                TEXT NOT NULL,
    spirit_category              TEXT,   -- the category this brand belongs to, from the brand dictionary
    mention_count                  INTEGER DEFAULT 1,
    confidence                        REAL,
    created_at                          TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_menu_items_menu_source ON menu_items(menu_source_id);
CREATE INDEX idx_menu_items_venue ON menu_items(venue_id);
CREATE INDEX idx_menu_items_beverage_category ON menu_items(beverage_category);
CREATE INDEX idx_menu_items_spirit_category ON menu_items(spirit_category);

CREATE INDEX idx_brand_mentions_menu_source ON brand_mentions(menu_source_id);
CREATE INDEX idx_brand_mentions_brand ON brand_mentions(brand_name);
CREATE INDEX idx_brand_mentions_venue ON brand_mentions(venue_id);

-- Tracks which menu_sources have already been run through Phase 3 analysis,
-- so re-running the batch is resumable/idempotent (same pattern as Phase 2's
-- extraction_status - process once, skip on subsequent runs unless forced).
CREATE TABLE IF NOT EXISTS menu_source_analysis_status (
    menu_source_id       TEXT PRIMARY KEY REFERENCES menu_sources(menu_source_id),
    analyzed_at             TEXT DEFAULT (datetime('now')),
    items_found                INTEGER,
    brand_mentions_found          INTEGER
);
