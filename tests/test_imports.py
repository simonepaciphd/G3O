"""Smoke test: every public module imports without side effects."""

from __future__ import annotations


def test_top_level_import():
    import g3o

    assert g3o.__version__


def test_common_imports():
    from g3o.common import config, schema  # noqa: F401

    assert len(schema.DATA_COLUMNS) == 44
    # 37 = 35 base + the institution_uid/sweep_uid key layer (PI ruling 2026-08-14).
    assert len(schema.ACTIVITY_COLUMNS) == 37
    # 20 = 17 base + group_d_salvaged_fields (Group-D salvage flag, 2026-07-21)
    # + the same two-column key layer.
    assert len(schema.ACTIVITY_SOURCE_COLUMNS) == 20
    # 22 = 21 base + institution_uid. No sweep_uid: this CSV is not a loader
    # input, and at institution grain sweep_uid restates the uid.
    assert len(schema.SUMMARY_COLUMNS) == 22


def test_discovery_imports():
    # The three entity/multi-strategy helpers that used to be exported from
    # g3o.discovery were removed 2026-08-24 (review F12): unused by the pipeline,
    # and every one of them built a quoted institution name — the query shape the
    # project measured and abandoned. `build_site_query` stays; stage_discovery
    # imports it.
    from g3o.discovery import query_builder, search_google, serper_client  # noqa: F401
    from g3o.discovery.serper_client import build_site_query  # noqa: F401


def test_scrape_imports():
    from g3o.scrape import (  # noqa: F401
        FetchMetadata,
        RenderedPage,
        check_keyword_proximity,
        fetcher,
        html,
        pdf,
        render,
        render_url,
        scrape_url,
    )
