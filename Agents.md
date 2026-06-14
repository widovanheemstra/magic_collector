# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Install deps and run the web app:
```bash
pip install -r requirements.txt
python app.py            # serves on http://127.0.0.1:5001 by default
```

Smoke-test the Scryfall API (no test framework configured):
```bash
python test_api.py
```

Elasticsearch indexing pipeline (requires a running ES cluster and `.env` configured — see `.env.example`):
```bash
python create_elk_index.py        # create the `mtg_cards` index with mappings
python load_bulk_cards_to_elk.py  # download Scryfall bulk data and bulk-index every card
```

`main.py` is an unused stub from `uv init` — the real entry point is `app.py`.

## Architecture

This is a single-file Flask monolith (`app.py`, ~1700 lines) backed by a local SQLite database, with Scryfall as the external data source and optional Elasticsearch as a parallel search index.

**Data flow.** The canonical store is SQLite (`magic_collector.db`, configurable via `DATABASE` env var). `init_db()` creates/migrates all tables and is only invoked from the `__main__` block in `app.py` — importing the module does NOT run migrations, so test/REPL code must call `app.init_db()` explicitly. The app pulls from Scryfall on demand via `/fetch_sets` and `/fetch_cards/<set_code>`, then `store_sets()` / `store_cards()` persist into SQLite. Card refresh from Scryfall goes through `store_single_card()`. The Elasticsearch scripts are independent of the Flask app — they download Scryfall bulk data directly and do not read from SQLite.

**Key tables.**
- `sets`, `cards` — Scryfall mirror. Complex fields (`prices`, `legalities`, `image_uris`, `card_faces`) are stored as JSON strings; templates decode them with the `from_json` Jinja filter registered in `app.py`.
- `user_collection` — quantities keyed by `(card_id, is_foil)`. Helpers: `get_collection_quantity`, `get_collection_totals`, `add_to_collection`, `update_collection_quantity`.
- `trade_data` — buy/sell ledger. **The trading routes (`/add_trade`, `/delete_trade`) mutate `user_collection` as a side effect** (buy adds, sell removes, delete rolls back). Any change to trading logic must keep collection state consistent.
- `decks`, `deck_cards` — deck lists with a `sideboard` flag. Deck routes validate card names against the `cards` table via `validate_cards_in_database()` and parse pasted decklists via `parse_decklist_text()`.
- `card_legalities_history`, `card_prices_history` — append-only history written by `save_legalities_history` / `save_prices_history` on every card store.

**Pricing.** `get_card_price(card_data, is_foil)` is the single source of truth for resolving a price from a card's JSON `prices` blob (handles foil/non-foil fallback). Collection value calculations and trade profit all funnel through it.

**Collection sorting.** `view_collection_group()` (route `/collection/<group_id>`) accepts a `?sort=` query parameter with values `collector_number` (default), `color`, or `rarity`. The `sort_collection()` helper and `parse_mana_cost()` helper in `app.py` handle the sorting logic. Color sort groups cards by MTG color (single-color → multi-color → colorless), then by rarity within each group, then by collector number. Rarity sort orders common → uncommon → rare → mythic. The `group_detail.html` template renders three toggle buttons (Collector, Color, Rarity) in the header bar.

**Double-faced cards.** Cards may have a `card_faces` JSON array instead of (or in addition to) top-level `image_uris`. Templates and `store_cards()` handle both shapes — preserve this when touching card-rendering code.

**Configuration.** All config is read from environment variables via `python-dotenv` at the top of `app.py` and the ELK scripts. Defaults are in the README; `.env.example` shows a working local setup.

**Frontend.** Server-rendered Jinja2 templates in `templates/` extending `base.html` (Bootstrap 5 + Font Awesome via CDN). No build step, no JS framework.

## Notes for editing

- Schema changes belong in `init_db()`. There are no migrations — additive `ALTER TABLE` patterns inside `init_db()` (wrapped in try/except for "already exists") are the convention.
- When adding routes that read/write the collection, reuse the `*_collection*` helpers rather than issuing raw SQL — they handle the foil/non-foil split and timestamps.
- `requirements.txt` is the authoritative dep list; `pyproject.toml` exists for `uv` but its `dependencies = []` is empty and not used.
