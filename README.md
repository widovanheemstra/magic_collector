# Magic: The Gathering Collector

A comprehensive Python web application for collecting and managing Magic: The Gathering cards using the Scryfall API. This application provides a complete solution for Magic: The Gathering enthusiasts to organize their collection, build decks, and explore card data.

## Features

### Core Functionality
- **Sets Management**: Browse all available Magic: The Gathering sets with details like release dates, card counts, and set types
- **Card Database**: View cards from specific sets with images, mana costs, types, oracle text, and comprehensive card details
- **Collection Management**: Track your personal card collection with foil/non-foil quantities and collection value
- **Deck Building**: Create and manage Magic decks with main deck and sideboard support
- **Advanced Search**: Search through cards by name, type, oracle text, and other attributes
- **Data Storage**: All data is stored locally in a SQLite database for offline access
- **API Integration**: Fetches data from the official Scryfall API with automatic updates
- **Elasticsearch Integration**: Index all MTG cards into Elasticsearch for advanced search and analytics

### Collection Features
- Add/remove cards from your personal collection
- Track both foil and non-foil quantities separately
- View collection value based on current market prices
- Update card prices and legalities from Scryfall API
- Collection statistics and overview

### Deck Building Features
- Create and manage multiple decks
- Support for main deck and sideboard
- Deck validation against your card database
- Collection quantity checking for deck cards
- Deck editing and deletion
- Format specification for each deck

### Search & Discovery
- Full-text search across card names, types, and oracle text
- Paginated search results
- Browse cards by set
- View detailed card information with images
- See other printings of the same card

## Installation

1. Clone or download this repository
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Create a `.env` file to customize configuration (see Configuration section below)

## Configuration

The application supports configuration through environment variables. You can create a `.env` file in the project root to customize settings:

### Environment Variables

Create a `.env` file with the following optional variables:

```env
# Database configuration
DATABASE=magic_collector.db

# Server configuration
HOST=127.0.0.1
PORT=5001
DEBUG=False

# Elasticsearch configuration (for ELK integration)
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200
ELASTICSEARCH_USER=your_user
ELASTICSEARCH_PASSWORD=your_password
ELASTICSEARCH_INDEX=mtg_cards
ELASTICSEARCH_USE_SSL=false
ELASTICSEARCH_VERIFY_CERTS=true
BULK_DELAY_SECONDS=0.1
```

### Configuration Options

- **DATABASE**: SQLite database file path (default: `magic_collector.db`)
- **HOST**: Server host address (default: `127.0.0.1`)
- **PORT**: Server port number (default: `5001`)
- **DEBUG**: Enable debug mode (default: `False`)
- **ELASTICSEARCH_HOST**: Elasticsearch server host (default: `localhost`)
- **ELASTICSEARCH_PORT**: Elasticsearch server port (default: `9200`)
- **ELASTICSEARCH_USER**: Elasticsearch username (optional)
- **ELASTICSEARCH_PASSWORD**: Elasticsearch password (optional)
- **ELASTICSEARCH_INDEX**: Elasticsearch index name for MTG cards (default: `mtg_cards`)
- **ELASTICSEARCH_USE_SSL**: Use HTTPS for Elasticsearch connection (default: `false`)
- **ELASTICSEARCH_VERIFY_CERTS**: Verify SSL certificates (default: `true`)
- **BULK_DELAY_SECONDS**: Delay between bulk indexing operations in seconds (default: `0.1`)

### Example .env File

```env
# Custom database location
DATABASE=/path/to/your/magic_collector.db

# Run on all interfaces
HOST=0.0.0.0
PORT=8080

# Enable debug mode
DEBUG=True
```

If no `.env` file is present, the application will use the default values.

## Usage

1. Run the application:
   ```bash
   python app.py
   ```

2. Open your web browser and navigate to `http://localhost:5001`

3. **Initial Setup**: Click "Fetch All Sets" to load all available Magic sets from the Scryfall API

4. **Browse Data**: 
   - View all sets on the "All Sets" page
   - Click on any set to view its cards
   - Use "Fetch Cards" to load card data for specific sets

5. **Manage Collection**:
   - Add cards to your collection from card detail pages
   - View your collection with current values
   - Update card prices and legalities

6. **Build Decks**:
   - Create and manage multiple decks
   - Add main deck and sideboard cards
   - Check collection quantities for deck cards

