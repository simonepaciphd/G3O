import argparse
import os
import json
import time
from urllib.parse import urlparse
import search_serper
import scrape
import config

def is_valid_gov_url(url):
    """
    Task 2: Filter to ensure we only keep relevant government links.
    Includes negative keyword check to exclude media/news domains.
    Validates URLs based on:
    1. Negative filtering: excludes news/press/blog domains
    2. Positive filtering: includes .gov, .us, county, and org domains
    Returns True if URL passes both filters.
    """
    if not url: return False
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    
    # Exclude news and blog domains often found in search
    negative_keywords = ['news', 'press', 'blog', 'journal', 'magazine']
    if any(neg in domain for neg in negative_keywords):
        return False
        
    # Include government and organization domains
    if domain.endswith(".gov") or domain.endswith(".us") or "county" in domain or "org" in domain:
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="G3O Data Collection Tool")
    parser.add_argument("--query", required=True, help="Search query for finding relevant pages")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of search results to process")
    parser.add_argument("--output", default="collected_data.jsonl", help="Output filename for collected data")
    parser.add_argument("--counties", action="store_true", help="Use county-specific search strategies")
    parser.add_argument("--depth", type=int, default=1, help="Depth of recursive link following (1=no recursion)")
    parser.add_argument("--proximity", default=None, help="Comma-separated keywords for proximity check (e.g., 'ai,policy,regulation')")
    
    args = parser.parse_args()
    
    # Task 2: Strategy Execution - Choose search mode based on arguments
    search_results = []
    if args.counties:
        print("Executing county search strategies...")
        strategies = search_serper.get_us_county_strategies(args.query)
        for strat in strategies:
            # Distribute limit across all strategies
            res = search_serper.search_google(strat, num_results=max(2, args.limit // len(strategies)))
            search_results.extend(res)
    else:
        # Standard search mode
        search_results = search_serper.search_google(args.query, num_results=args.limit)
    
    print(f"Found {len(search_results)} initial pages.")
    
    # Initialize data collection structures
    collected_data = []
    visited_urls = set()
    prox_keywords = [k.strip().lower() for k in args.proximity.split(',')] if args.proximity else []

    def process_url(url, source_type, parent_context=""):
        """
        Handles scraping and proximity validation for a single URL.
        Includes a polite delay between requests.
        Returns the scraped data if successful and passes filters, None otherwise.
        """
        # Skip if already visited
        if url in visited_urls: return None
        visited_urls.add(url)
        
        # Rate limiting to avoid blocking
        time.sleep(1)
        
        # Scrape the URL
        data = scrape.scrape_url(url)
        if data['success']:
            # Task 1: Proximity Verification - Check if keywords appear near each other
            if prox_keywords:
                if not scrape.check_keyword_proximity(data['text'], prox_keywords, max_distance=50):
                    print(f"   Skipped {url} - Proximity check failed.")
                    return None
            
            # Add metadata and save to collection
            data['source_type'] = source_type
            data['parent_context'] = parent_context
            collected_data.append(data)
            return data
        return None

    # Primary processing loop - Process all search results
    for res in search_results:
        url = res.get('link')
        if not url: continue
        page_data = process_url(url, source_type="search_result")
        
        # Task 3: Recursive Scraping - Follow links if depth > 1
        if args.depth > 1 and page_data:
            print(f"   Recursion: Checking links in {url}...")
            links_to_check = page_data.get('links', [])
            
            # Prioritization: Sort links to check AI/Policy terms first
            links_to_check.sort(key=lambda x: any(w in x['anchor_text'].lower() for w in ['ai', 'policy']), reverse=True)
            
            # Process up to 5 relevant links per page
            sub_count = 0
            for link_obj in links_to_check:
                link_url = link_obj['url']
                link_text = link_obj['anchor_text'].lower()
                
                # Stop after 5 links to prevent explosion
                if sub_count >= 5: break
                
                # Only follow valid government URLs with relevant keywords
                if is_valid_gov_url(link_url) and link_url not in visited_urls:
                    if any(w in link_text for w in ['policy', 'ai', 'report', 'guideline', 'pdf']):
                        process_url(link_url, source_type="recursive_link", parent_context=url)
                        sub_count += 1

    # Save output to JSONL format
    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUTS_DIR, args.output)
    with open(out_path, 'w', encoding='utf-8') as f:
        for item in collected_data:
            json.dump(item, f, ensure_ascii=False)
            f.write("\n")
            
    print(f"Saved {len(collected_data)} records to {out_path}")

if __name__ == "__main__":
    main()