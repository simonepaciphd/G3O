# G3O Shared Repository

## Global Government GenAI Observatory (G3O)
**Collaboration Module: Search & Collection**

This repository contains the search and scraping components for G3O. Note that "QuantSearch" is an internal legacy name for the engine, but this repo focuses on the "Observatory" data collection.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Create a `.env` file (or use system env vars):
   ```
   SERPER_API_KEY=your_key_here
   ```

## Development

The code is in `src/`.
- `search_serper.py`: Handles Google Search API (Serper).
- `scrape.py`: Handles HTML/PDF fetching and text cleaning.
- `collection_driver.py`: A simple CLI to run the pipeline.

### Running the Collector
```bash
python src/collection_driver.py --query "UK artificial intelligence policy" --limit 5
```
Output will be saved to `data/collected_data.jsonl`.

## Contributing
- Please keep `scrape.py` focused on high-quality text extraction.
- Do not commit your `.env` file containing secrets.
