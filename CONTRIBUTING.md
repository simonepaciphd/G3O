# Contributing to G3O

Welcome! This document outlines the development roadmap and contribution guidelines for the G3O (Global Government GenAI Observatory) data collection system.

## Setup

1. Clone the repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.template` to `.env` and add your API key:
   ```bash
   cp .env.template .env
   # Edit .env with your SERPER_API_KEY
   ```

3. Test the setup:
   ```bash
   python -m src.collection_driver --query "UK AI policy" --limit 3
   ```

---

## Development Roadmap

### Priority 1: Search Improvements

| Task | Description | Status |
|------|-------------|--------|
| ✅ Full metadata extraction | Date, position, sitelinks from Serper | Done |
| ✅ Search operators | `site:`, `filetype:pdf` support | Done |
| ✅ Homepage discovery | Find official website for entity | Done |
| ✅ Multi-strategy search | Try multiple query patterns | Done |
| 🔲 LLM query refinement | Use GPT to suggest better search terms | TODO |
| 🔲 Date range filtering | Search within specific time periods | TODO |

### Priority 2: Scraping Improvements

| Task | Description | Status |
|------|-------------|--------|
| ✅ PDF extraction | Extract text from PDF documents | Done |
| ✅ Boilerplate removal | Remove nav, footer, ads, cookies | Done |
| ✅ Link extraction with context | Anchor text + surrounding paragraph | Done |
| 🔲 Dynamic page support | Add Playwright for JS-rendered pages | TODO |
| 🔲 Readability algorithm | Port Mozilla Readability for cleaner text | TODO |
| 🔲 Language detection | Identify page language | TODO |

### Priority 3: Quality & Testing

| Task | Description | Status |
|------|-------------|--------|
| 🔲 GitHub Actions CI | Auto-run tests on push | TODO |
| 🔲 Test fixtures | Sample pages for regression testing | TODO |
| 🔲 Scrape quality scoring | Heuristic to rate extraction quality | TODO |

---

## How to Contribute

### Pick a Task
1. Check the roadmap above for `TODO` items
2. Open an issue or comment on existing one to claim it
3. Create a feature branch: `git checkout -b feature/my-improvement`

### Code Guidelines
- Keep functions focused and documented
- Add type hints where possible
- Test with real URLs before submitting

### Testing Locally
```bash
# Run the collection driver
python -m src.collection_driver --query "test query" --limit 5

# Test specific functions in Python REPL
python
>>> from src import search_serper, scrape
>>> results = search_serper.search_google("test")
>>> page = scrape.scrape_url("https://example.com")
```

### Pull Requests
1. Ensure code works locally
2. Push to your branch
3. Open PR with description of changes
4. GitHub Actions will run tests (if configured)

---

## Architecture Overview

```
src/
├── config.py           # Environment variables and settings
├── search_serper.py    # Google Search via Serper API
├── scrape.py           # URL fetching and text extraction
└── collection_driver.py  # CLI entry point
```

### Key Functions

**search_serper.py**
- `search_google(query)` - Basic search
- `search_entity_homepage(entity_name)` - Find official website
- `multi_strategy_search(entity, topic)` - Combined search strategies

**scrape.py**
- `scrape_url(url)` - Fetch and extract text + links
- Supports HTML, PDF, DOCX automatically

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SERPER_API_KEY` | Yes | API key for Google Search |
| `OPENAI_API_KEY` | No | For LLM features (future) |

---

## Questions?

Open an issue on GitHub or contact the maintainer.
