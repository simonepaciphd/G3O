"""G3O procurement pipeline.

Shared-core + per-source-adapter ETL that turns public-procurement repositories
into one standardized GenAI-procurement master. See docs/architecture.md.

The extraction/staging core (models / search / classify / standardize / store)
is built and tested offline. It does not yet produce the 39-field contract rows.
No source adapter exists, nothing has been pulled from a live repository, and
the institution matcher waits on the master's persistent key (spec §5).

The GenAI search terms and the classification taxonomy are PI-defined
(substantive) and are never invented in code — see pipeline/core/classify.py.
"""

__version__ = "0.1.0-core"
