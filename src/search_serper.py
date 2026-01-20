import requests
import json
import os
import hashlib
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

def search_google(query, num_results=10, force_refresh=False):
    """
    Search Google via Serper.
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
            for item in data['organic']:
                results.append({
                    "title": item.get('title'),
                    "link": item.get('link'),
                    "snippet": item.get('snippet')
                })
        
        save_to_cache(query, results)
        return results
        
    except Exception as e:
        print(f"Search failed: {e}")
        return []
