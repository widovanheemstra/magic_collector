# Magic Collector

A local web app for collecting, valuing, organizing, and deck-building Magic: The Gathering cards. Scryfall is the card data source; the app mirrors that catalog and layers your personal collection and decks on top.

## Language

### Catalog

**Card**:
One printing of a card name from a specific set — the unit you own and value. Many cards share a name.
_Avoid_: printing (the code's synonym — standardize on "card"), card name

**Card name**:
The shared face of a card, e.g. "Lightning Bolt". Decklists and search reference names, not cards.
_Avoid_: card, face

**Set**:
A release of cards (e.g. "9th Edition") with a set code, a block, and a release date.
_Avoid_: expansion, product

**Rarity**:
A card's scarcity tier within its set: common, uncommon, rare, or mythic.
_Avoid_: tier, level

**Collector number**:
A card's position within its set; the default ordering of a collection.
_Avoid_: slot, position

**Color identity**:
The set of colors in a card's mana cost; used to group cards by color.
_Avoid_: colors

**Mana cost**:
The symbols a card must pay to cast, from which its color identity and level are derived.
_Avoid_: cost, casting cost

**Double-faced card**:
A card with distinct front and back faces (e.g. split, morph) rather than a single face.
_Avoid_: split card, flip card

**Format**:
A game ruleset a card can be legal in, e.g. Standard, Modern, Commander.
_Avoid_: edition, constructible

**Legality**:
Whether a card is allowed in a format — Legal, Banned, or Restricted.
_Avoid_: status

### Your collection

**Collection**:
The cards you own, recorded as quantities per card, foil status, and group.
_Avoid_: inventory, holdings

**Group**:
A named bucket your collection is filed under — either pinned to one set or custom.
_Avoid_: folder, category, pile

**Set group**:
A group pinned to a single set, holding the cards of that set you own.
_Avoid_: set, set bucket

**Custom group**:
A group not tied to a set — a theme, a list, or a deck's cards — that you name and may image yourself.
_Avoid_: folder, list

**My Collection**:
The default group every card starts in. Created automatically and not deletable.
_Avoid_: default collection, home

**Foil**:
A card's foil finish — a variant tracked separately from non-foil.
_Avoid_: shiny, holo

**Non-foil**:
The standard finish of a card, tracked separately from foil.
_Avoid_: regular, base

**Deck**:
A named, formatted list of cards with a main section and an optional sideboard.
_Avoid_: build

**Sideboard**:
The optional section of a deck holding alternate cards, separate from the main deck.
_Avoid_: bench, subs

### Value

**Price**:
A card's market value in one currency (USD or EUR), with a foil and a non-foil figure.
_Avoid_: cost

**Collection value**:
The sum of each owned card's price multiplied by its quantity, shown in the display currency.
_Avoid_: total, portfolio

**Display currency**:
The currency — USD or EUR — you chose to show values in.
_Avoid_: locale

**Price history**:
The record of a card's prices across refreshes.
_Avoid_: price log

**Legality history**:
The record of a card's legality per format across refreshes.
_Avoid_: legality log

### Data sources

**Scryfall**:
The upstream catalog and API the app mirrors for card data, images, prices, and legalities.
_Avoid_: API

**Bulk data**:
Scryfall's full card dataset, pulled by the ELK loader rather than the web app.
_Avoid_: dump, snapshot

**Search index**:
An optional Elasticsearch index mirroring the card catalog for advanced search.
_Avoid_: ELK
