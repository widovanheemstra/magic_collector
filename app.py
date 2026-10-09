import time
import json
import sqlite3
import re
import requests
import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response, stream_with_context
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MTG color symbol mapping
COLOR_SYMBOLS = {'W': 0, 'U': 1, 'B': 2, 'R': 3, 'G': 4}
COLOR_NAMES = ['White', 'Blue', 'Black', 'Red', 'Green']
RARITY_ORDER = {'common': 0, 'uncommon': 1, 'rare': 2, 'mythic': 3}

app = Flask(__name__)

SUPPORTED_CURRENCIES = ('USD', 'EUR')
CURRENCY_SYMBOLS = {'USD': '$', 'EUR': '€'}
SUPPORTED_THEMES = ('light', 'dark', 'system')
DEFAULT_THEME = 'light'


def get_currency():
    """Display currency from settings, falling back to the legacy cookie (default USD)."""
    value = get_setting('currency') or request.cookies.get('currency', 'USD')
    return value if value in SUPPORTED_CURRENCIES else 'USD'


def get_theme():
    """Display theme from settings: light, dark, or system (default light)."""
    value = get_setting('theme', DEFAULT_THEME)
    return value if value in SUPPORTED_THEMES else DEFAULT_THEME


@app.context_processor
def inject_settings():
    currency = get_currency()
    return {
        'currency': currency,
        'currency_symbol': CURRENCY_SYMBOLS[currency],
        'theme': get_theme(),
    }


@app.route('/set_currency/<currency>')
def set_currency(currency):
    """Persist the display currency choice in settings (cookie kept for compatibility)."""
    currency = currency.upper()
    if currency not in SUPPORTED_CURRENCIES:
        currency = 'USD'
    set_setting('currency', currency)
    next_url = request.referrer or url_for('index')
    resp = redirect(next_url)
    resp.set_cookie('currency', currency, max_age=60 * 60 * 24 * 365)
    return resp


@app.route('/set_theme/<theme>')
def set_theme(theme):
    """Persist the display theme choice in settings and return to the referring page."""
    theme = (theme or '').lower()
    if theme not in SUPPORTED_THEMES:
        theme = DEFAULT_THEME
    set_setting('theme', theme)
    return redirect(request.referrer or url_for('index'))


# Top-level destination for each route, used to highlight the sidebar/tab bar.
NAV_ACTIVE_BY_ENDPOINT = {
    'index': 'home',
    'view_collection': 'collection',
    'view_collection_group': 'collection',
    'decks': 'decks',
    'deck_view': 'decks',
    'deck_edit': 'decks',
    'deck_new': 'decks',
    'view_sets': 'sets',
    'view_cards_by_set': 'sets',
    'search_cards': 'search',
    'view_settings': 'settings',
}


def get_sidebar_context():
    """Navigation data for the shell: custom groups (binders) with counts, the
    default group, and collection/deck totals for sidebar badges.

    Returns a dict consumed by _sidebar.html / _tabbar.html.
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.id, g.name, g.image_url,
               COALESCE(SUM(uc.quantity), 0) AS card_count,
               COUNT(DISTINCT uc.card_id) AS unique_count
        FROM collection_groups g
        LEFT JOIN user_collection uc ON uc.group_id = g.id
        WHERE g.set_code IS NULL
        GROUP BY g.id
        ORDER BY g.name COLLATE NOCASE
    ''')
    rows = cursor.fetchall()

    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM user_collection')
    total_cards = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT card_id) FROM user_collection')
    total_unique = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM decks')
    deck_count = cursor.fetchone()[0]
    conn.close()

    binders = []
    default_binder = None
    for r in rows:
        item = {
            'id': r['id'],
            'name': r['name'],
            'image_url': r['image_url'],
            'card_count': r['card_count'],
            'unique_count': r['unique_count'],
        }
        if r['name'] == 'My Collection':
            default_binder = item
        else:
            binders.append(item)

    active_binder_id = None
    if request.endpoint == 'view_collection_group':
        active_binder_id = request.view_args.get('group_id')

    return {
        'sidebar_binders': binders,
        'sidebar_default_binder': default_binder,
        'sidebar_total_cards': total_cards,
        'sidebar_total_unique': total_unique,
        'sidebar_deck_count': deck_count,
        'nav_active': NAV_ACTIVE_BY_ENDPOINT.get(request.endpoint, ''),
        'active_binder_id': active_binder_id,
    }


@app.context_processor
def inject_navigation():
    return get_sidebar_context()

# Tile images (collection groups and decks): pre-bundled choices live in
# GALLERY_DIR (shared), user uploads are saved into their own per-entity folder.
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'gif', 'webp', 'png', 'svg'}
GALLERY_DIR = 'group_gallery'
GROUP_UPLOAD_DIR = 'group_images'
DECK_UPLOAD_DIR = 'deck_images'


def slugify(text):
    """Lowercase, hyphenated slug for use in filenames."""
    slug = re.sub(r'[^a-z0-9]+', '-', text.strip().lower()).strip('-')
    return slug or 'tile'


def save_tile_image(file_storage, upload_dir_name, entity_id, name):
    """Save an uploaded tile image under static/<upload_dir_name>.

    The filename is the entity's name slug plus its id (so a rename doesn't
    orphan the file and two entities with the same name can't collide).
    Returns the static URL, or None if the file extension isn't allowed.
    """
    ext = file_storage.filename.rsplit('.', 1)[-1].lower() if '.' in file_storage.filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    upload_dir = os.path.join(app.static_folder, upload_dir_name)
    os.makedirs(upload_dir, exist_ok=True)

    slug = f'{slugify(name)}-{entity_id}'
    # Remove any previous upload for this entity under a different extension.
    for existing in os.listdir(upload_dir):
        if existing.rsplit('.', 1)[0] == slug:
            os.remove(os.path.join(upload_dir, existing))

    filename = f'{slug}.{ext}'
    file_storage.save(os.path.join(upload_dir, filename))
    return url_for('static', filename=f'{upload_dir_name}/{filename}')


def save_group_image(file_storage, group_id, group_name):
    return save_tile_image(file_storage, GROUP_UPLOAD_DIR, group_id, group_name)


def save_deck_image(file_storage, deck_id, deck_name):
    return save_tile_image(file_storage, DECK_UPLOAD_DIR, deck_id, deck_name)


def parse_mana_cost(mana_cost, colors_json=None):
    """Parse a mana cost string and return a sort key tuple.
    
    Returns (category, color_count, unique_colors, numeric_value, display_name)
    where:
      category: 0=single_color, 1=multi_color, 2=colorless
      color_count: number of unique colors
      unique_colors: sorted list of color symbols
      numeric_value: for colorless cards, the mana cost number
      display_name: human-readable color group name
    """
    if not mana_cost:
        if colors_json:
            try:
                colors_list = json.loads(colors_json)
                if colors_list and len(colors_list) == 1:
                    color = colors_list[0]
                    return (0, 1, [color], 0, COLOR_NAMES[COLOR_SYMBOLS[color]])
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        return (2, 0, [], 0, 'Colorless')
    
    color_symbols = re.findall(r'([WUBRG])', mana_cost)
    unique_colors = sorted(set(color_symbols))
    color_count = len(unique_colors)
    
    if color_count == 1:
        color = unique_colors[0]
        return (0, 1, unique_colors, 0, COLOR_NAMES[COLOR_SYMBOLS[color]])
    elif color_count >= 2:
        display = ' + '.join(COLOR_NAMES[COLOR_SYMBOLS[c]] for c in unique_colors)
        return (1, color_count, unique_colors, 0, display)
    else:
        numeric_match = re.search(r'(\d+)', mana_cost)
        numeric_value = int(numeric_match.group(1)) if numeric_match else 0
        return (2, 0, [], numeric_value, str(numeric_value))


def sort_collection(collection, sort_mode='collector_number'):
    """Sort collection cards by the given mode.
    
    Each card entry is a tuple: (card_data..., quantity, is_foil, added_at, updated_at, price, line_total)
    card_data columns: id(0), name(1), mana_cost(2), cmc(3), type_line(4), oracle_text(5),
      power(6), toughness(7), colors(8), color_identity(9), legalities(10), games(11),
      reserved(12), foil(13), nonfoil(14), finishes(15), oversized(16), promo(17),
      reprint(18), variation(19), set_id(20), set_code(21), set_name(22),
      collector_number(23), rarity(24), artist(25), border_color(26), frame(27),
      full_art(28), textless(29), booster(30), story_spotlight(31), prices(32),
      related_uris(33), purchase_uris(34), image_uris(35), card_faces(36)
    """
    def sort_key(card):
        card_data = card[:37]
        mana_cost = card_data[2]
        colors_json = card_data[9]
        rarity = (RARITY_ORDER.get(card_data[24], 99) if card_data[24] else 99)
        collector = card_data[23] or ''
        
        # Extract numeric prefix from collector number for proper sorting
        # e.g., "A-115" -> ("A", 115), "CH1" -> ("CH", 1), "304" -> ("", 304)
        prefix_match = re.match(r'^([A-Za-z]+)-?', collector)
        if prefix_match:
            prefix = prefix_match.group(1)
            rest = collector[len(prefix):].lstrip('-')
            try:
                num = int(rest) if rest else 0
            except ValueError:
                num = 0
            collector_key = (prefix, num)
        else:
            try:
                num = int(collector) if collector else 0
                collector_key = ('', num)
            except ValueError:
                collector_key = (collector, 0)
        
        if sort_mode == 'color':
            colors_col = card_data[8]  # colors column
            cat, color_count, unique_colors, numeric_val, display = parse_mana_cost(mana_cost, colors_col)
            # Sort by: category → color_count → display_name → rarity → collector_number
            return (cat, color_count, display, rarity, collector_key, card_data[0])
        elif sort_mode == 'rarity':
            # Sort by: rarity → collector_number
            return (rarity, collector_key, card_data[0])
        else:
            # collector_number (default)
            return (collector_key, rarity, card_data[0])
    
    return sorted(collection, key=sort_key)
DATABASE = os.getenv('DATABASE', 'magic_collector.db')


def get_setting(key, default=None):
    """Read a value from the `settings` key/value table, or `default`."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except sqlite3.OperationalError:
        # settings table not created yet (pre-migration database) — treat as unset.
        return default


