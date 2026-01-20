import argparse
import os
import json
from src import search_serper, scrape, config

def main():
    parser = argparse.ArgumentParser(description="G3O Data Collection Tool")
    parser.add_argument("--query", required=True, help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    parser.add_argument("--output", default="collected_data.jsonl", help="Output file")
    
    args = parser.parse_args()
    
    # 1. Search
    print(f"Searching for: {args.query}")
    results = search_serper.search_google(args.query, num_results=args.limit)
    
    collected = []
    
    # 2. Scrape
    for r in results:
        url = r.get('link')
        if not url: continue
        
        data = scrape.scrape_url(url)
        if data.get('text'):
             collected.append({
                 "title": r.get('title'),
                 "url": url,
                 "snippet": r.get('snippet'),
                 "text": data['text']
             })
             
    # 3. Save
    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
    out_path = os.path.join(config.OUTPUTS_DIR, args.output)
    
    # Check if we should append or write new?
    # For now, append to output
    with open(out_path, 'a', encoding='utf-8') as f:
        for item in collected:
            json.dump(item, f, ensure_ascii=False)
            f.write("\n")
            
    print(f"Saved {len(collected)} pages to {out_path}")

if __name__ == "__main__":
    main()