7. **Search Cards**:
   - Use the search functionality to find specific cards
   - Search by name, type, or oracle text

8. **Elasticsearch Integration** (Optional):
   - Create Elasticsearch index for advanced search capabilities
   - Load all cards from bulk data into Elasticsearch
   - See "ELK Integration" section below for details

## API Endpoints

### Main Pages
- `/` - Home page with database statistics and recent sets
- `/sets` - View all available sets
- `/cards/<set_code>` - View cards for a specific set
- `/card/<card_id>` - View detailed information for a specific card
- `/collection` - View and manage your personal card collection
- `/search` - Search cards by name, type, or oracle text
- `/decks` - View and manage your decks
- `/deck/<deck_id>` - View individual deck details
- `/deck/new` - Create a new deck
- `/deck/<deck_id>/edit` - Edit an existing deck
- `/settings` - Application settings and database management

### Data Management
- `/fetch_sets` (POST) - Fetch and store all sets from Scryfall API
- `/fetch_cards/<set_code>` (POST) - Fetch and store cards for a specific set
- `/refresh_card/<card_id>` - Refresh individual card data from Scryfall API

### Collection Management
- `/add_to_collection` (POST) - Add cards to your collection
- `/update_collection_quantity` (POST) - Update exact quantity of cards in collection
- `/clear_collection` (POST) - Clear all cards from collection
- `/update_collection_prices` (POST) - Update prices and legalities for all collection cards

### Deck Management
- `/add_deck` (POST) - Add a new deck
- `/update_deck` (POST) - Create or update a deck with validation
- `/delete_deck` (POST) - Delete a deck
- `/delete_all_decks` (POST) - Delete all decks

### API Data Endpoints
- `/get_sets` - Get all sets for dropdown menus
- `/get_set_info/<set_code>` - Get set information including max collector number
- `/get_database_stats` - Get comprehensive database statistics

## Database Schema

The application uses SQLite with the following tables:

### Core Tables
- **sets**: Stores set information (id, code, name, type, release date, card count, etc.)
- **cards**: Stores comprehensive card information (name, mana cost, type, rarity, oracle text, image URLs, prices, legalities, etc.)

### Collection Management
- **user_collection**: Tracks personal card collection (card_id, quantity, foil status, timestamps)
- **card_legalities_history**: Historical tracking of card legalities across formats
- **card_prices_history**: Historical tracking of card prices over time

### Deck Building
- **decks**: Stores deck information (name, description, format, timestamps)
- **deck_cards**: Links decks to cards with quantities and sideboard status

### Key Features
- Foreign key relationships maintain data integrity
- JSON storage for complex data (prices, legalities, image_uris, card_faces)
- Automatic timestamp tracking for all data
- Support for both foil and non-foil card variants
- Historical data tracking for prices and legalities

## ELK Integration

The application includes scripts to index all MTG cards into Elasticsearch for advanced search, analytics, and full-text search capabilities.

### Prerequisites