def set_setting(key, value):
    """Upsert a value in the `settings` key/value table."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO settings (key, value) VALUES (?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        (key, None if value is None else str(value)),
    )
    conn.commit()
    conn.close()

# Scryfall requires a custom User-Agent and an explicit Accept header on every
# request; it rejects the default python-requests User-Agent with a 400
# (subcode "generic_user_agent"). See https://scryfall.com/docs/api.
SCRYFALL_HEADERS = {
    'User-Agent': os.getenv('SCRYFALL_USER_AGENT', 'MagicCollector/1.0'),
    'Accept': 'application/json',
}

# Custom Jinja2 filters
@app.template_filter('from_json')
def from_json_filter(json_string):
    """Convert JSON string to Python object"""
    if json_string:
        try:
            return json.loads(json_string)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}

@app.template_filter('strftime')
def strftime_filter(timestamp, format_string='%Y-%m-%d %H:%M'):
    """Format timestamp string"""
    if timestamp:
        try:
            from datetime import datetime
            # Handle both string and datetime objects
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            else:
                dt = timestamp
            return dt.strftime(format_string)
        except (ValueError, AttributeError):
            return str(timestamp)
    return 'N/A'

MANA_SYMBOL_RE = re.compile(r'\{([^{}]+)\}')


@app.template_filter('mana_symbols')
def mana_symbols_filter(mana_cost):
    """Render '{W}{U}{2}' as Scryfall mana-symbol SVGs (hybrid '{W/U}' -> 'WU')."""
    from markupsafe import Markup
    if not mana_cost:
        return Markup('')
    parts = MANA_SYMBOL_RE.split(mana_cost)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            if part:
                out.append(Markup.escape(part))
        else:
            sym = re.sub(r'[^0-9A-Za-z]', '', part)
            url = f'https://svgs.scryfall.io/card-symbols/{sym}.svg'
            alt_text = '{' + part + '}'
            out.append(Markup(
                f'<img src="{url}" alt="{alt_text}" class="mc-mana" loading="lazy" '
                f'width="20" height="20">'
            ))
    return Markup('').join(out) if out else Markup('')


def parse_optional(json_str):
    """Parse a JSON column into a Python object, or None."""
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


def card_dict_from_row(row, qty_regular=0, qty_foil=0, currency='USD'):
    """Turn a cards-table tuple (c.*) into a dict for the collection views,
    with resolved images, faces and prices for both finishes."""
    image_uris = parse_optional(row[37])
    card_faces = parse_optional(row[38])
    price = price_from_json(row[34], False, currency)
    price_foil = price_from_json(row[34], True, currency)
    line_regular = (price * qty_regular) if price else 0
    line_foil = (price_foil * qty_foil) if price_foil else 0
    return {
        'id': row[0], 'name': row[1], 'mana_cost': row[2], 'cmc': row[3],
        'type_line': row[4], 'oracle_text': row[5], 'power': row[6], 'toughness': row[7],
        'colors': row[8], 'color_identity': row[9], 'legalities': row[10],
        'set_code': row[21], 'set_name': row[22], 'collector_number': row[23],
        'rarity': row[24], 'artist': row[25],
        'image_uris': image_uris, 'card_faces': card_faces,
        'qty_regular': qty_regular, 'qty_foil': qty_foil,
        'price': price, 'price_foil': price_foil,
        'line_total': line_regular + line_foil,
    }


def _collector_key(card):
    """Sort key by collector number (numeric when possible, then raw string)."""
    num = card['collector_number'] or ''
    m = re.match(r'(\d+)', num)
    return (int(m.group(1)) if m else 0, num)


def sort_binder_cards(cards, mode):
    """Sort card dicts by collector_number (default), color, rarity, or price."""
    if mode == 'price':
        return sorted(cards, key=lambda c: (c['line_total'] or 0), reverse=True)
    if mode == 'color':
        def color_key(c):
            colors = parse_optional(c['colors']) or []
            base = _collector_key(c)
            if len(colors) == 1:
                return (0, COLOR_SYMBOLS.get(colors[0], 99), base)
            if len(colors) > 1:
                return (1, 0, base)
            return (2, 0, base)
        return sorted(cards, key=color_key)
    if mode == 'rarity':
        return sorted(cards, key=lambda c: (RARITY_ORDER.get(c['rarity'], 9), _collector_key(c)))
    return sorted(cards, key=_collector_key)

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Create sets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sets (
            id TEXT PRIMARY KEY,
            code TEXT UNIQUE,
            name TEXT,
            set_type TEXT,
            released_at TEXT,
            block_code TEXT,
            block TEXT,
            parent_set_code TEXT,
            card_count INTEGER,
            digital BOOLEAN,
            foil_only BOOLEAN,
            nonfoil_only BOOLEAN,
            scryfall_uri TEXT,
            uri TEXT,
            icon_svg_uri TEXT,
            search_uri TEXT,
            printed_size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create cards table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            name TEXT,
            mana_cost TEXT,
            cmc REAL,
            type_line TEXT,
            oracle_text TEXT,
            power TEXT,
            toughness TEXT,
            colors TEXT,
            color_identity TEXT,
            legalities TEXT,
            games TEXT,
            reserved BOOLEAN,
            foil BOOLEAN,
            nonfoil BOOLEAN,
            finishes TEXT,
            oversized BOOLEAN,
            promo BOOLEAN,
            reprint BOOLEAN,
            variation BOOLEAN,
            set_id TEXT,
            set_code TEXT,
            set_name TEXT,
            collector_number TEXT,
            rarity TEXT,
            artist TEXT,
            border_color TEXT,
            frame TEXT,
            full_art BOOLEAN,
            textless BOOLEAN,
            booster BOOLEAN,
            story_spotlight BOOLEAN,
            edhrec_rank INTEGER,
            penny_rank INTEGER,
            prices TEXT,
            related_uris TEXT,
            purchase_uris TEXT,
            image_uris TEXT,
            card_faces TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (set_id) REFERENCES sets (id)
        )
    ''')
    
    # Create card_legalities_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_legalities_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            format_name TEXT,
            legality_status TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (card_id) REFERENCES cards (id)
        )
    ''')
    
    # Create card_prices_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_prices_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            price_type TEXT,
            price_value TEXT,
            currency TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (card_id) REFERENCES cards (id)
        )
    ''')
    
    # Create user_collection table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            quantity INTEGER DEFAULT 1,
            is_foil BOOLEAN DEFAULT FALSE,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (card_id) REFERENCES cards (id),
            UNIQUE(card_id, is_foil)
        )
    ''')
    
    # Create decks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            format TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create deck_cards table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deck_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER,
            card_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            is_sideboard BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deck_id) REFERENCES decks (id) ON DELETE CASCADE
        )
    ''')
    
    # Add card_faces column if it doesn't exist (migration for existing databases)
    try:
        cursor.execute('ALTER TABLE cards ADD COLUMN card_faces TEXT')
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    # Add image_url column to decks if it doesn't exist (migration for existing databases)
    try:
        cursor.execute('ALTER TABLE decks ADD COLUMN image_url TEXT')
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    # Add image_card_id column to decks if it doesn't exist (cover art pinning)
    try:
        cursor.execute('ALTER TABLE decks ADD COLUMN image_card_id TEXT')
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass

    # Collection groups: every user_collection row belongs to exactly one group.
    # A group is either pinned to a set (set_code non-null, unique) or custom (set_code null).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS collection_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            image_url TEXT,
            set_code TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (set_code) REFERENCES sets (code)
        )
    ''')

    # Ensure the default "My Collection" group exists (id captured for migration below).
    cursor.execute("SELECT id FROM collection_groups WHERE set_code IS NULL AND name = 'My Collection'")
    row = cursor.fetchone()
    if row:
        default_group_id = row[0]
    else:
        cursor.execute("INSERT INTO collection_groups (name) VALUES ('My Collection')")
        default_group_id = cursor.lastrowid

    # Migrate user_collection to include group_id with a new uniqueness constraint.
    # SQLite cannot ALTER constraints, so rebuild the table when group_id is missing.
    cursor.execute("PRAGMA table_info(user_collection)")
    uc_cols = [r[1] for r in cursor.fetchall()]
    if 'group_id' not in uc_cols:
        cursor.execute('''
            CREATE TABLE user_collection_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                card_id TEXT,
                quantity INTEGER DEFAULT 1,
                is_foil BOOLEAN DEFAULT FALSE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (card_id) REFERENCES cards (id),
                FOREIGN KEY (group_id) REFERENCES collection_groups (id) ON DELETE CASCADE,
                UNIQUE(group_id, card_id, is_foil)
            )
        ''')
        cursor.execute(
            'INSERT INTO user_collection_new (id, group_id, card_id, quantity, is_foil, added_at, updated_at) '
            'SELECT id, ?, card_id, quantity, is_foil, added_at, updated_at FROM user_collection',
            (default_group_id,)
        )
        cursor.execute('DROP TABLE user_collection')
        cursor.execute('ALTER TABLE user_collection_new RENAME TO user_collection')

    # Key/value app settings (display currency, theme, default group, sync state).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # Indexes for hot lookup paths (cards by name, deck_cards by deck, etc.)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_name ON cards (name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cards_set_id ON cards (set_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_deck_cards_deck_id ON deck_cards (deck_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_collection_group_id ON user_collection (group_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_collection_card_id ON user_collection (card_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_card_legalities_history_card_id ON card_legalities_history (card_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_card_prices_history_card_id ON card_prices_history (card_id)')

    conn.commit()
    conn.close()



def get_scryfall_sets():
    """Fetch all sets from Scryfall API"""
    try:
        response = requests.get('https://api.scryfall.com/sets', headers=SCRYFALL_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching sets: {e}")
        return None

def get_cards_by_set(set_code):
    """Fetch cards for a specific set from Scryfall API"""
    try:
        url = f'https://api.scryfall.com/cards/search?q=set:{set_code}'
        all_cards = []
        
        while url:
            response = requests.get(url, headers=SCRYFALL_HEADERS, timeout=30)
            response.raise_for_status()
            data = response.json()
            all_cards.extend(data.get('data', []))
            
            # Check if there are more pages
            if data.get('has_more'):
                url = data.get('next_page')
            else:
                url = None
                
        return all_cards
    except requests.RequestException as e:
        print(f"Error fetching cards for set {set_code}: {e}")
        return []

def get_card_from_scryfall(card_id):
    """Fetch a specific card from Scryfall API by ID"""
    try:
        response = requests.get(f'https://api.scryfall.com/cards/{card_id}', headers=SCRYFALL_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching card {card_id} from Scryfall: {e}")
        return None

def store_sets(sets_data):
    """Store sets data in the database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    for set_data in sets_data:
        cursor.execute('''
            INSERT OR REPLACE INTO sets (
                id, code, name, set_type, released_at, block_code, block,
                parent_set_code, card_count, digital, foil_only, nonfoil_only,
                scryfall_uri, uri, icon_svg_uri, search_uri, printed_size
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            set_data.get('id'),
            set_data.get('code'),
            set_data.get('name'),
            set_data.get('set_type'),
            set_data.get('released_at'),
            set_data.get('block_code'),
            set_data.get('block'),
            set_data.get('parent_set_code'),
            set_data.get('card_count'),
            set_data.get('digital', False),
            set_data.get('foil_only', False),
            set_data.get('nonfoil_only', False),
            set_data.get('scryfall_uri'),
            set_data.get('uri'),
            set_data.get('icon_svg_uri'),
            set_data.get('search_uri'),
            set_data.get('printed_size')
        ))
    
    conn.commit()
    conn.close()

def save_legalities_history(cursor, card_id, legalities_data):
    """Save legalities history for a card"""
    if legalities_data and isinstance(legalities_data, dict):
        for format_name, status in legalities_data.items():
            cursor.execute('''
                INSERT INTO card_legalities_history (card_id, format_name, legality_status)
                VALUES (?, ?, ?)
            ''', (card_id, format_name, status))

def save_prices_history(cursor, card_id, prices_data):
    """Save prices history for a card"""
    if prices_data and isinstance(prices_data, dict):
        for price_type, price_value in prices_data.items():
            if price_value is not None:
                # Determine currency based on price type
                currency = 'USD' if 'usd' in price_type.lower() else 'EUR' if 'eur' in price_type.lower() else 'TIX' if 'tix' in price_type.lower() else 'Unknown'
                cursor.execute('''
                    INSERT INTO card_prices_history (card_id, price_type, price_value, currency)
                    VALUES (?, ?, ?, ?)
                ''', (card_id, price_type, str(price_value), currency))

def get_default_group_id():
    """Return the id of the default 'My Collection' group (created in init_db)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM collection_groups WHERE set_code IS NULL AND name = 'My Collection'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_or_create_set_group(set_code):
    """Get or create the collection group pinned to a set. Returns (group_id, created)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM collection_groups WHERE set_code = ?', (set_code,))
    row = cursor.fetchone()
    if row:
        conn.close()
        return row[0], False
    cursor.execute('SELECT name, icon_svg_uri FROM sets WHERE code = ?', (set_code,))
    set_row = cursor.fetchone()
    name = set_row[0] if set_row else set_code.upper()
    icon = set_row[1] if set_row else None
    cursor.execute(
        'INSERT INTO collection_groups (name, image_url, set_code) VALUES (?, ?, ?)',
        (name, icon, set_code)
    )
    group_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return group_id, True

def get_collection_quantity(card_id, is_foil=False, group_id=None):
    """Total quantity of a card across all groups, or scoped to one group."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    if group_id is None:
        cursor.execute(
            'SELECT COALESCE(SUM(quantity), 0) FROM user_collection WHERE card_id = ? AND is_foil = ?',
            (card_id, is_foil)
        )
    else:
        cursor.execute(
            'SELECT quantity FROM user_collection WHERE card_id = ? AND is_foil = ? AND group_id = ?',
            (card_id, is_foil, group_id)
        )
    result = cursor.fetchone()
    conn.close()
    return (result[0] if result else 0) or 0

def get_collection_totals(card_id, group_id=None):
    """Both foil and non-foil quantities for a card (summed across groups by default)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    if group_id is None:
        cursor.execute(
            'SELECT is_foil, COALESCE(SUM(quantity), 0) FROM user_collection WHERE card_id = ? GROUP BY is_foil',
            (card_id,)
        )
    else:
        cursor.execute(
            'SELECT is_foil, quantity FROM user_collection WHERE card_id = ? AND group_id = ?',
            (card_id, group_id)
        )
    results = cursor.fetchall()
    conn.close()

    non_foil = 0
    foil = 0
    for is_foil, quantity in results:
        if is_foil:
            foil = quantity
        else:
            non_foil = quantity
    return non_foil, foil

def add_to_collection(card_id, quantity, is_foil=False, group_id=None):
    """Increment a card's quantity in a group (default: 'My Collection')."""
    if group_id is None:
        group_id = get_default_group_id()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT quantity FROM user_collection WHERE card_id = ? AND is_foil = ? AND group_id = ?',
        (card_id, is_foil, group_id)
    )
    existing = cursor.fetchone()
    if existing:
        new_quantity = existing[0] + quantity
        cursor.execute(
            'UPDATE user_collection SET quantity = ?, updated_at = CURRENT_TIMESTAMP '
            'WHERE card_id = ? AND is_foil = ? AND group_id = ?',
            (new_quantity, card_id, is_foil, group_id)
        )
    else:
        cursor.execute(
            'INSERT INTO user_collection (group_id, card_id, quantity, is_foil) VALUES (?, ?, ?, ?)',
            (group_id, card_id, quantity, is_foil)
        )
    conn.commit()
    conn.close()
    return True

def ensure_in_collection(card_id, is_foil, group_id, min_quantity=1):
    """Insert at min_quantity only if absent. Used for idempotent 'add full set'."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO user_collection (group_id, card_id, quantity, is_foil) VALUES (?, ?, ?, ?)',
        (group_id, card_id, min_quantity, is_foil)
    )
    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return inserted

def update_collection_quantity(card_id, quantity, is_foil=False, group_id=None):
    """Set the exact quantity of a card in a group; quantity<=0 removes the row."""
    if group_id is None:
        group_id = get_default_group_id()
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    if quantity <= 0:
        cursor.execute(
            'DELETE FROM user_collection WHERE card_id = ? AND is_foil = ? AND group_id = ?',
            (card_id, is_foil, group_id)
        )
        conn.commit()
        conn.close()
        return 0
    cursor.execute(
        'INSERT INTO user_collection (group_id, card_id, quantity, is_foil, updated_at) '
        'VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) '
        'ON CONFLICT(group_id, card_id, is_foil) DO UPDATE SET '
        'quantity = excluded.quantity, updated_at = CURRENT_TIMESTAMP',
        (group_id, card_id, quantity, is_foil)
    )
    conn.commit()
    conn.close()
    return quantity

def price_from_json(prices_json, is_foil=False, currency='USD'):
    """Extract the appropriate price from a prices JSON blob (foil/non-foil, USD/EUR)."""
    if not prices_json:
        return None
    currency_key = 'eur' if currency == 'EUR' else 'usd'
    try:
        prices = json.loads(prices_json)
        if is_foil:
            # For foil cards, try the foil price first, then fall back to non-foil
            price = prices.get(f'{currency_key}_foil') or prices.get(currency_key)
        else:
            price = prices.get(currency_key)
        return float(price) if price else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def get_card_price(card_data, is_foil=False, currency='USD'):
    """Extract the appropriate price from card data based on foil status and currency (USD/EUR)"""
    if not card_data or not card_data[34]:  # prices field is at index 34
        return None
    return price_from_json(card_data[34], is_foil, currency)

def store_cards(cards_data, set_code):
    """Store cards data in the database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    for card_data in cards_data:
        # Convert complex fields to JSON strings
        legalities = json.dumps(card_data.get('legalities', {}))
        games = json.dumps(card_data.get('games', []))
        finishes = json.dumps(card_data.get('finishes', []))
        prices = json.dumps(card_data.get('prices', {}))
        related_uris = json.dumps(card_data.get('related_uris', {}))
        purchase_uris = json.dumps(card_data.get('purchase_uris', {}))
        image_uris = json.dumps(card_data.get('image_uris', {}))
        colors = json.dumps(card_data.get('colors', []))
        color_identity = json.dumps(card_data.get('color_identity', []))
        
        card_name = card_data.get('name', '')
        card_oracle_text = card_data.get('oracle_text', '')
        mana_cost = card_data.get('mana_cost', '')
        type_line = card_data.get('type_line', '')


        # Handle card_faces data - store as JSON for better parsing
        card_faces_data = card_data.get('card_faces', [])
        if card_faces_data:
            card_name = card_faces_data[0].get('name', '') + " // " + card_faces_data[1].get('name', '') 
            card_oracle_text = card_faces_data[0].get('oracle_text', '') + " \n//\n " + card_faces_data[1].get('oracle_text', '') 
            mana_cost = card_faces_data[0].get('mana_cost', '') + "  // " + card_faces_data[1].get('mana_cost', '') 
            type_line = card_faces_data[0].get('type_line', '') + " // " + card_faces_data[1].get('type_line', '') 

            # Store card_faces as JSON for better parsing
            card_faces = json.dumps(card_faces_data)
        else:
            # No card_faces data, store as empty string
            card_faces = ''
        
        cursor.execute('''
            INSERT OR REPLACE INTO cards (
                id, name, mana_cost, cmc, type_line, oracle_text, power, toughness,
                colors, color_identity, legalities, games, reserved, foil, nonfoil,
                finishes, oversized, promo, reprint, variation, set_id, set_code,
                set_name, collector_number, rarity, artist, border_color, frame,
                full_art, textless, booster, story_spotlight, edhrec_rank, penny_rank,
                prices, related_uris, purchase_uris, image_uris, card_faces
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            card_data.get('id'),
            card_name,
            mana_cost,
            card_data.get('cmc'),
            type_line,
            card_oracle_text,
            card_data.get('power'),
            card_data.get('toughness'),
            colors,
            color_identity,
            legalities,
            games,
            card_data.get('reserved', False),
            card_data.get('foil', False),
            card_data.get('nonfoil', False),
            finishes,
            card_data.get('oversized', False),
            card_data.get('promo', False),
            card_data.get('reprint', False),
            card_data.get('variation', False),
            card_data.get('set_id'),
            set_code,
            card_data.get('set_name'),
            card_data.get('collector_number'),
            card_data.get('rarity'),
            card_data.get('artist'),
            card_data.get('border_color'),
            card_data.get('frame'),
            card_data.get('full_art', False),
            card_data.get('textless', False),
            card_data.get('booster', False),
            card_data.get('story_spotlight', False),
            card_data.get('edhrec_rank'),
            card_data.get('penny_rank'),
            prices,
            related_uris,
            purchase_uris,
            image_uris,
            card_faces
        ))
        
        # Save legalities and prices history
        card_id = card_data.get('id')
        if card_id:
            save_legalities_history(cursor, card_id, card_data.get('legalities', {}))
            save_prices_history(cursor, card_id, card_data.get('prices', {}))
    
    conn.commit()
    conn.close()

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon for browsers that request it at the site root."""
    return app.send_static_file('favicon.ico')

@app.route('/')
def index():
    """Main page with sets overview"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sets ORDER BY released_at DESC')
    sets = cursor.fetchall()
    
    # Get total cards count
    cursor.execute('SELECT COUNT(*) FROM cards')
    total_cards = cursor.fetchone()[0]
    
    # Get cards in collection count
    cursor.execute('SELECT COUNT(*) FROM user_collection')
    cards_in_collection = cursor.fetchone()[0]
    
    conn.close()
    
    return render_template('index.html', sets=sets, total_cards=total_cards, cards_in_collection=cards_in_collection)

