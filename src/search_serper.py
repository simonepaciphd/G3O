import requests
import json
import os
import hashlib
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_exponential
from src import config

def get_cache_key(query):
    h = hashlib.md5()
    h.update(query.encode('utf-8'))
    return h.hexdigest()

def get_cached_result(query):
    key = get_cache_key(query)
    path = os.path.join(config.CACHE_DIR, f"serp_{key}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_to_cache(query, data):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    key = get_cache_key(query)
    path = os.path.join(config.CACHE_DIR, f"serp_{key}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def execute_serper_query(query, num_results=10):
    headers = {
        'X-API-KEY': config.SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({"q": query, "num": num_results})
    
    response = requests.post(config.SERPER_ENDPOINT, headers=headers, data=payload, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()

def extract_domain(url):
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except:
        return ""

def search_google(query, num_results=10, force_refresh=False):
    """
    Search Google via Serper. Returns rich metadata for each result.
    
    Returns list of dicts with:
    - title, link, snippet (basic)
    - domain, position, date (metadata)
    - sitelinks (if available)
    """
    if not force_refresh:
        cached = get_cached_result(query)
        if cached:
            return cached

    print(f"Searching: {query}")
    try:
        data = execute_serper_query(query, num_results)
        
        results = []
        if 'organic' in data:
            for idx, item in enumerate(data['organic']):
                result = {
                    # Basic fields
                    "title": item.get('title'),
                    "link": item.get('link'),
                    "snippet": item.get('snippet'),
                    # Rich metadata
                    "domain": extract_domain(item.get('link', '')),
                    "position": item.get('position', idx + 1),
                    "date": item.get('date'),  # Publication date if available
                    "sitelinks": item.get('sitelinks', []),
                }
                results.append(result)
        
        save_to_cache(query, results)
        return results
        
    except Exception as e:
        print(f"Search failed: {e}")
        return []

# --- Search Operators & Smart Queries ---

def build_site_query(query, site_domain):
    """Build a site-scoped search query."""
    return f"site:{site_domain} {query}"

def build_filetype_query(query, filetype="pdf"):
    """Build a filetype-specific query."""
    return f"{query} filetype:{filetype}"

def search_entity_homepage(entity_name, entity_type="government agency"):
    """
    Find the official homepage for an entity.
    Returns the most likely official domain.
    """
    # Try official website query first
    query = f'"{entity_name}" official website {entity_type}'
    results = search_google(query, num_results=5)
    
    if not results:
        # Fallback to simpler query
        results = search_google(f"{entity_name} {entity_type}", num_results=5)
    
    if results:
        # Return the first result's domain (usually the official site)
        return {
            "homepage": results[0].get('link'),
            "domain": results[0].get('domain'),
            "confidence": "high" if len(results) > 0 else "low"
        }
    return {"homepage": None, "domain": None, "confidence": "none"}

def search_entity_with_site_scope(entity_name, topic, homepage_domain=None):
    """
    Search for a topic within an entity's website.
    If homepage unknown, discovers it first.
    """
    if not homepage_domain:
        discovery = search_entity_homepage(entity_name)
        homepage_domain = discovery.get('domain')
    
    if homepage_domain:
        # Site-scoped search
        query = build_site_query(topic, homepage_domain)
        return search_google(query, num_results=10)
    else:
        # Fallback to general search
        return search_google(f"{entity_name} {topic}", num_results=10)

def multi_strategy_search(entity_name, topic, num_results_per_strategy=5):
    """
    Execute multiple search strategies and deduplicate results.
    Returns combined, deduplicated results.
    """
    all_results = []
    seen_urls = set()
    
    strategies = [
        f'"{entity_name}" "{topic}"',  # Exact match
        f'{entity_name} {topic}',       # Broad match
        f'{entity_name} {topic} policy',  # Policy focus
        f'{entity_name} {topic} announcement',  # News focus
        build_filetype_query(f"{entity_name} {topic}", "pdf"),  # PDF reports
    ]
    
    for query in strategies:
        results = search_google(query, num_results=num_results_per_strategy)
        for r in results:
            url = r.get('link', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                r['search_strategy'] = query  # Track which strategy found it
                all_results.append(r)
    
    return all_results
