"""Discovery layer: institution-driven search via the Serper Google Search API.

See README.md and docs/architecture.md for the design.
"""

from g3o.discovery.serper_client import search_google

__all__ = ["search_google"]
