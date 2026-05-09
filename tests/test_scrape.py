"""Scrape-layer tests.

The ``scrape_url`` test makes a real HTTP request to example.com to mirror
the historical CI smoke test. CI uses ``continue-on-error`` for any
network-dependent step at the workflow level; locally, this test will
fail without network connectivity, which is the desired behavior.
"""

from __future__ import annotations

import pytest

from g3o.scrape import RenderedPage, check_keyword_proximity
from g3o.scrape.fetcher import scrape_url


def test_keyword_proximity_returns_true_within_distance():
    text = "We are launching a new generative AI assistant policy this quarter."
    assert check_keyword_proximity(text, ["generative", "policy"], max_distance=10)


def test_keyword_proximity_returns_false_when_only_one_keyword_found():
    text = "We are launching a new product."
    assert not check_keyword_proximity(text, ["generative", "policy"], max_distance=50)


def test_keyword_proximity_handles_empty_text():
    assert not check_keyword_proximity("", ["x", "y"], max_distance=50)


@pytest.mark.network
def test_scrape_url_returns_text_for_example_com():
    result = scrape_url(
        "https://example.com",
        force_refresh=True,
        prefer_render_on_empty=False,
    )
    assert isinstance(result, RenderedPage)
    assert result.url == "https://example.com"
    assert result.content_type in {"html", "pdf"}
    assert result.text
    assert result.fetch_metadata.access_date  # ISO date string
    assert result.fetch_metadata.fetch_method in {"html", "pdf"}