@app.route('/sets')
def view_sets():
    """View all sets with owned/synced stats."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sets ORDER BY released_at DESC')
    raw_sets = cursor.fetchall()

    cursor.execute('''
        SELECT c.set_code, COUNT(DISTINCT c.id) AS owned_unique,
               COALESCE(SUM(uc.quantity), 0) AS owned_qty
        FROM user_collection uc JOIN cards c ON c.id = uc.card_id
        GROUP BY c.set_code
    ''')
    owned_map = {code: (unique, qty) for code, unique, qty in cursor.fetchall()}
    cursor.execute('SELECT set_code, COUNT(*) FROM cards GROUP BY set_code')
    synced_map = dict(cursor.fetchall())
    types = sorted({s[3] for s in raw_sets if s[3]})
    conn.close()

    sets = []
    for s in raw_sets:
        owned_unique, owned_qty = owned_map.get(s[1], (0, 0))
        sets.append({
            'id': s[0], 'code': s[1], 'name': s[2], 'set_type': s[3],
            'released_at': s[4], 'card_count': s[8], 'icon_svg_uri': s[14],
            'foil_only': s[10], 'digital': s[9],
            'owned_unique': owned_unique, 'owned_qty': owned_qty,
            'synced': synced_map.get(s[1], 0),
        })
    return render_template('sets.html', sets=sets, set_types=types)

@app.route('/cards/<set_code>')
def view_cards_by_set(set_code):
    """View cards for a specific set, with per-card ownership and sorting."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sets WHERE code = ?', (set_code,))
    s = cursor.fetchone()
    if not s:
        conn.close()
        return redirect(url_for('view_sets'))
    currency = get_currency()

    cursor.execute('''
        SELECT c.*,
               COALESCE(SUM(CASE WHEN uc.is_foil = 0 THEN uc.quantity ELSE 0 END), 0) AS qty_regular,
               COALESCE(SUM(CASE WHEN uc.is_foil = 1 THEN uc.quantity ELSE 0 END), 0) AS qty_foil
        FROM cards c
        LEFT JOIN user_collection uc ON uc.card_id = c.id
        WHERE c.set_code = ?
        GROUP BY c.id
    ''', (set_code,))
    cards = [card_dict_from_row(row, row[40], row[41], currency) for row in cursor.fetchall()]
    conn.close()

    sort_mode = request.args.get('sort', 'collector')
    if sort_mode not in ('collector', 'name', 'price'):
        sort_mode = 'collector'
    if sort_mode == 'name':
        cards.sort(key=lambda c: c['name'].lower())
    elif sort_mode == 'price':
        cards.sort(key=lambda c: c['price'] or 0, reverse=True)
    else:
        cards.sort(key=_collector_key)

    total_owned = sum(c['qty_regular'] + c['qty_foil'] for c in cards)
    if request.args.get('owned'):
        cards = [c for c in cards if c['qty_regular'] + c['qty_foil'] > 0]

    set_info = {
        'code': s[1], 'name': s[2], 'set_type': s[3], 'released_at': s[4],
        'card_count': s[8], 'icon_svg_uri': s[14], 'digital': s[9],
        'foil_only': s[10], 'nonfoil_only': s[11], 'printed_size': s[16],
    }
    total_owned = sum(c['qty_regular'] + c['qty_foil'] for c in cards)
    return render_template('cards.html', set_info=set_info, cards=cards,
                           total_owned=total_owned, sort_mode=sort_mode)

