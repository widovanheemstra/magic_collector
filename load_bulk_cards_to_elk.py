#!/usr/bin/env python3
"""
Magic Collector - Load Bulk Cards to ELK Script
This script loads all cards using Scryfall's bulk data API and indexes them into Elasticsearch.
Based on load_bulk_cards.py but modified to index into Elasticsearch instead of SQLite.
"""

import requests
import json
import os
import gzip
import time
from datetime import datetime
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# Load environment variables from .env file
load_dotenv()

# Elasticsearch configuration
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'localhost')
ELASTICSEARCH_PORT = int(os.getenv('ELASTICSEARCH_PORT', 9200))
ELASTICSEARCH_USER = os.getenv('ELASTICSEARCH_USER', None)
ELASTICSEARCH_PASSWORD = os.getenv('ELASTICSEARCH_PASSWORD', None)
ELASTICSEARCH_INDEX = os.getenv('ELASTICSEARCH_INDEX', 'mtg_cards')
BULK_DELAY_SECONDS = float(os.getenv('BULK_DELAY_SECONDS', '0.1'))  # Delay between bulk operations in seconds

# Scryfall rejects the default python-requests User-Agent with a 400; send a
# custom User-Agent and explicit Accept header on every request.
SCRYFALL_HEADERS = {
    'User-Agent': os.getenv('SCRYFALL_USER_AGENT', 'MagicCollector/1.0'),
    'Accept': 'application/json',
}

def create_elasticsearch_client():
    """Create and return an Elasticsearch client"""
    # Check if SSL is required (https)
    use_ssl = os.getenv('ELASTICSEARCH_USE_SSL', 'false').lower() == 'true'
    verify_certs = os.getenv('ELASTICSEARCH_VERIFY_CERTS', 'true').lower() == 'true'
    protocol = 'https' if use_ssl else 'http'
    
    # Build the connection URL
    connection_url = f'{protocol}://{ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}'
    
    # Base configuration
    es_config = {
        'hosts': [connection_url],
        'request_timeout': 30,
        'max_retries': 10,
        'retry_on_timeout': True
    }
    
    # SSL configuration
    if use_ssl and not verify_certs:
        es_config['verify_certs'] = False
        es_config['ssl_show_warn'] = False
    
    # Authentication
    if ELASTICSEARCH_USER and ELASTICSEARCH_PASSWORD:
        es_config['basic_auth'] = (ELASTICSEARCH_USER, ELASTICSEARCH_PASSWORD)
    
    es = Elasticsearch(
        [connection_url],
        basic_auth=(ELASTICSEARCH_USER, ELASTICSEARCH_PASSWORD),
        verify_certs=False,
        ssl_show_warn=False
    )
    return es

