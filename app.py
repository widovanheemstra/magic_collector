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

def get_card_price(card_data, is_foil=False):
    """Extract the appropriate USD price from card data based on foil status"""
    if not card_data or not card_data[34]:  # prices field is at index 34
        return None
    
    try:
        prices = json.loads(card_data[34])
        if is_foil:
            # For foil cards, try usd_foil first, then fall back to usd
            price = prices.get('usd_foil') or prices.get('usd')
        else:
            # For non-foil cards, use usd price
            price = prices.get('usd')
        
        return float(price) if price else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

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
    """View all sets"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sets ORDER BY released_at DESC')
    sets = cursor.fetchall()
    conn.close()
    
    return render_template('sets.html', sets=sets)

@app.route('/cards/<set_code>')
def view_cards_by_set(set_code):
    """View cards for a specific set"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Get set info
    cursor.execute('SELECT * FROM sets WHERE code = ?', (set_code,))
    set_info = cursor.fetchone()
    
    # Get cards for this set - sort by collector number as number
    cursor.execute('SELECT * FROM cards WHERE set_code = ? ORDER BY CAST(collector_number AS INTEGER)', (set_code,))
    cards = cursor.fetchall()
    
    conn.close()
    
    return render_template('cards.html', set_info=set_info, cards=cards)

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
    
    # Get other printings of the same card (same name, different sets)
    other_printings = []
    if card:
        card_name = card[1]  # name is at index 1
        cursor.execute('''
            SELECT c.id, c.name, c.set_code, c.collector_number, c.image_uris, c.rarity,
                   s.name as set_name, s.released_at
            FROM cards c
            JOIN sets s ON c.set_code = s.code
            WHERE c.name = ? AND c.id != ?
            ORDER BY s.released_at DESC
        ''', (card_name, card_id))
        other_printings = cursor.fetchall()
    
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

    return render_template('card_detail.html', card=card, set_info=set_info, non_foil_qty=non_foil_qty, foil_qty=foil_qty, card_faces_data=card_faces_data, other_printings=other_printings, back_url=back_url, back_label=back_label)

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
        return jsonify({
            'success': True, 
            'message': f'Updated {"foil" if is_foil else "non-foil"} quantity to {new_quantity}',
            'new_quantity': new_quantity,
            'non_foil_qty': non_foil_qty,
            'foil_qty': foil_qty
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
    """List all collection groups with aggregate stats and the global total value."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT g.id, g.name, g.image_url, g.set_code, g.updated_at,
               s.icon_svg_uri,
               COUNT(uc.id) AS rows_in_group,
               COALESCE(SUM(uc.quantity), 0) AS total_qty
        FROM collection_groups g
        LEFT JOIN sets s ON s.code = g.set_code
        LEFT JOIN user_collection uc ON uc.group_id = g.id
        GROUP BY g.id
        ORDER BY (g.set_code IS NULL) DESC, g.updated_at DESC
    ''')
    raw_groups = cursor.fetchall()

    # Per-group value: sum each row's price * quantity.
    groups = []
    total_collection_value = 0
    for g_id, name, image_url, set_code, updated_at, set_icon, row_count, total_qty in raw_groups:
        cursor.execute('''
            SELECT c.prices, uc.quantity, uc.is_foil
            FROM user_collection uc JOIN cards c ON c.id = uc.card_id
            WHERE uc.group_id = ?
        ''', (g_id,))
        group_value = 0.0
        for prices_json, qty, is_foil in cursor.fetchall():
            # Reuse get_card_price by faking a card_data tuple with prices at index 34.
            fake = [None] * 35
            fake[34] = prices_json
            price = get_card_price(fake, bool(is_foil))
            if price and qty:
                group_value += price * qty
        total_collection_value += group_value
        groups.append({
            'id': g_id,
            'name': name,
            'image_url': image_url or set_icon,
            'set_code': set_code,
            'updated_at': updated_at,
            'row_count': row_count,
            'total_qty': total_qty,
            'value': group_value,
        })

    conn.close()
    default_group_id = get_default_group_id()
    return render_template('collection.html', groups=groups,
                           total_collection_value=total_collection_value,
                           default_group_id=default_group_id)

@app.route('/collection/<int:group_id>')
def view_collection_group(group_id):
    """Show all cards in a single collection group."""
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

    cursor.execute('''
        SELECT c.*, uc.quantity, uc.is_foil, uc.added_at, uc.updated_at
        FROM user_collection uc JOIN cards c ON uc.card_id = c.id
        WHERE uc.group_id = ?
        ORDER BY uc.updated_at DESC
    ''', (group_id,))
    collection = cursor.fetchall()
    conn.close()

    collection_with_prices = []
    total_value = 0
    for card_data in collection:
        price = get_card_price(card_data, card_data[41])
        quantity = card_data[40]
        line_total = price * quantity if price and quantity else None
        collection_with_prices.append((*card_data, price, line_total))
        if line_total:
            total_value += line_total

    # Apply sorting based on query parameter
    sort_mode = request.args.get('sort', 'collector_number')
    if sort_mode not in ('color', 'rarity', 'collector_number'):
        sort_mode = 'collector_number'
    collection_sorted = sort_collection(collection_with_prices, sort_mode)

    group = {
        'id': g_row[0],
        'name': g_row[1],
        'image_url': g_row[2] or g_row[4],
        'set_code': g_row[3],
        'is_default': g_row[0] == get_default_group_id(),
    }
    return render_template('group_detail.html',
                            group=group,
                            collection=collection_sorted,
                            total_collection_value=total_value,
                            sort_mode=sort_mode)

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
    conn.close()
    return redirect(url_for('view_collection_group', group_id=group_id))

@app.route('/collection_groups/<int:group_id>/update', methods=['POST'])
def update_collection_group(group_id):
    """Rename a group or override its image."""
    name = (request.form.get('name') or '').strip()
    image_url = (request.form.get('image_url') or '').strip() or None
    if not name:
        return redirect(url_for('view_collection_group', group_id=group_id))
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

@app.route('/decks')
def decks():
    """Display all decks"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get all decks
        cursor.execute('''
            SELECT id, name, description, format, created_at, updated_at
            FROM decks
            ORDER BY updated_at DESC
        ''')
        decks = cursor.fetchall()
        
        # Get deck cards for each deck
        deck_data = []
        for deck in decks:
            deck_id, name, description, format_name, created_at, updated_at = deck
            
            # Get main deck cards
            cursor.execute('''
                SELECT card_name, quantity
                FROM deck_cards
                WHERE deck_id = ? AND is_sideboard = FALSE
                ORDER BY card_name
            ''', (deck_id,))
            main_deck = cursor.fetchall()
            
            # Get sideboard cards
            cursor.execute('''
                SELECT card_name, quantity
                FROM deck_cards
                WHERE deck_id = ? AND is_sideboard = TRUE
                ORDER BY card_name
            ''', (deck_id,))
            sideboard = cursor.fetchall()
            
            deck_data.append({
                'id': deck_id,
                'name': name,
                'description': description,
                'format': format_name,
                'created_at': created_at,
                'updated_at': updated_at,
                'main_deck': main_deck,
                'sideboard': sideboard
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
    """View individual deck details"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get deck info
        cursor.execute('''
            SELECT id, name, description, format, created_at, updated_at
            FROM decks
            WHERE id = ?
        ''', (deck_id,))
        deck = cursor.fetchone()
        
        if not deck:
            return "Deck not found", 404
        
        deck_id, name, description, format_name, created_at, updated_at = deck
        
        # Get main deck cards
        cursor.execute('''
            SELECT card_name, quantity
            FROM deck_cards
            WHERE deck_id = ? AND is_sideboard = FALSE
            ORDER BY card_name
        ''', (deck_id,))
        main_deck = cursor.fetchall()
        
        # Get sideboard cards
        cursor.execute('''
            SELECT card_name, quantity
            FROM deck_cards
            WHERE deck_id = ? AND is_sideboard = TRUE
            ORDER BY card_name
        ''', (deck_id,))
        sideboard = cursor.fetchall()
        
        # Check collection quantities for each card
        def get_collection_quantity(card_name):
            cursor.execute('''
                SELECT SUM(quantity) FROM user_collection uc
                JOIN cards c ON uc.card_id = c.id
                WHERE c.name = ?
            ''', (card_name,))
            result = cursor.fetchone()
            return result[0] if result[0] else 0
        
        # Add collection quantities to main deck
        main_deck_with_collection = []
        for card_name, quantity in main_deck:
            collection_qty = get_collection_quantity(card_name)
            main_deck_with_collection.append({
                'name': card_name,
                'quantity': quantity,
                'in_collection': collection_qty
            })
        
        # Add collection quantities to sideboard
        sideboard_with_collection = []
        for card_name, quantity in sideboard:
            collection_qty = get_collection_quantity(card_name)
            sideboard_with_collection.append({
                'name': card_name,
                'quantity': quantity,
                'in_collection': collection_qty
            })
        
        conn.close()
        
        deck_data = {
            'id': deck_id,
            'name': name,
            'description': description,
            'format': format_name,
            'created_at': created_at,
            'updated_at': updated_at,
            'main_deck': main_deck_with_collection,
            'sideboard': sideboard_with_collection
        }
        
        return render_template('deck_view.html', deck=deck_data)
        
    except Exception as e:
        return f"Error loading deck: {str(e)}", 500

@app.route('/deck/new')
def deck_new():
    """Create new deck page"""
    deck_data = {
        'id': None,
        'name': '',
        'description': '',
        'format': '',
        'created_at': '',
        'updated_at': '',
        'main_deck_text': '',
        'sideboard_text': ''
    }
    return render_template('deck_edit.html', deck=deck_data)

@app.route('/deck/<int:deck_id>/edit')
def deck_edit(deck_id):
    """Edit deck page"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Get deck info
        cursor.execute('''
            SELECT id, name, description, format, created_at, updated_at
            FROM decks
            WHERE id = ?
        ''', (deck_id,))
        deck = cursor.fetchone()
        
        if not deck:
            return "Deck not found", 404
        
        deck_id, name, description, format_name, created_at, updated_at = deck
        
        # Get main deck cards
        cursor.execute('''
            SELECT card_name, quantity
            FROM deck_cards
            WHERE deck_id = ? AND is_sideboard = FALSE
            ORDER BY card_name
        ''', (deck_id,))
        main_deck = cursor.fetchall()
        
        # Get sideboard cards
        cursor.execute('''
            SELECT card_name, quantity
            FROM deck_cards
            WHERE deck_id = ? AND is_sideboard = TRUE
            ORDER BY card_name
        ''', (deck_id,))
        sideboard = cursor.fetchall()
        
        conn.close()
        
        # Format cards for text areas
        main_deck_text = '\n'.join([f"{qty} {name}" for name, qty in main_deck])
        sideboard_text = '\n'.join([f"{qty} {name}" for name, qty in sideboard])
        
        deck_data = {
            'id': deck_id,
            'name': name,
            'description': description,
            'format': format_name,
            'created_at': created_at,
            'updated_at': updated_at,
            'main_deck_text': main_deck_text,
            'sideboard_text': sideboard_text
        }
        
        return render_template('deck_edit.html', deck=deck_data)
        
    except Exception as e:
        return f"Error loading deck for edit: {str(e)}", 500

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
        data = request.get_json()
        deck_id = data.get('deck_id')
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        format_name = data.get('format', '').strip()
        main_deck_text = data.get('main_deck_text', '').strip()
        sideboard_text = data.get('sideboard_text', '').strip()
        
        if not name:
            return jsonify({'success': False, 'message': 'Deck name is required'})
        
        # Parse deck lists
        main_deck = parse_decklist_text(main_deck_text)
        sideboard = parse_decklist_text(sideboard_text)
        
        # Get all unique card names for validation
        all_card_names = set()
        for card in main_deck + sideboard:
            all_card_names.add(card['name'])
        
        # Validate cards exist in database
        missing_cards = validate_cards_in_database(list(all_card_names))
        if missing_cards:
            return jsonify({
                'success': False, 
                'message': f'Cards not found in database: {", ".join(missing_cards)}'
            })
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        if deck_id:
            # Update existing deck
            cursor.execute('''
                UPDATE decks 
                SET name = ?, description = ?, format = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (name, description, format_name, deck_id))
            
            # Delete existing deck cards
            cursor.execute('DELETE FROM deck_cards WHERE deck_id = ?', (deck_id,))
        else:
            # Create new deck
            cursor.execute('''
                INSERT INTO decks (name, description, format)
                VALUES (?, ?, ?)
            ''', (name, description, format_name))
            deck_id = cursor.lastrowid
        
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
        return jsonify({'success': True, 'message': f'Deck {action} successfully', 'deck_id': deck_id})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error saving deck: {str(e)}'})

if __name__ == '__main__':
    init_db()

    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
    app.run(debug=debug, host=host, port=port)
