"""G3O — Global Government GenAI Observatory.

Production data-collection pipeline for the G3O project. The pipeline has
three layers: discovery (search), scrape (retrieval + parse), extract
(LLM-driven structured extraction), and validate (cross-source merge and
deduplication).

See README.md and docs/architecture.md for the design.
"""

__version__ = "0.1.0"
