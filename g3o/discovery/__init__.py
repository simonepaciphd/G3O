"""Discovery layer: institution-driven search via the Serper Google Search API.

See README.md and docs/architecture.md for the design.
"""

from g3o.discovery.serper_client import (
    multi_strategy_search,
    search_entity_homepage,
    search_entity_with_site_scope,
    search_google,
)

__all__ = [
    "multi_strategy_search",
    "search_entity_homepage",
    "search_entity_with_site_scope",
    "search_google",
]