1. **Elasticsearch Installation**: Ensure Elasticsearch is installed and running
   - Download from [Elasticsearch Downloads](https://www.elastic.co/downloads/elasticsearch)
   - Or use Docker

2. **Configuration**: Add Elasticsearch settings to your `.env` file (see Configuration section)

### ELK Scripts

#### 1. Create Elasticsearch Index

The `create_elk_index.py` script creates an Elasticsearch index with proper mappings for all card fields:

```bash
python create_elk_index.py
```

**What it does:**
- Creates an index named `mtg_cards` (or as specified in `.env`)
- Defines mappings for all card fields from the SQLite `cards` table
- Includes nested mappings for `prices_history` from `card_prices_history` table
- Sets up proper field types (text, keyword, date, nested, etc.)
- Configures analyzers for card name searching

**Features:**
- All card fields indexed (name, mana_cost, type_line, oracle_text, etc.)
- Prices history stored as nested documents
- Support for double-faced cards (card_faces)
- Full-text search capabilities
- Keyword fields for exact matching

#### 2. Load Bulk Data to Elasticsearch

The `load_bulk_cards_to_elk.py` script downloads and indexes all cards from Scryfall's bulk data API:

```bash
python load_bulk_cards_to_elk.py
```

**What it does:**
- Downloads bulk card data from Scryfall API (default_cards dataset)
- Clears all existing documents from the index before loading
- Indexes all cards into Elasticsearch using bulk API
- Processes prices history from current prices
- Provides progress tracking and error handling

**Features:**
- Automatic clearing of existing documents before load
- Bulk indexing for performance (configurable batch size)
- Configurable delay between bulk operations to prevent overwhelming Elasticsearch
- Progress reporting every 10,000 cards
- Error handling and retry logic
- Verification of indexed cards after completion

**Bulk Data Loading:**
- Downloads the complete default_cards dataset from Scryfall
- Processes gzipped JSON data
- Indexes all card fields including:
  - Basic card information (name, mana cost, type, etc.)
  - Prices and prices history
  - Legalities across formats
  - Card images and URIs
  - Double-faced card data
  - Color identity and mana symbols

### Usage Workflow

1. **Start Elasticsearch**: Ensure your Elasticsearch instance is running

2. **Create the Index**:
   ```bash
   python create_elk_index.py
   ```

3. **Load Card Data**:
   ```bash
   python load_bulk_cards_to_elk.py
   ```
   ⚠️ **Warning**: This will download and index ALL cards from Scryfall (hundreds of thousands of cards). This process may take significant time and bandwidth.

4. **Verify**: The script will automatically verify the indexed cards and show statistics

### Index Structure

The Elasticsearch index includes:

- **Card Fields**: All fields from the SQLite `cards` table
- **Prices History**: Nested documents with price_type, price_value, currency, and recorded_at
- **Current Prices**: Object with USD, EUR, TIX prices
- **Card Faces**: Nested array for double-faced cards
- **Legalities**: Object with format names and legality status
- **Images**: Object with various image URI sizes

### Performance Tips

- **Batch Size**: Default is 100 cards per batch. Adjust based on your Elasticsearch cluster size
- **Bulk Delay**: Default is 0.1 seconds. Increase if Elasticsearch is being overwhelmed
- **Index Settings**: The index is created with 1 shard and 0 replicas by default (adjustable in `create_elk_index.py`)

### Troubleshooting

- **Connection Issues**: Check Elasticsearch is running and accessible at the configured host/port
- **SSL Errors**: Set `ELASTICSEARCH_VERIFY_CERTS=false` for self-signed certificates
- **Timeout Errors**: Increase `BULK_DELAY_SECONDS` or reduce batch size
- **Index Not Found**: Run `create_elk_index.py` before loading data

## Data Sources

- [Scryfall API - Sets](https://scryfall.com/docs/api/sets/all)
- [Scryfall API - Cards](https://scryfall.com/docs/api/cards/collector)
- [Scryfall Bulk Data API](https://scryfall.com/docs/api/bulk-data)

## Technologies Used

- **Backend**: Python Flask
- **Database**: SQLite
- **Search Engine**: Elasticsearch (optional, for ELK integration)
- **Frontend**: HTML, Bootstrap 5, Font Awesome
- **API**: Scryfall REST API
- **Data Format**: JSON

## Features in Detail

### Sets Information
- Set name, code, and type
- Release date and card count
- Block information and parent sets
- Digital/foil status
- Set icons and search URIs
- Printed size and card counts

### Cards Information
- Card name and mana cost
- Type line and oracle text
- Power and toughness
- Rarity and collector number
- Artist and border color
- Card images (normal, large, small)
- Current pricing (USD, EUR, TIX)
- Legalities across all formats
- Card faces for double-sided cards
- Color identity and mana symbols
- EDHREC and penny rankings

### Collection Management
- Track foil and non-foil quantities separately
- Real-time collection value calculation
- Add/remove cards with quantity controls
- Collection statistics and overview
- Price history tracking

### Deck Building
- Create unlimited decks with descriptions
- Main deck and sideboard support
- Deck validation against card database
- Collection quantity checking
- Format specification (Standard, Modern, etc.)
- Deck editing and management
- Card name validation

## Notes

- The application fetches data from the Scryfall API on demand
- Data is cached locally in SQLite for faster access and offline use
- Card images are displayed when available from the API
- The application handles pagination for large sets automatically
- Deck building includes validation against your card database
- Historical data tracking for prices and legalities
- Support for double-sided cards and complex card types
- Real-time collection value calculation based on current market prices
- **Elasticsearch Integration**: Optional but recommended for advanced search capabilities and analytics
- Bulk data loading scripts allow you to index all MTG cards for full-text search and complex queries
- Elasticsearch index includes all card fields plus prices history in a single unified index