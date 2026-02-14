import requests
import json
import os
import hashlib
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_exponential
import config

def get_cache_key(query):
    """
    Generates a unique MD5 hash for a search query to manage caching.
    Ensures consistent cache filenames across different query executions.
    """
    h = hashlib.md5()
    h.update(query.encode('utf-8'))
    return h.hexdigest()

def get_cached_result(query):
    """
    Retrieves search results from the local cache if they exist.
    Returns None if the query has not been cached previously.
    """
    key = get_cache_key(query)
    path = os.path.join(config.CACHE_DIR, f"serp_{key}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_to_cache(query, data):
    """
    Saves search results to the local cache directory.
    Creates cache directory if it doesn't exist.
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    key = get_cache_key(query)
    path = os.path.join(config.CACHE_DIR, f"serp_{key}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def execute_serper_query(query, num_results=10):
    """
    Executes a POST request to the Serper.dev API with retry logic.
    Uses exponential backoff to handle temporary API failures.
    Returns mock data if SERPER_API_KEY is not configured.
    """
    if not config.SERPER_API_KEY:
        print("Warning: No SERPER_API_KEY. Returning mock data.")
        return {"organic": [
            {"title": "Mock Result 1", "link": "https://example.com/county-ai", "snippet": "Artificial intelligence policy."},
            {"title": "Mock Result 2", "link": "https://example.org/gov-policy.pdf", "snippet": "AI guidelines."}
        ]}

    headers = {
        'X-API-KEY': config.SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = json.dumps({"q": query, "num": num_results})
    
    response = requests.post(config.SERPER_ENDPOINT, headers=headers, data=payload, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()

def extract_domain(url):
    """
    Extracts and cleans the domain from a given URL.
    Removes 'www.' prefix for consistent domain comparison.
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace('www.', '')
    except:
        return ""

def search_google(query, num_results=10, force_refresh=False):
    """
    Performs a Google search via Serper and returns processed metadata.
    Returns cached results if available unless force_refresh=True.
    Extracts and structures organic search results with metadata:
    - title, link, snippet: basic search result fields
    - domain: extracted domain name
    - position: ranking position in results
    - date: publication date if available
    - sitelinks: additional links from the same domain
    """
    # Check cache first unless force refresh is requested
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
                    "title": item.get('title'),
                    "link": item.get('link'),
                    "snippet": item.get('snippet'),
                    "domain": extract_domain(item.get('link', '')),
                    "position": item.get('position', idx + 1),
                    "date": item.get('date'),
                    "sitelinks": item.get('sitelinks', []),
                }
                results.append(result)
        
        save_to_cache(query, results)
        return results
        
    except Exception as e:
        print(f"Search failed: {e}")
        return []

def build_site_query(query, site_domain):
    """
    Builds a site-scoped search query using Google's site: operator.
    Example: "AI policy" -> "site:example.gov AI policy"
    """
    return f"site:{site_domain} {query}"

def build_filetype_query(query, filetype="pdf"):
    """
    Builds a filetype-specific search query using Google's filetype: operator.
    Example: "AI policy" -> "AI policy filetype:pdf"
    Useful for finding specific document types like PDFs, DOCs, XLS.
    """
    return f"{query} filetype:{filetype}"

def get_us_county_strategies(topic):
    """
    Task 2: Generates specialized search queries targeting US County data.
    Returns a list of 5 different search strategies:
    1. Government sites with "county" in content
    2. Organization sites with county government focus
    3. National Association of Counties (NACO) resources
    4. County policy documents (PDFs)
    5. County board meeting agendas
    """
    strategies = [
        f"{topic} site:.gov \"county\"",
        f"{topic} site:.org \"county\" \"government\"",
        f"{topic} site:naco.org",
        f"{topic} \"county policy\" filetype:pdf",
        f"{topic} \"county board\" agenda"
    ]
    return strategies

def search_entity_homepage(entity_name, entity_type="government agency"):
    """
    Attempts to find the official homepage domain for a specific entity.
    Uses exact phrase matching for high-confidence results.
    Falls back to broader search if exact match returns no results.
    Returns dict with homepage URL, domain, and confidence level.
    """
    # Try exact phrase match first
    query = f'"{entity_name}" official website {entity_type}'
    results = search_google(query, num_results=5)
    
    # Fall back to broader search if no results
    if not results:
        results = search_google(f"{entity_name} {entity_type}", num_results=5)
    
    if results:
        return {
            "homepage": results[0].get('link'),
            "domain": results[0].get('domain'),
            "confidence": "high" if len(results) > 0 else "low"
        }
    return {"homepage": None, "domain": None, "confidence": "none"}

def search_entity_with_site_scope(entity_name, topic, homepage_domain=None):
    """
    Searches for a topic specifically within an entity's website.
    If homepage_domain is not provided, attempts to discover it first.
    Falls back to general search if domain discovery fails.
    """
    # Discover homepage domain if not provided
    if not homepage_domain:
        discovery = search_entity_homepage(entity_name)
        homepage_domain = discovery.get('domain')
    
    # Execute site-scoped search if domain is known
    if homepage_domain:
        query = build_site_query(topic, homepage_domain)
        return search_google(query, num_results=10)
    else:
        # Fall back to general search
        return search_google(f"{entity_name} {topic}", num_results=10)

def multi_strategy_search(entity_name, topic, num_results_per_strategy=5):
    """
    Executes multiple search strategies and deduplicates the results.
    Uses 5 different query patterns to maximize coverage:
    1. Exact phrase match for both entity and topic
    2. Broad match without quotes
    3. Topic with "policy" context
    4. Topic with "announcement" context
    5. PDF documents containing both terms
    Deduplicates by URL and tracks which strategy found each result.
    """
    all_results = []
    seen_urls = set()
    
    # Define multiple search strategies
    strategies = [
        f'"{entity_name}" "{topic}"',
        f'{entity_name} {topic}',
        f'{entity_name} {topic} policy',
        f'{entity_name} {topic} announcement',
        build_filetype_query(f"{entity_name} {topic}", "pdf"),
    ]
    
    # Execute each strategy and deduplicate
    for query in strategies:
        results = search_google(query, num_results=num_results_per_strategy)
        for r in results:
            url = r.get('link', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                r['search_strategy'] = query
                all_results.append(r)
    
    return all_results