def get_bulk_data_info():
    """Get bulk data information from Scryfall API"""
    try:
        response = requests.get('https://api.scryfall.com/bulk-data', headers=SCRYFALL_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching bulk data info: {e}")
        return None

def get_default_cards_download_url():
    """Get the download URL for default cards bulk data"""
    bulk_data = get_bulk_data_info()
    if not bulk_data:
        return None
    
    # Find the default_cards entry
    for data_type in bulk_data.get('data', []):
        if data_type.get('type') == 'default_cards':
            return data_type.get('download_uri')
    
    print("Default cards bulk data not found")
    return None

def prepare_prices_history(prices_data):
    """Prepare prices history data from prices field for Elasticsearch"""
    prices_history = []
    if prices_data and isinstance(prices_data, dict):
        current_time = datetime.utcnow().isoformat()
        for price_type, price_value in prices_data.items():
            if price_value is not None:
                try:
                    price_float = float(price_value)
                    # Determine currency based on price type
                    currency = 'USD' if 'usd' in price_type.lower() else 'EUR' if 'eur' in price_type.lower() else 'TIX' if 'tix' in price_type.lower() else 'Unknown'
                    
                    prices_history.append({
                        'price_type': price_type,
                        'price_value': price_float,
                        'currency': currency,
                        'recorded_at': current_time
                    })
                except (ValueError, TypeError):
                    # Skip invalid price values
                    continue
    return prices_history

def prepare_card_document(card_data):
    """Prepare a card document for Elasticsearch indexing"""
    try:
        # Handle card_faces data
        card_faces_data = card_data.get('card_faces', [])
        if card_faces_data:
            card_name = card_faces_data[0].get('name', '') + " // " + card_faces_data[1].get('name', '')
            card_oracle_text = card_faces_data[0].get('oracle_text', '') + " \n//\n " + card_faces_data[1].get('oracle_text', '')
            mana_cost = card_faces_data[0].get('mana_cost', '') + "  // " + card_faces_data[1].get('mana_cost', '')
            type_line = card_faces_data[0].get('type_line', '') + " // " + card_faces_data[1].get('type_line', '')
        else:
            card_name = card_data.get('name', '')
            card_oracle_text = card_data.get('oracle_text', '')
            mana_cost = card_data.get('mana_cost', '')
            type_line = card_data.get('type_line', '')
            card_faces_data = []
        
        # Prepare prices history from current prices
        prices_data = card_data.get('prices', {})
        prices_history = prepare_prices_history(prices_data)
        
        # Prepare prices object (current prices)
        prices_obj = {}
        if prices_data:
            for price_type, price_value in prices_data.items():
                if price_value is not None:
                    try:
                        prices_obj[price_type] = float(price_value)
                    except (ValueError, TypeError):
                        pass
        
        # Build the document
        doc = {
            'id': card_data.get('id'),
            'name': card_name,
            'mana_cost': mana_cost,
            'cmc': card_data.get('cmc'),
            'type_line': type_line,
            'oracle_text': card_oracle_text,
            'power': card_data.get('power'),
            'toughness': card_data.get('toughness'),
            'colors': card_data.get('colors', []),
            'color_identity': card_data.get('color_identity', []),
            'legalities': card_data.get('legalities', {}),
            'games': card_data.get('games', []),
            'finishes': card_data.get('finishes', []),
            'reserved': card_data.get('reserved', False),
            'foil': card_data.get('foil', False),
            'nonfoil': card_data.get('nonfoil', False),
            'oversized': card_data.get('oversized', False),
            'promo': card_data.get('promo', False),
            'reprint': card_data.get('reprint', False),
            'variation': card_data.get('variation', False),
            'set_id': card_data.get('set_id'),
            'set_code': card_data.get('set', ''),
            'set_name': card_data.get('set_name'),
            'collector_number': card_data.get('collector_number'),
            'rarity': card_data.get('rarity'),
            'artist': card_data.get('artist'),
            'border_color': card_data.get('border_color'),
            'frame': card_data.get('frame'),
            'full_art': card_data.get('full_art', False),
            'textless': card_data.get('textless', False),
            'booster': card_data.get('booster', False),
            'story_spotlight': card_data.get('story_spotlight', False),
            'edhrec_rank': card_data.get('edhrec_rank'),
            'penny_rank': card_data.get('penny_rank'),
            'prices': prices_obj,
            'prices_history': prices_history,
            'related_uris': card_data.get('related_uris', {}),
            'purchase_uris': card_data.get('purchase_uris', {}),
            'image_uris': card_data.get('image_uris', {}),
            'card_faces': card_faces_data,
            'created_at': card_data.get('released_at') or datetime.utcnow().isoformat(),
            'indexed_at': datetime.utcnow().isoformat()
        }
        
        return doc
        
    except Exception as e:
        print(f"Error preparing card document {card_data.get('name', 'unknown')}: {e}")
        return None

def clear_all_documents(es, index_name):
    """Clear all documents from the Elasticsearch index"""
    try:
        print(f"\n🗑️  Clearing all documents from index '{index_name}'...")
        
        # Delete all documents using delete_by_query
        query = {
            "query": {
                "match_all": {}
            }
        }
        
        result = es.delete_by_query(index=index_name, body=query, wait_for_completion=True)
        deleted_count = result.get('deleted', 0)
        
        # Refresh the index
        es.indices.refresh(index=index_name)
        
        print(f"✅ Cleared {deleted_count} documents from index '{index_name}'")
        return True
        
    except Exception as e:
        print(f"❌ Error clearing documents: {e}")
        return False

def index_cards_bulk(es, cards_data, batch_size=100):
    """Index cards into Elasticsearch using bulk API"""
    success_count = 0
    error_count = 0
    batch_number = 0
    
    def generate_actions():
        """Generator function for bulk indexing"""
        for card_data in cards_data:
            doc = prepare_card_document(card_data)
            if doc and doc.get('id'):
                yield {
                    '_index': ELASTICSEARCH_INDEX,
                    '_id': doc['id'],
                    '_source': doc
                }
    
    # Process in batches
    actions = []
    for action in generate_actions():
        actions.append(action)
        
        if len(actions) >= batch_size:
            batch_number += 1
            try:
                success, failed = bulk(es, actions, raise_on_error=False)
                success_count += success
                error_count += len(failed) if failed else 0
                
                if success_count % 10000 == 0:
                    print(f"  Indexed {success_count} cards...")
                elif batch_number % 10 == 0:
                    print(f"  Processed {batch_number} batches ({success_count} cards indexed)...")
                
                # Add delay between bulk operations
                if BULK_DELAY_SECONDS > 0:
                    time.sleep(BULK_DELAY_SECONDS)
                    
            except Exception as e:
                print(f"Error in bulk indexing batch: {e}")
                error_count += len(actions)
            
            actions = []
    
    # Index remaining actions
    if actions:
        batch_number += 1
        try:
            success, failed = bulk(es, actions, raise_on_error=False)
            success_count += success
            error_count += len(failed) if failed else 0
        except Exception as e:
            print(f"Error in final bulk indexing batch: {e}")
            error_count += len(actions)
    
    return success_count, error_count

def download_and_process_bulk_data():
    """Download and process the bulk data and index into Elasticsearch"""
    print("🚀 Magic Collector - Load Bulk Cards to ELK Script")
    print("=" * 60)
    
    start_time = datetime.now()
    
    try:
        # Connect to Elasticsearch
        print(f"🔌 Connecting to Elasticsearch at {ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}...")
        try:
            es = create_elasticsearch_client()
            
            # Test connection with better error handling
            try:
                if not es.ping():
                    print("❌ Could not connect to Elasticsearch. The server did not respond to ping.")
                    print(f"   Check if Elasticsearch is running at {ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}")
                    return False
            except Exception as ping_error:
                print(f"❌ Connection error: {ping_error}")
                print(f"   Failed to connect to {ELASTICSEARCH_HOST}:{ELASTICSEARCH_PORT}")
                print("\n💡 Troubleshooting:")
                print("   1. Verify Elasticsearch is running")
                print("   2. Check if the host and port are correct")
                print("   3. Check firewall/network settings")
                print("   4. If using SSL, set ELASTICSEARCH_USE_SSL=true in .env")
                print("   5. If using self-signed cert, set ELASTICSEARCH_VERIFY_CERTS=false")
                return False
        except Exception as e:
            print(f"❌ Error creating Elasticsearch client: {e}")
            return False
        
        # Check if index exists
        if not es.indices.exists(index=ELASTICSEARCH_INDEX):
            print(f"❌ Index '{ELASTICSEARCH_INDEX}' does not exist.")
            print("💡 Please run 'create_elk_index.py' first to create the index.")
            return False
        
        print(f"✅ Connected to Elasticsearch (index: {ELASTICSEARCH_INDEX})")
        
        # Clear all existing documents from the index
        if not clear_all_documents(es, ELASTICSEARCH_INDEX):
            print("⚠️  Warning: Could not clear existing documents. Continuing anyway...")
        
        # Get the download URL
        print("\n📡 Getting bulk data information...")
        download_url = get_default_cards_download_url()
        if not download_url:
            print("❌ Could not get download URL for default cards")
            return False
        
        print(f"📥 Download URL: {download_url}")
        
        # Download the bulk data
        print("\n📥 Downloading bulk data (this may take a while)...")
        response = requests.get(download_url, headers=SCRYFALL_HEADERS, stream=True)
        response.raise_for_status()
        
        # Get file size for progress tracking
        total_size = int(response.headers.get('content-length', 0))
        print(f"📊 File size: {total_size / (1024*1024):.1f} MB")
        
        # Process the gzipped JSON data
        print("\n🔄 Processing bulk data...")
        
        # The bulk data is a single JSON array, not line-delimited JSON
        with gzip.open(response.raw, 'rt', encoding='utf-8') as f:
            cards_data = json.load(f)
        
        print(f"📊 Successfully loaded {len(cards_data)} cards from bulk data")
        
        # Index cards into Elasticsearch
        print(f"\n💾 Indexing cards into Elasticsearch (index: {ELASTICSEARCH_INDEX})...")
        print("   This may take a while...")
        success_count, error_count = index_cards_bulk(es, cards_data)
        
        # Refresh the index to make documents searchable
        print("\n🔄 Refreshing index...")
        es.indices.refresh(index=ELASTICSEARCH_INDEX)
        
        # Calculate execution time
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print(f"🎉 Script completed!")
        print(f"⏱️  Total execution time: {duration}")
        print(f"📊 Cards indexed: {success_count}")
        print(f"❌ Cards with errors: {error_count}")
        
        return True
        
    except requests.RequestException as e:
        print(f"❌ Error downloading bulk data: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_indexed_cards(es):
    """Verify how many cards were indexed into Elasticsearch"""
    try:
        # Get total document count
        result = es.count(index=ELASTICSEARCH_INDEX)
        total_cards = result['count']
        
        # Get sample of cards by set
        query = {
            "size": 0,
            "aggs": {
                "sets": {
                    "terms": {
                        "field": "set_code.keyword",
                        "size": 10,
                        "order": {"_count": "desc"}
                    }
                }
            }
        }
        
        result = es.search(index=ELASTICSEARCH_INDEX, body=query)
        top_sets = result.get('aggregations', {}).get('sets', {}).get('buckets', [])
        
        # Get recent cards
        recent_query = {
            "size": 5,
            "sort": [{"indexed_at": {"order": "desc"}}],
            "_source": ["name", "set_code", "collector_number"]
        }
        recent_result = es.search(index=ELASTICSEARCH_INDEX, body=recent_query)
        recent_cards = [hit['_source'] for hit in recent_result.get('hits', {}).get('hits', [])]
        
        print(f"\n📊 Elasticsearch index contains {total_cards} total cards")
        print("🏆 Top sets by card count:")
        for bucket in top_sets:
            print(f"   • {bucket['key']} - {bucket['doc_count']} cards")
        
        print("\n🆕 Most recently indexed cards:")
        for card in recent_cards:
            print(f"   • {card.get('name', 'Unknown')} ({card.get('set_code', 'N/A')} #{card.get('collector_number', 'N/A')})")
            
    except Exception as e:
        print(f"❌ Error verifying indexed cards: {e}")

if __name__ == "__main__":
    print("⚠️  WARNING: This script will download and index ALL cards from Scryfall into Elasticsearch.")
    print("This will use significant disk space, bandwidth, and Elasticsearch resources.")
    print("=" * 60)
    
    response = input("\nDo you want to continue? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ Script cancelled by user")
        exit(0)
    
    success = download_and_process_bulk_data()
    
    if success:
        es = create_elasticsearch_client()
        verify_indexed_cards(es)
        print("\n✅ All done! Cards are now indexed in Elasticsearch.")
    else:
        print("\n❌ Script failed. Please check the errors above.")