@app.route('/card/<card_id>')
def view_card_detail(card_id):
    """View detailed information for a specific card"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Get card details
    cursor.execute('SELECT * FROM cards WHERE id = ?', (card_id,))
    card = cursor.fetchone()
    
    # Get set info for this card
    if card:
        cursor.execute('SELECT * FROM sets WHERE code = ?', (card[21],))  # set_code is at index 21
        set_info = cursor.fetchone()
    else:
        set_info = None
    
    # Get collection quantities (both foil and non-foil)
    if card:
        non_foil_qty, foil_qty = get_collection_totals(card_id)
    else:
        non_foil_qty, foil_qty = 0, 0

    currency = get_currency()

    # Per-group ownership for this exact printing (both finishes per group).
    groups_owned = []
    if card:
        cursor.execute('''
            SELECT g.id, g.name, uc.is_foil, uc.quantity
            FROM user_collection uc JOIN collection_groups g ON g.id = uc.group_id
            WHERE uc.card_id = ?
            ORDER BY g.name COLLATE NOCASE
        ''', (card_id,))
        grouped = {}
        for g_id, g_name, is_foil, qty in cursor.fetchall():
            entry = grouped.setdefault(g_id, {'group_id': g_id, 'group_name': g_name, 'regular': 0, 'foil': 0})
            if is_foil:
                entry['foil'] = qty
            else:
                entry['regular'] = qty
        groups_owned = list(grouped.values())

    # All binder groups (custom groups + the default group) for the "Add to" select.
    cursor.execute('''
        SELECT g.id, g.name FROM collection_groups g
        WHERE g.set_code IS NULL
        ORDER BY (g.name = 'My Collection') DESC, g.name COLLATE NOCASE
    ''')
    add_groups = [{'id': g_id, 'name': g_name} for g_id, g_name in cursor.fetchall()]

    # Decks that use this card name (any printing), with main/side totals.
    decks_used = []
    if card:
        card_name = card[1]
        cursor.execute('''
            SELECT d.id, d.name, dc.is_sideboard, COALESCE(SUM(dc.quantity), 0)
            FROM deck_cards dc JOIN decks d ON d.id = dc.deck_id
            WHERE dc.card_name = ?
            GROUP BY d.id, dc.is_sideboard
        ''', (card_name,))
        deck_totals = {}
        for d_id, d_name, is_sideboard, qty in cursor.fetchall():
            entry = deck_totals.setdefault(d_id, {'id': d_id, 'name': d_name, 'main': 0, 'side': 0})
            if is_sideboard:
                entry['side'] = qty
            else:
                entry['main'] = qty
        # Copies owned by this name across the whole collection (any printing, both finishes).
        cursor.execute('''
            SELECT COALESCE(SUM(uc.quantity), 0)
            FROM user_collection uc JOIN cards c ON c.id = uc.card_id
            WHERE c.name = ?
        ''', (card_name,))
        owned_by_name = cursor.fetchone()[0]
        total_required = sum(d['main'] + d['side'] for d in deck_totals.values())
        decks_used = []
        for d in deck_totals.values():
            required = d['main'] + d['side']
            d['owned'] = min(required, owned_by_name)
            d['owned_total'] = owned_by_name
            d['shares'] = total_required > owned_by_name
            decks_used.append(d)

    # Other printings of the same card (same name, different sets) with owned state + price.
    other_printings = []
    if card:
        card_name = card[1]
        cursor.execute('''
            SELECT c.id, c.name, c.set_code, c.collector_number, c.image_uris, c.rarity,
                   c.prices, s.name as set_name, s.released_at
            FROM cards c
            JOIN sets s ON c.set_code = s.code
            WHERE c.name = ? AND c.id != ?
            ORDER BY s.released_at DESC
        ''', (card_name, card_id))
        for row in cursor.fetchall():
            nf, f = get_collection_totals(row[0])
            previous_price = price_from_json(row[6], False, currency)
            other_printings.append({
                'id': row[0], 'name': row[1], 'set_code': row[2],
                'collector_number': row[3], 'image_uris': parse_optional(row[4]),
                'rarity': row[5], 'set_name': row[7], 'released_at': row[8],
                'owned_total': nf + f, 'non_foil_qty': nf, 'foil_qty': f,
                'price': previous_price,
            })

    # Legal formats (chips) + the count of non-legal formats.
    legal_formats = []
    non_legal_formats = []
    if card:
        legalities = parse_optional(card[10]) or {}
        format_order = ['standard', 'pioneer', 'modern', 'legacy', 'vintage', 'commander',
                        'pauper', 'penny', 'brawl', 'future', 'historic', 'gladiator',
                        'premodern', 'predh', 'alchemy', 'explorer', 'duel', 'oldschool']
        for fmt in format_order:
            status = legalities.get(fmt)
            if not status:
                continue
            if status == 'legal':
                legal_formats.append(fmt)
            else:
                non_legal_formats.append((fmt, status))

    # Prices for the three-cell price strip (both currencies).
    prices_blob = card[34] if card else None
    prices_strip = {
        'eur': price_from_json(prices_blob, False, 'EUR'),
        'eur_foil': price_from_json(prices_blob, True, 'EUR'),
        'usd': price_from_json(prices_blob, False, 'USD'),
    }

    # Check if this is a double-sided card and get card_faces data
    card_faces_data = None
    if card and card[38]:  # card_faces field is at index 38
        try:
            # Try to parse as JSON first (new format)
            card_faces_data = json.loads(card[38])
        except (json.JSONDecodeError, TypeError):
            # Fallback for old format - try to parse the old string format
            card_faces_string = card[38]
            if card_faces_string and ' // ' in card_faces_string:
                # Split the faces and create a simple structure for the template
                face_strings = card_faces_string.split(' // ')
                card_faces_data = []
                for i, face_string in enumerate(face_strings):
                    # Parse the face string format: "Name (Type) |IMG:url"
                    image_url = None
                    if ' |IMG:' in face_string:
                        name_type, image_url = face_string.split(' |IMG:', 1)
                    else:
                        name_type = face_string
                    
                    # Extract name and type from "Name (Type)"
                    if ' (' in name_type and name_type.endswith(')'):
                        name = name_type.split(' (')[0]
                        type_line = name_type.split(' (')[1][:-1]  # Remove closing parenthesis
                    else:
                        name = name_type
                        type_line = ''
                    
                    # Create image_uris structure if we have an image URL
                    image_uris = None
                    if image_url:
                        image_uris = {'normal': image_url, 'large': image_url}
                    
                    card_faces_data.append({
                        'name': name,
                        'type_line': type_line,
                        'oracle_text': '',  # We don't store oracle text in the old format
                        'image_uris': image_uris
                    })
    
    conn.close()

    # Determine the "back" target based on where the card was opened from.
    # Originating pages pass a `from` query parameter (plus the relevant id).
    back_url = None
    back_label = None
    from_page = request.args.get('from')
    if from_page == 'collection' and request.args.get('group_id'):
        back_url = url_for('view_collection_group', group_id=request.args.get('group_id'))
        back_label = 'Back to Collection'
    elif from_page == 'deck' and request.args.get('deck_id'):
        back_url = url_for('deck_view', deck_id=request.args.get('deck_id'))
        back_label = 'Back to Deck'
    elif from_page == 'set' and request.args.get('set_code'):
        back_url = url_for('view_cards_by_set', set_code=request.args.get('set_code'))
        back_label = 'Back to Set'

    # Fallback to the card's own set when no origin was provided.
    if not back_url and set_info:
        back_url = url_for('view_cards_by_set', set_code=set_info[1])
        back_label = 'Back to Set'

    scryfall_uri = None
    if card:
        try:
            scryfall_uri = (parse_optional(card[35]) or {}).get('scryfall')
        except Exception:
            scryfall_uri = None
        if not scryfall_uri:
            scryfall_uri = f'https://scryfall.com/cards/{card[21]}/{card[23]}'

    return render_template('card_detail.html',
                           card=card, set_info=set_info,
                           non_foil_qty=non_foil_qty, foil_qty=foil_qty,
                           card_faces_data=card_faces_data,
                           other_printings=other_printings,
                           groups_owned=groups_owned, add_groups=add_groups,
                           decks_used=decks_used,
                           legal_formats=legal_formats, non_legal_formats=non_legal_formats,
                           prices_strip=prices_strip, scryfall_uri=scryfall_uri,
                           back_url=back_url, back_label=back_label)

@app.route('/add_to_collection', methods=['POST'])
def add_to_collection_route():
    """Add cards to collection"""
    data = request.get_json()
    card_id = data.get('card_id')
    quantity = int(data.get('quantity', 1))
    is_foil = data.get('is_foil', False)
    
    if not card_id or quantity <= 0:
        return jsonify({'success': False, 'message': 'Invalid card ID or quantity'})
    
    try:
        add_to_collection(card_id, quantity, is_foil)
        non_foil_qty, foil_qty = get_collection_totals(card_id)
        return jsonify({
            'success': True, 
            'message': f'Added {quantity} {"foil" if is_foil else "non-foil"} card(s) to collection',
            'non_foil_qty': non_foil_qty,
            'foil_qty': foil_qty
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error adding to collection: {str(e)}'})

@app.route('/update_collection_quantity', methods=['POST'])
def update_collection_quantity_route():
    """Update the exact quantity of a card in collection"""
    data = request.get_json()
    card_id = data.get('card_id')
    quantity = int(data.get('quantity', 0))
    is_foil = data.get('is_foil', False)
    group_id = data.get('group_id')

    if not card_id:
        return jsonify({'success': False, 'message': 'Invalid card ID'})

    try:
        new_quantity = update_collection_quantity(card_id, quantity, is_foil, group_id=group_id)
        non_foil_qty, foil_qty = get_collection_totals(card_id)
        group_nf = get_collection_quantity(card_id, False, group_id)
        group_foil = get_collection_quantity(card_id, True, group_id)
        return jsonify({
            'success': True, 
            'message': f'Updated {"foil" if is_foil else "non-foil"} quantity to {new_quantity}',
            'new_quantity': new_quantity,
            'non_foil_qty': non_foil_qty,
            'foil_qty': foil_qty,
            'group_non_foil_qty': group_nf,
            'group_foil_qty': group_foil,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating collection: {str(e)}'})

@app.route('/clear_collection', methods=['POST'])
def clear_collection_route():
    """Clear all cards from the user's collection"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get count before clearing
        cursor.execute('SELECT COUNT(*) FROM user_collection')
        count_before = cursor.fetchone()[0]
        
        # Clear all collection entries
        cursor.execute('DELETE FROM user_collection')
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully cleared {count_before} cards from collection'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error clearing collection: {str(e)}'})

@app.route('/update_collection_prices', methods=['POST'])
def update_collection_prices():
    """Update prices and legality for all cards in the collection.

    Streams newline-delimited JSON progress events so the page can show how
    many cards have been updated so far. Each line is either a ``progress``
    event or a final ``done`` event.
    """
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Get all unique card IDs from the collection
    cursor.execute('SELECT DISTINCT card_id FROM user_collection')
    card_ids = [card_id for (card_id,) in cursor.fetchall()]
    total = len(card_ids)

    def generate():
        updated_count = 0
        error_count = 0

        if not card_ids:
            conn.close()
            yield json.dumps({
                'type': 'done', 'success': False, 'total': 0,
                'updated': 0, 'errors': 0,
                'message': 'No cards in collection to update'
            }) + '\n'
            return

        yield json.dumps({
            'type': 'progress', 'updated': 0, 'errors': 0, 'total': total
        }) + '\n'

        # Scryfall's bulk endpoint accepts up to 75 identifiers per request,
        # so batch the lookups instead of one HTTP request per card.
        for i in range(0, total, 75):
            batch = card_ids[i:i + 75]
            try:
                response = requests.post(
                    'https://api.scryfall.com/cards/collection',
                    json={'identifiers': [{'id': cid} for cid in batch]},
                    headers=SCRYFALL_HEADERS,
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()

                for card_data in result.get('data', []):
                    prices = json.dumps(card_data.get('prices', {}))
                    legalities = json.dumps(card_data.get('legalities', {}))

                    cursor.execute('''
                        UPDATE cards
                        SET prices = ?, legalities = ?
                        WHERE id = ?
                    ''', (prices, legalities, card_data.get('id')))
                    updated_count += 1

                # Any identifiers Scryfall couldn't resolve are reported here.
                error_count += len(result.get('not_found', []))
                conn.commit()

                # Be respectful to the API between batches.
                time.sleep(0.1)

            except Exception as e:
                print(f"Error updating batch starting at {i}: {e}")
                error_count += len(batch)

            yield json.dumps({
                'type': 'progress', 'updated': updated_count,
                'errors': error_count, 'total': total
            }) + '\n'

        conn.close()
        yield json.dumps({
            'type': 'done', 'success': True, 'total': total,
            'updated': updated_count, 'errors': error_count,
            'message': f'Updated prices and legality for {updated_count} cards. '
                       f'{error_count} cards had errors.'
        }) + '\n'

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/collection')
def view_collection():
    """Collection overview: binders (custom groups), the By-set table, and an
    'All cards' flat grid (toggle via ?view=cards)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    currency = get_currency()
    view_mode = request.args.get('view', 'groups')
    if view_mode not in ('groups', 'cards'):
        view_mode = 'groups'

    # Header stats across the whole collection.
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM user_collection')
    total_cards = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT c.name) FROM user_collection uc JOIN cards c ON c.id = uc.card_id')
    total_unique = cursor.fetchone()[0]

    def group_value(group_id):
        cursor.execute('''
            SELECT c.prices, uc.quantity, uc.is_foil
            FROM user_collection uc JOIN cards c ON c.id = uc.card_id
            WHERE uc.group_id = ?
        ''', (group_id,))
        value = 0.0
        for prices_json, qty, is_foil in cursor.fetchall():
            price = price_from_json(prices_json, bool(is_foil), currency)
            if price and qty:
                value += price * qty
        return value

    binders = []
    set_rows = []
    all_cards = []
    total_collection_value = 0

    if view_mode == 'groups':
        cursor.execute('''
            SELECT g.id, g.name, g.image_url,
                   COALESCE(SUM(uc.quantity), 0) AS total_qty,
                   COUNT(DISTINCT uc.card_id) AS unique_count
            FROM collection_groups g
            LEFT JOIN user_collection uc ON uc.group_id = g.id
            WHERE g.set_code IS NULL
            GROUP BY g.id
            ORDER BY g.updated_at DESC
        ''')
        for g_id, name, image_url, total_qty, unique_count in cursor.fetchall():
            value = group_value(g_id) if total_qty else 0
            total_collection_value += value
            binders.append({
                'id': g_id, 'name': name, 'image_url': image_url,
                'unique_count': unique_count, 'total_qty': total_qty, 'value': value,
            })

        # By-set table: cards owned from each set across all groups.
        cursor.execute('''
            SELECT c.set_code, s.name, s.icon_svg_uri, s.released_at, s.card_count,
                   COUNT(DISTINCT c.id) AS owned_unique,
                   COALESCE(SUM(uc.quantity), 0) AS owned_qty
            FROM user_collection uc
            JOIN cards c ON c.id = uc.card_id
            JOIN sets s ON s.code = c.set_code
            GROUP BY c.set_code
            ORDER BY owned_qty DESC
        ''')
        for code, name, icon, released, card_count, owned_unique, owned_qty in cursor.fetchall():
            cursor.execute('''
                SELECT c.prices, uc.quantity, uc.is_foil
                FROM user_collection uc JOIN cards c ON c.id = uc.card_id
                WHERE c.set_code = ?
            ''', (code,))
            value = 0.0
            for prices_json, qty, is_foil in cursor.fetchall():
                price = price_from_json(prices_json, bool(is_foil), currency)
                if price and qty:
                    value += price * qty
            total_collection_value += value
            set_rows.append({
                'code': code, 'name': name, 'icon_svg_uri': icon,
                'released_at': released, 'card_count': card_count,
                'owned_unique': owned_unique, 'owned_qty': owned_qty, 'value': value,
            })
    else:
        cursor.execute('''
            SELECT c.*,
                   COALESCE(SUM(CASE WHEN uc.is_foil = 0 THEN uc.quantity ELSE 0 END), 0) AS qty_regular,
                   COALESCE(SUM(CASE WHEN uc.is_foil = 1 THEN uc.quantity ELSE 0 END), 0) AS qty_foil
            FROM user_collection uc JOIN cards c ON c.id = uc.card_id
            GROUP BY c.id
            ORDER BY c.name, c.collector_number
        ''')
        for row in cursor.fetchall():
            all_cards.append(card_dict_from_row(row, row[40], row[41], currency))
        total_collection_value = sum(c['line_total'] for c in all_cards)

    conn.close()
    default_group_id = get_default_group_id()
    return render_template('collection.html',
                           groups=binders, set_rows=set_rows, all_cards=all_cards,
                           view_mode=view_mode,
                           total_cards=total_cards, total_unique=total_unique,
                           total_collection_value=total_collection_value,
                           default_group_id=default_group_id)

@app.route('/collection/<int:group_id>')
def view_collection_group(group_id):
    """Show all cards in a single collection group (binder)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT g.id, g.name, g.image_url, g.set_code, s.icon_svg_uri
        FROM collection_groups g
        LEFT JOIN sets s ON s.code = g.set_code
        WHERE g.id = ?
    ''', (group_id,))
    g_row = cursor.fetchone()
    if not g_row:
        conn.close()
        return redirect(url_for('view_collection'))

    currency = get_currency()
    cursor.execute('''
        SELECT c.*,
               COALESCE(SUM(CASE WHEN uc.is_foil = 0 THEN uc.quantity ELSE 0 END), 0) AS qty_regular,
               COALESCE(SUM(CASE WHEN uc.is_foil = 1 THEN uc.quantity ELSE 0 END), 0) AS qty_foil
        FROM user_collection uc JOIN cards c ON uc.card_id = c.id
        WHERE uc.group_id = ?
        GROUP BY c.id
    ''', (group_id,))
    cards = [card_dict_from_row(row, row[40], row[41], currency) for row in cursor.fetchall()]
    conn.close()

    total_unique = len(cards)
    total_qty = sum(c['qty_regular'] + c['qty_foil'] for c in cards)
    total_value = sum(c['line_total'] for c in cards)

    sort_mode = request.args.get('sort', 'collector_number')
    if sort_mode not in ('collector_number', 'color', 'rarity', 'price'):
        sort_mode = 'collector_number'
    cards = sort_binder_cards(cards, sort_mode)

    view_style = request.args.get('view', 'grid')
    if view_style not in ('grid', 'list'):
        view_style = 'grid'

    group = {
        'id': g_row[0],
        'name': g_row[1],
        'image_url': g_row[2] or g_row[4],
        'set_code': g_row[3],
        'is_default': g_row[0] == get_default_group_id(),
    }
    return render_template('group_detail.html',
                            group=group,
                            cards=cards,
                            total_unique=total_unique,
                            total_qty=total_qty,
                            total_collection_value=total_value,
                            sort_mode=sort_mode,
                            view_style=view_style)

@app.route('/collection/<int:group_id>/make_deck')
def make_deck_from_group(group_id):
    """Create a deck pre-filled with the binder's cards (by card name, quantities summed)."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM collection_groups WHERE id = ?', (group_id,))
    g = cursor.fetchone()
    if not g:
        conn.close()
        return redirect(url_for('view_collection'))
    cursor.execute('''
        SELECT c.name, SUM(uc.quantity) AS total, MAX(c.image_uris) AS image_uris
        FROM user_collection uc JOIN cards c ON c.id = uc.card_id
        WHERE uc.group_id = ?
        GROUP BY c.name
    ''', (group_id,))
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        return redirect(url_for('view_collection_group', group_id=group_id))

    image_url = None
    for _, _, image_uris in rows:
        parsed = parse_optional(image_uris)
        if parsed and (parsed.get('normal') or parsed.get('large')):
            image_url = parsed.get('normal') or parsed.get('large')
            break

    cursor.execute(
        'INSERT INTO decks (name, description, format, image_url) VALUES (?, ?, ?, ?)',
        (f"Deck: {g[0]}", f'Created from the "{g[0]}" binder.', None, image_url),
    )
    deck_id = cursor.lastrowid
    cursor.executemany(
        'INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard) VALUES (?, ?, ?, ?)',
        [(deck_id, name, qty, 0) for name, qty, _ in rows],
    )
    conn.commit()
    conn.close()
    return redirect(url_for('deck_view', deck_id=deck_id))

@app.route('/search')
def search_cards():
    """Search cards page"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    results = []
    total_results = 0
    total_pages = 0
    
    if query:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Search in card name, type_line, and oracle_text
        search_term = f'%{query}%'
        
        # Get total count
        cursor.execute('''
            SELECT COUNT(*) FROM cards 
            WHERE name LIKE ? OR type_line LIKE ? OR oracle_text LIKE ?
        ''', (search_term, search_term, search_term))
        total_results = cursor.fetchone()[0]
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute('''
            SELECT c.id, c.name, c.mana_cost, c.type_line, c.oracle_text, c.power, c.toughness,
                   c.rarity, c.set_code, c.collector_number, c.image_uris, c.prices,
                   s.name as set_name, s.released_at
            FROM cards c
            LEFT JOIN sets s ON c.set_code = s.code
            WHERE c.name LIKE ? OR c.type_line LIKE ? OR c.oracle_text LIKE ?
            ORDER BY c.name, s.released_at DESC
            LIMIT ? OFFSET ?
        ''', (search_term, search_term, search_term, per_page, offset))
        results = cursor.fetchall()
        
        total_pages = (total_results + per_page - 1) // per_page
        
        conn.close()
    
    return render_template('search.html', 
                         query=query, 
                         results=results, 
                         total_results=total_results,
                         page=page, 
                         per_page=per_page,
                         total_pages=total_pages)

@app.route('/fetch_sets', methods=['POST'])
def fetch_sets():
    """Fetch and store sets from Scryfall API"""
    sets_data = get_scryfall_sets()
    if sets_data and 'data' in sets_data:
        store_sets(sets_data['data'])
        return jsonify({'success': True, 'message': f'Fetched and stored {len(sets_data["data"])} sets'})
    else:
        return jsonify({'success': False, 'message': 'Failed to fetch sets'})

@app.route('/fetch_cards/<set_code>', methods=['POST'])
def fetch_cards(set_code):
    """Fetch and store cards for a specific set"""
    cards_data = get_cards_by_set(set_code)
    if cards_data:
        store_cards(cards_data, set_code)
        return jsonify({'success': True, 'message': f'Fetched and stored {len(cards_data)} cards for set {set_code}'})
    else:
        return jsonify({'success': False, 'message': f'Failed to fetch cards for set {set_code}'})

@app.route('/api/card_names')
def api_card_names():
    """Return up to 8 distinct card names starting with the query (for autocomplete)."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'names': []})
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT DISTINCT name FROM cards WHERE name LIKE ? ORDER BY name LIMIT 8',
        (f'{q}%',),
    )
    names = [r[0] for r in cursor.fetchall()]
    conn.close()
    return jsonify({'names': names})


@app.route('/api/card_by_name')
def api_card_by_name():
    """Return card detail JSON for the most recent printing of a name.

    Used by the deck view to show card details inline. Prefers a printing that
    has an image; otherwise falls back to the most recently added record.
    """
    name = (request.args.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Missing name'}), 400
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, mana_cost, cmc, type_line, oracle_text, power, toughness,
               set_code, set_name, collector_number, rarity, artist,
               legalities, prices, image_uris, card_faces
        FROM cards
        WHERE name = ?
        ORDER BY (image_uris IS NULL OR image_uris = ''), created_at DESC
        LIMIT 1
    ''', (name,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify({'success': False, 'message': f'Card "{name}" is not in the local database'}), 404

    def parse(s):
        if not s:
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            return None

    card = {
        'id': row[0], 'name': row[1], 'mana_cost': row[2], 'cmc': row[3],
        'type_line': row[4], 'oracle_text': row[5], 'power': row[6], 'toughness': row[7],
        'set_code': row[8], 'set_name': row[9], 'collector_number': row[10],
        'rarity': row[11], 'artist': row[12],
        'legalities': parse(row[13]),
        'prices': parse(row[14]),
        'image_uris': parse(row[15]),
        'card_faces': parse(row[16]),
    }
    return jsonify({'success': True, 'card': card})

@app.route('/add_set_to_collection/<set_code>', methods=['POST'])
def add_set_to_collection(set_code):
    """Add 1x of every card in a set to a pinned collection group.

    Auto-fetches cards from Scryfall if they aren't loaded locally yet.
    Idempotent: cards already present in the group are left alone.
    """
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT name, foil_only FROM sets WHERE code = ?', (set_code,))
        set_row = cursor.fetchone()
        conn.close()
        if not set_row:
            return jsonify({'success': False, 'message': f'Set {set_code} not found. Refresh sets first.'})
        foil_only = bool(set_row[1])

        # Ensure cards are loaded locally; auto-fetch from Scryfall if not.
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM cards WHERE set_code = ?', (set_code,))
        card_count = cursor.fetchone()[0]
        conn.close()
        if card_count == 0:
            cards_data = get_cards_by_set(set_code)
            if not cards_data:
                return jsonify({'success': False, 'message': f'No cards available for set {set_code} from Scryfall'})
            store_cards(cards_data, set_code)

        group_id, _created = get_or_create_set_group(set_code)

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM cards WHERE set_code = ?', (set_code,))
        card_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        added = 0
        for card_id in card_ids:
            if ensure_in_collection(card_id, is_foil=foil_only, group_id=group_id, min_quantity=1):
                added += 1

        return jsonify({
            'success': True,
            'group_id': group_id,
            'added': added,
            'already_present': len(card_ids) - added,
            'message': f'Added {added} new card(s) to "{set_row[0]}" group; {len(card_ids) - added} already present.'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error adding set to collection: {str(e)}'})

@app.route('/api/tile_gallery_images')
def api_tile_gallery_images():
    """List project-bundled images available to pick as a group or deck tile image."""
    folder = os.path.join(app.static_folder, GALLERY_DIR)
    images = []
    if os.path.isdir(folder):
        for fname in sorted(os.listdir(folder)):
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext in ALLOWED_IMAGE_EXTENSIONS:
                images.append(url_for('static', filename=f'{GALLERY_DIR}/{fname}'))
    return jsonify({'images': images})

@app.route('/collection_groups', methods=['POST'])
def create_collection_group():
    """Create a custom (non-set) collection group."""
    name = (request.form.get('name') or '').strip()
    image_url = (request.form.get('image_url') or '').strip() or None
    if not name:
        return redirect(url_for('view_collection'))
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO collection_groups (name, image_url) VALUES (?, ?)',
        (name, image_url)
    )
    group_id = cursor.lastrowid
    conn.commit()

    upload = request.files.get('image_file')
    if upload and upload.filename:
        saved_url = save_group_image(upload, group_id, name)
        if saved_url:
            cursor.execute('UPDATE collection_groups SET image_url = ? WHERE id = ?', (saved_url, group_id))
            conn.commit()
    conn.close()
    return redirect(url_for('view_collection_group', group_id=group_id))

@app.route('/collection_groups/<int:group_id>/update', methods=['POST'])
def update_collection_group(group_id):
    """Rename a group or override its image."""
    name = (request.form.get('name') or '').strip()
    image_url = (request.form.get('image_url') or '').strip() or None
    if not name:
        return redirect(url_for('view_collection_group', group_id=group_id))

    upload = request.files.get('image_file')
    if upload and upload.filename:
        saved_url = save_group_image(upload, group_id, name)
        if saved_url:
            image_url = saved_url

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE collection_groups SET name = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (name, image_url, group_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('view_collection_group', group_id=group_id))

@app.route('/collection_groups/<int:group_id>/delete', methods=['POST'])
def delete_collection_group(group_id):
    """Delete a group and all of its collection rows. The default group is protected."""
    default_id = get_default_group_id()
    if group_id == default_id:
        return jsonify({'success': False, 'message': 'The default "My Collection" group cannot be deleted.'}), 400
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_collection WHERE group_id = ?', (group_id,))
    cursor.execute('DELETE FROM collection_groups WHERE id = ?', (group_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Group deleted'})

@app.route('/settings')
def view_settings():
    """Settings page"""
    return render_template('settings.html')

@app.route('/theme-demo')
def view_theme_demo():
    """Theme demo page showing Kaldheim theme"""
    return render_template('theme_demo.html')

@app.route('/get_database_stats')
def get_database_stats():
    """Get database statistics"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get total cards count
        cursor.execute('SELECT COUNT(*) FROM cards')
        total_cards = cursor.fetchone()[0]
        
        # Get total sets count
        cursor.execute('SELECT COUNT(*) FROM sets')
        total_sets = cursor.fetchone()[0]
        
        # Get cards in collection count
        cursor.execute('SELECT COUNT(*) FROM user_collection')
        collection_cards = cursor.fetchone()[0]
        
        # Get total decks count
        cursor.execute('SELECT COUNT(*) FROM decks')
        total_decks = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_cards': total_cards,
                'total_sets': total_sets,
                'collection_cards': collection_cards,
                'total_decks': total_decks
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting database stats: {str(e)}'
        })

def get_deck_value(cursor, deck_id, currency='USD'):
    """Sum of best-printing price x quantity for every card in a deck (main + sideboard)."""
    cursor.execute(
        'SELECT card_name, SUM(quantity) FROM deck_cards WHERE deck_id = ? GROUP BY card_name',
        (deck_id,)
    )
    card_totals = cursor.fetchall()
    prices_by_name = get_best_prices_for_card_names(cursor, [name for name, _ in card_totals], currency)

    total = 0.0
    for card_name, quantity in card_totals:
        price = prices_by_name.get(card_name)
        if price:
            total += price * quantity
    return total


def get_best_prices_for_card_names(cursor, card_names, currency='USD'):
    """Batch-resolve the non-foil price (in the given currency) for the best printing of each card name.

    Avoids one query per card name: a single query pulls every candidate printing
    for the requested names, and the best printing per name (prefer a printing with
    image_uris, then most recently added) is picked in Python.
    """
    unique_names = list(dict.fromkeys(card_names))
    if not unique_names:
        return {}

    prices_by_name = {}
    CHUNK_SIZE = 500  # stay well under SQLite's default bound-parameter limit
    for i in range(0, len(unique_names), CHUNK_SIZE):
        chunk = unique_names[i:i + CHUNK_SIZE]
        placeholders = ','.join('?' for _ in chunk)
        cursor.execute(f'''
            SELECT name, prices, (image_uris IS NULL OR image_uris = '') AS no_image, created_at
            FROM cards
            WHERE name IN ({placeholders})
            ORDER BY name, no_image, created_at DESC
        ''', chunk)

        for name, prices, _no_image, _created_at in cursor.fetchall():
            if name in prices_by_name:
                continue  # already have the best printing for this name (first row per name)
            if not prices:
                continue
            fake_card = [None] * 35
            fake_card[34] = prices
            price = get_card_price(fake_card, False, currency)
            if price:
                prices_by_name[name] = price
    return prices_by_name

@app.route('/decks')
def decks():
    """Display all decks with ownership stats."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get all decks
        cursor.execute('''
            SELECT id, name, description, format, image_url, created_at, updated_at
            FROM decks
            ORDER BY updated_at DESC
        ''')
        decks = cursor.fetchall()

        # Get every deck's cards in one query instead of two round-trips per deck
        cursor.execute('''
            SELECT deck_id, card_name, quantity, is_sideboard
            FROM deck_cards
            ORDER BY deck_id, card_name
        ''')
        main_by_deck = {}
        sideboard_by_deck = {}
        all_card_names = []
        for deck_id, card_name, quantity, is_sideboard in cursor.fetchall():
            bucket = sideboard_by_deck if is_sideboard else main_by_deck
            bucket.setdefault(deck_id, []).append((card_name, quantity))
            all_card_names.append(card_name)

        # Resolve every card's price once instead of once per deck per card
        prices_by_name = get_best_prices_for_card_names(cursor, all_card_names, get_currency())

        # Copies owned per card name across the whole collection (any printing, both finishes)
        cursor.execute('''
            SELECT c.name, COALESCE(SUM(uc.quantity), 0)
            FROM user_collection uc JOIN cards c ON c.id = uc.card_id
            GROUP BY c.name
        ''')
        owned_by_name = dict(cursor.fetchall())

        deck_data = []
        for deck in decks:
            deck_id, name, description, format_name, image_url, created_at, updated_at = deck

            main_deck = main_by_deck.get(deck_id, [])
            sideboard = sideboard_by_deck.get(deck_id, [])

            totals = {}
            for card_name, quantity in main_deck + sideboard:
                totals[card_name] = totals.get(card_name, 0) + quantity
            value = sum(
                prices_by_name[card_name] * quantity
                for card_name, quantity in totals.items()
                if card_name in prices_by_name
            )

            required = sum(totals.values())
            owned_copies = sum(
                min(owned_by_name.get(card_name, 0), quantity)
                for card_name, quantity in totals.items()
            )
            main_total = sum(q for _, q in main_deck)
            side_total = sum(q for _, q in sideboard)
            missing = [n for n in totals if n not in owned_by_name]

            deck_data.append({
                'id': deck_id,
                'name': name,
                'description': description,
                'format': format_name,
                'image_url': image_url,
                'created_at': created_at,
                'updated_at': updated_at,
                'main_deck': main_deck,
                'sideboard': sideboard,
                'value': value,
                'main_total': main_total,
                'side_total': side_total,
                'total_cards': required,
                'owned_copies': owned_copies,
                'missing': missing,
                'pct': (owned_copies / required * 100) if required else 0,
            })

        conn.close()
        
        return render_template('decks.html', decks=deck_data)
        
    except Exception as e:
        return f"Error loading decks: {str(e)}", 500

@app.route('/add_deck', methods=['POST'])
def add_deck():
    """Add a new deck"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        format_name = data.get('format', '').strip()
        main_deck = data.get('main_deck', [])
        sideboard = data.get('sideboard', [])
        
        if not name:
            return jsonify({'success': False, 'message': 'Deck name is required'})
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Insert deck
        cursor.execute('''
            INSERT INTO decks (name, description, format)
            VALUES (?, ?, ?)
        ''', (name, description, format_name))
        
        deck_id = cursor.lastrowid
        
        # Insert main deck cards
        for card in main_deck:
            card_name = card.get('name', '').strip()
            quantity = int(card.get('quantity', 1))
            if card_name:
                cursor.execute('''
                    INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard)
                    VALUES (?, ?, ?, FALSE)
                ''', (deck_id, card_name, quantity))
        
        # Insert sideboard cards
        for card in sideboard:
            card_name = card.get('name', '').strip()
            quantity = int(card.get('quantity', 1))
            if card_name:
                cursor.execute('''
                    INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard)
                    VALUES (?, ?, ?, TRUE)
                ''', (deck_id, card_name, quantity))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Deck added successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error adding deck: {str(e)}'})

@app.route('/delete_deck', methods=['POST'])
def delete_deck():
    """Delete a deck"""
    try:
        data = request.get_json()
        deck_id = data.get('deck_id')
        
        if not deck_id:
            return jsonify({'success': False, 'message': 'Deck ID is required'})
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Delete deck (cascade will delete deck_cards)
        cursor.execute('DELETE FROM decks WHERE id = ?', (deck_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Deck deleted successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting deck: {str(e)}'})

@app.route('/delete_all_decks', methods=['POST'])
def delete_all_decks():
    """Delete all decks"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get count before deleting
        cursor.execute('SELECT COUNT(*) FROM decks')
        count_before = cursor.fetchone()[0]
        
        # Delete all decks (cascade will delete deck_cards)
        cursor.execute('DELETE FROM decks')
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Successfully deleted {count_before} decks from the database'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error deleting decks: {str(e)}'})

def store_single_card(card_data):
    """Store a single card in the database"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Extract basic card information
    card_name = card_data.get('name', '')
    card_oracle_text = card_data.get('oracle_text', '')
    mana_cost = card_data.get('mana_cost', '')
    type_line = card_data.get('type_line', '')

    # Handle card_faces data - store as JSON for better parsing
    card_faces_data = card_data.get('card_faces', [])
    if card_faces_data:
        card_name = card_faces_data[0].get('name', '') + " // " + card_faces_data[1].get('name', '') 
        card_oracle_text = card_faces_data[0].get('oracle_text', '') + " \n//\n " + card_faces_data[1].get('oracle_text', '') 
        mana_cost = card_faces_data[0].get('mana_cost', '') + "  // " + card_faces_data[1].get('mana_cost', '') 
        type_line = card_faces_data[0].get('type_line', '') + " // " + card_faces_data[1].get('type_line', '') 

        # Store card_faces as JSON for better parsing
        card_faces = json.dumps(card_faces_data)
    else:
        # No card_faces data, store as empty string
        card_faces = ''
    
    # Convert other data to JSON strings
    legalities = json.dumps(card_data.get('legalities', {}))
    prices = json.dumps(card_data.get('prices', {}))
    related_uris = json.dumps(card_data.get('related_uris', {}))
    purchase_uris = json.dumps(card_data.get('purchase_uris', {}))
    image_uris = json.dumps(card_data.get('image_uris', {}))
    
    cursor.execute('''
        INSERT OR REPLACE INTO cards (
            id, name, mana_cost, cmc, type_line, oracle_text, power, toughness,
            colors, color_identity, legalities, games, reserved, foil, nonfoil,
            finishes, oversized, promo, reprint, variation, set_id, set_code,
            set_name, collector_number, rarity, artist, border_color, frame,
            full_art, textless, booster, story_spotlight, edhrec_rank, penny_rank,
            prices, related_uris, purchase_uris, image_uris, card_faces
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        card_data.get('id'),
        card_name,
        mana_cost,
        card_data.get('cmc', 0),
        type_line,
        card_oracle_text,
        card_data.get('power'),
        card_data.get('toughness'),
        json.dumps(card_data.get('colors', [])),
        json.dumps(card_data.get('color_identity', [])),
        legalities,
        json.dumps(card_data.get('games', [])),
        card_data.get('reserved', False),
        card_data.get('foil', False),
        card_data.get('nonfoil', False),
        json.dumps(card_data.get('finishes', [])),
        card_data.get('oversized', False),
        card_data.get('promo', False),
        card_data.get('reprint', False),
        card_data.get('variation', False),
        card_data.get('set_id'),
        card_data.get('set'),
        card_data.get('set_name'),
        card_data.get('collector_number'),
        card_data.get('rarity'),
        card_data.get('artist'),
        card_data.get('border_color'),
        card_data.get('frame'),
        card_data.get('full_art', False),
        card_data.get('textless', False),
        card_data.get('booster', False),
        card_data.get('story_spotlight', False),
        card_data.get('edhrec_rank'),
        card_data.get('penny_rank'),
        prices,
        related_uris,
        purchase_uris,
        image_uris,
        card_faces
    ))
    
    # Save legalities and prices history
    card_id = card_data.get('id')
    if card_id:
        save_legalities_history(cursor, card_id, card_data.get('legalities', {}))
        save_prices_history(cursor, card_id, card_data.get('prices', {}))
    
    conn.commit()
    conn.close()

@app.route('/refresh_card/<card_id>')
def refresh_card(card_id):
    """Refresh card data from Scryfall API"""
    try:
        # Get the card from Scryfall API
        card_data = get_card_from_scryfall(card_id)
        if not card_data:
            return "Card not found in Scryfall API", 404
        
        # Store the updated card data
        store_single_card(card_data)
        
        return f"Card {card_id} refreshed successfully. <a href='/card/{card_id}'>View card</a>"
        
    except Exception as e:
        return f"Error refreshing card: {str(e)}", 500

@app.route('/deck/<int:deck_id>')
def deck_view(deck_id):
    """Deck builder: deck header + inline main/sideboard card tables."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, description, format, image_url, created_at, updated_at
            FROM decks
            WHERE id = ?
        ''', (deck_id,))
        deck = cursor.fetchone()

        if not deck:
            conn.close()
            return "Deck not found", 404

        deck_id, name, description, format_name, image_url, created_at, updated_at = deck
        currency = get_currency()
        deck_value = get_deck_value(cursor, deck_id, currency)
        rows = get_deck_card_rows(cursor, deck_id, currency)
        conn.close()

        highlight_missing = [c for c in request.args.get('missing', '').split('|') if c]
        main_cards = [r for r in rows if not r['is_sideboard']]
        side_cards = [r for r in rows if r['is_sideboard']]
        main_total = sum(r['quantity'] for r in main_cards)
        side_total = sum(r['quantity'] for r in side_cards)
        required = main_total + side_total
        owned_copies = sum(min(r['in_collection'], r['quantity']) for r in rows if not r['missing'])
        missing_names = sorted({r['name'] for r in rows if r['missing']})

        deck_data = {
            'id': deck_id,
            'name': name,
            'description': description,
            'format': format_name,
            'image_url': image_url,
            'created_at': created_at,
            'updated_at': updated_at,
            'main_cards': main_cards,
            'side_cards': side_cards,
            'main_total': main_total,
            'side_total': side_total,
            'total_cards': required,
            'unique_cards': len(rows),
            'owned_copies': owned_copies,
            'missing_names': missing_names,
            'value': deck_value,
        }
        return render_template('deck_view.html', deck=deck_data,
                               missing_cards=highlight_missing, currency=currency)

    except Exception as e:
        return f"Error loading deck: {str(e)}", 500

@app.route('/deck/<int:deck_id>/cards', methods=['POST'])
def deck_cards_route(deck_id):
    """Add/update/remove a card row in a deck (main deck or sideboard), by name.

    quantity <= 0 removes the row; otherwise the (name, sideboard) row quantity is set.
    Missing card names are synced from Scryfall before being accepted.
    """
    try:
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        quantity = int(data.get('quantity', 1))
        is_sideboard = bool(data.get('is_sideboard', False))
        if not name:
            return jsonify({'success': False, 'message': 'Card name is required'})

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM decks WHERE id = ?', (deck_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Deck not found'}), 404

        cursor.execute('SELECT COUNT(*) FROM cards WHERE name = ?', (name,))
        if cursor.fetchone()[0] == 0:
            still_missing = sync_missing_cards_from_scryfall([name])
            if still_missing:
                conn.close()
                return jsonify({'success': False, 'message': f'"{name}" not found on Scryfall'})
            cursor.execute('SELECT COUNT(*) FROM cards WHERE name = ?', (name,))

        if quantity <= 0:
            cursor.execute(
                'DELETE FROM deck_cards WHERE deck_id = ? AND card_name = ? AND is_sideboard = ?',
                (deck_id, name, is_sideboard))
        else:
            cursor.execute(
                'UPDATE deck_cards SET quantity = ? WHERE deck_id = ? AND card_name = ? AND is_sideboard = ?',
                (quantity, deck_id, name, is_sideboard))
            if cursor.rowcount == 0:
                cursor.execute(
                    'INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard) VALUES (?, ?, ?, ?)',
                    (deck_id, name, quantity, is_sideboard))

        # Use the first added card's art as the deck cover until the user changes it.
        cursor.execute('SELECT image_url FROM decks WHERE id = ?', (deck_id,))
        if not cursor.fetchone()[0]:
            cursor.execute('''
                SELECT image_uris FROM cards
                WHERE name = ?
                ORDER BY (image_uris IS NULL OR image_uris = ''), created_at DESC LIMIT 1
            ''', (name,))
            pick = cursor.fetchone()
            img = None
            if pick:
                parsed = parse_optional(pick[0]) or {}
                img = parsed.get('art_crop') or parsed.get('normal')
            cursor.execute(
                'UPDATE decks SET image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (img, deck_id))
        else:
            cursor.execute('UPDATE decks SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (deck_id,))
        conn.commit()

        currency = get_currency()
        value = get_deck_value(cursor, deck_id, currency)
        cursor.execute(
            'SELECT COALESCE(SUM(quantity), 0) FROM deck_cards WHERE deck_id = ? AND is_sideboard = FALSE',
            (deck_id,))
        main_total = cursor.fetchone()[0]
        cursor.execute(
            'SELECT COALESCE(SUM(quantity), 0) FROM deck_cards WHERE deck_id = ? AND is_sideboard = TRUE',
            (deck_id,))
        side_total = cursor.fetchone()[0]
        conn.close()
        return jsonify({'success': True, 'main_total': main_total, 'side_total': side_total,
                        'value': value, 'message': 'Saved'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/deck/<int:deck_id>/add_to_collection', methods=['POST'])
def add_deck_to_collection(deck_id):
    """Add every resolvable card in a deck (main + sideboard) to a dedicated custom collection group.

    Reuses (rather than duplicates) the group on repeat calls, so re-adding after editing the
    deck just syncs quantities to the current list. Cards not found locally are synced from
    Scryfall the same way /update_deck does; whatever still can't be found is left out.
    """
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM decks WHERE id = ?', (deck_id,))
        deck_row = cursor.fetchone()
        if not deck_row:
            conn.close()
            return jsonify({'success': False, 'message': 'Deck not found'}), 404
        deck_name = deck_row[0]

        cursor.execute(
            'SELECT card_name, SUM(quantity) FROM deck_cards WHERE deck_id = ? GROUP BY card_name',
            (deck_id,)
        )
        card_totals = cursor.fetchall()
        conn.close()

        if not card_totals:
            return jsonify({'success': False, 'message': 'This deck has no cards to add'})

        missing_set = set(validate_cards_in_database([name for name, _ in card_totals]))
        if missing_set:
            missing_set = set(sync_missing_cards_from_scryfall(list(missing_set)))

        group_name = f'Deck: {deck_name}'
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM collection_groups WHERE set_code IS NULL AND name = ?', (group_name,))
        row = cursor.fetchone()
        if row:
            group_id = row[0]
        else:
            cursor.execute('INSERT INTO collection_groups (name) VALUES (?)', (group_name,))
            group_id = cursor.lastrowid

        added = 0
        for card_name, quantity in card_totals:
            if card_name in missing_set:
                continue
            cursor.execute('''
                SELECT id FROM cards WHERE name = ?
                ORDER BY (image_uris IS NULL OR image_uris = ''), created_at DESC
                LIMIT 1
            ''', (card_name,))
            card_row = cursor.fetchone()
            if not card_row:
                missing_set.add(card_name)
                continue
            card_id = card_row[0]

            cursor.execute(
                'SELECT id FROM user_collection WHERE group_id = ? AND card_id = ? AND is_foil = FALSE',
                (group_id, card_id)
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    'UPDATE user_collection SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (quantity, existing[0])
                )
            else:
                cursor.execute(
                    'INSERT INTO user_collection (group_id, card_id, quantity, is_foil) VALUES (?, ?, ?, FALSE)',
                    (group_id, card_id, quantity)
                )
            added += 1

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'group_id': group_id,
            'group_name': group_name,
            'added': added,
            'missing_cards': sorted(missing_set),
            'message': f'Added {added} card(s) to "{group_name}"'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error adding deck to collection: {str(e)}'})

@app.route('/deck/new')
def deck_new():
    """Create a new (empty) deck and open the builder."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO decks (name, description, format) VALUES ('Untitled deck', NULL, NULL)")
    deck_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return redirect(url_for('deck_view', deck_id=deck_id))

@app.route('/deck/<int:deck_id>/edit')
def deck_edit(deck_id):
    """Editing now happens inline on the builder page."""
    return redirect(url_for('deck_view', deck_id=deck_id))

def get_deck_card_rows(cursor, deck_id, currency='USD'):
    """Rows for the deck builder: per (name, main/side) with best-printing details,
    ownership by name, price and image for the cover thumbnails."""
    cursor.execute('''
        SELECT dc.card_name, dc.quantity, dc.is_sideboard
        FROM deck_cards dc
        WHERE dc.deck_id = ?
        ORDER BY dc.is_sideboard, dc.card_name
    ''', (deck_id,))
    entries = cursor.fetchall()
    if not entries:
        return []
    names = list(dict.fromkeys(n for n, _, _ in entries))
    placeholders = ','.join('?' for _ in names)

    cursor.execute(f'''
        SELECT name, type_line, prices, image_uris
        FROM cards
        WHERE name IN ({placeholders})
        ORDER BY name, (image_uris IS NULL OR image_uris = ''), created_at DESC
    ''', names)
    best = {}
    for name, type_line, prices, image_uris in cursor.fetchall():
        if name in best:
            continue
        img = parse_optional(image_uris) or {}
        best[name] = {
            'name': name,
            'type_line': type_line,
            'price': price_from_json(prices, False, currency),
            'image': img.get('art_crop') or img.get('normal') or img.get('small'),
        }

    cursor.execute(f'''
        SELECT c.name, COALESCE(SUM(uc.quantity), 0)
        FROM user_collection uc JOIN cards c ON c.id = uc.card_id
        WHERE c.name IN ({placeholders})
        GROUP BY c.name
    ''', names)
    owner = dict(cursor.fetchall())

    cursor.execute(f'SELECT DISTINCT name FROM cards WHERE name IN ({placeholders})', names)
    existing = {r[0] for r in cursor.fetchall()}

    rows = []
    for name, quantity, is_sideboard in entries:
        info = best.get(name, {'name': name, 'type_line': '', 'price': None, 'image': None})
        owned = owner.get(name, 0)
        missing = name not in existing
        rows.append({
            'name': name,
            'quantity': quantity,
            'is_sideboard': bool(is_sideboard),
            'type_line': info['type_line'] or 'Unknown',
            'price': info['price'],
            'image': info['image'],
            'in_collection': owned,
            'fully_owned': (not missing) and owned >= quantity,
            'missing': missing,
        })
    return rows

def validate_cards_in_database(card_names):
    """Check if all card names exist in the database"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        missing_cards = []
        for card_name in card_names:
            cursor.execute('SELECT COUNT(*) FROM cards WHERE name = ?', (card_name,))
            count = cursor.fetchone()[0]
            if count == 0:
                missing_cards.append(card_name)
        
        conn.close()
        return missing_cards
        
    except Exception as e:
        print(f"Error validating cards: {e}")
        return card_names  # Return all cards as missing if error

def sync_missing_cards_from_scryfall(card_names):
    """Try to fetch cards not yet in the local database from Scryfall and store them.

    Returns the names that still couldn't be found (invalid names or Scryfall errors).
    """
    still_missing = []
    for i in range(0, len(card_names), 75):
        batch = card_names[i:i + 75]
        try:
            response = requests.post(
                'https://api.scryfall.com/cards/collection',
                json={'identifiers': [{'name': name} for name in batch]},
                headers=SCRYFALL_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            for card_data in result.get('data', []):
                store_single_card(card_data)

            still_missing.extend(item['name'] for item in result.get('not_found', []) if 'name' in item)
        except Exception as e:
            print(f"Error syncing cards from Scryfall: {e}")
            still_missing.extend(batch)

    return still_missing

def parse_decklist_text(text):
    """Parse decklist text into card list"""
    cards = []
    if not text.strip():
        return cards
    
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # Try to parse "quantity cardname" format
        parts = line.split(' ', 1)
        if len(parts) == 2 and parts[0].isdigit():
            try:
                quantity = int(parts[0])
                card_name = parts[1].strip()
                if card_name:
                    cards.append({'name': card_name, 'quantity': quantity})
            except ValueError:
                # If first part isn't a number, treat whole line as card name with qty 1
                cards.append({'name': line, 'quantity': 1})
        else:
            # If no quantity specified, assume 1
            cards.append({'name': line, 'quantity': 1})
    
    return cards

@app.route('/update_deck', methods=['POST'])
def update_deck():
    """Create or update a deck with validation"""
    try:
        data = request.form
        deck_id = data.get('deck_id') or None
        deck_id = int(deck_id) if deck_id else None
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        format_name = data.get('format', '').strip()
        main_deck_text = data.get('main_deck_text', '').strip()
        sideboard_text = data.get('sideboard_text', '').strip()
        image_url = (data.get('image_url') or '').strip() or None

        if not name:
            return jsonify({'success': False, 'message': 'Deck name is required'})

        # Metadata-only save (edit modal): update the header fields, leave cards alone.
        if 'main_deck_text' not in data and 'sideboard_text' not in data:
            if not deck_id:
                return jsonify({'success': False, 'message': 'Deck ID is required'})
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE decks
                SET name = ?, description = ?, format = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (name, description, format_name, image_url, deck_id))
            upload = request.files.get('image_file')
            if upload and upload.filename:
                saved_url = save_deck_image(upload, deck_id, name)
                if saved_url:
                    cursor.execute('UPDATE decks SET image_url = ? WHERE id = ?', (saved_url, deck_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'Deck updated', 'deck_id': deck_id,
                            'missing_cards': []})

        # Parse deck lists
        main_deck = parse_decklist_text(main_deck_text)
        sideboard = parse_decklist_text(sideboard_text)

        # Get all unique card names for validation
        all_card_names = set()
        for card in main_deck + sideboard:
            all_card_names.add(card['name'])

        # Validate cards exist in database, syncing any missing ones from Scryfall
        missing_cards = validate_cards_in_database(list(all_card_names))
        if missing_cards:
            missing_cards = sync_missing_cards_from_scryfall(missing_cards)

        # Drop any cards that still can't be found
        missing_set = set(missing_cards)
        main_deck = [card for card in main_deck if card['name'] not in missing_set]
        sideboard = [card for card in sideboard if card['name'] not in missing_set]

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        if deck_id:
            # Update existing deck
            cursor.execute('''
                UPDATE decks
                SET name = ?, description = ?, format = ?, image_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (name, description, format_name, image_url, deck_id))

            # Delete existing deck cards
            cursor.execute('DELETE FROM deck_cards WHERE deck_id = ?', (deck_id,))
        else:
            # Create new deck
            cursor.execute('''
                INSERT INTO decks (name, description, format, image_url)
                VALUES (?, ?, ?, ?)
            ''', (name, description, format_name, image_url))
            deck_id = cursor.lastrowid

        upload = request.files.get('image_file')
        if upload and upload.filename:
            saved_url = save_deck_image(upload, deck_id, name)
            if saved_url:
                image_url = saved_url
                cursor.execute('UPDATE decks SET image_url = ? WHERE id = ?', (image_url, deck_id))

        # Insert main deck cards
        for card in main_deck:
            cursor.execute('''
                INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard)
                VALUES (?, ?, ?, FALSE)
            ''', (deck_id, card['name'], card['quantity']))
        
        # Insert sideboard cards
        for card in sideboard:
            cursor.execute('''
                INSERT INTO deck_cards (deck_id, card_name, quantity, is_sideboard)
                VALUES (?, ?, ?, TRUE)
            ''', (deck_id, card['name'], card['quantity']))
        
        conn.commit()
        conn.close()
        
        action = 'updated' if data.get('deck_id') else 'created'
        return jsonify({
            'success': True,
            'message': f'Deck {action} successfully',
            'deck_id': deck_id,
            'missing_cards': missing_cards
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving deck: {str(e)}'})

if __name__ == '__main__':
    init_db()

    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
    app.run(debug=debug, host=host, port=port)
