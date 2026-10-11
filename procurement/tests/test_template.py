"""Per-source smoke-run harness — CLONE THIS for each new source.

The core itself is covered offline in `test_core.py`, which runs the whole
five-stage path over synthetic OCDS fixtures. This file is the *source-specific*
half: proving that one real repository's real payloads survive the same path.
`test_smoke_first_api_source` below is now a worked example for Uruguay's ARCE
(the first real OCDS-API source, verified live 2026-08-10) — clone its shape for
the next source rather than starting from scratch.

Standing lab rule: before any full source pull, run the WHOLE path on a handful
of that source's records and fix every error, then scale.

Pattern for each new source:
  1. copy a few REAL sample payloads into tests/fixtures/<source_id>/
     (real ones — the _ocds_sample/ fixtures are synthetic and prove nothing
     about a live source's field placement). Document what each one is and why
     it was picked in a README.md alongside them (see the ury_... folder here).
  2. subclass SourceAdapter so search()/fetch() read the fixtures instead of the
     network — see _FixtureFileAdapter below, or FixtureAdapter in test_core.py
     for the synthetic-fixture shape.
  3. run Pipeline(...).run(limit=<fixture count>, strict=True)
  4. assert: records produced, schema-valid (StagingStore validates on write —
     a schema violation raises), no errors
  5. then, and only then, run the live pull: python -m pipeline.cli run <id> --limit 5

Run:  .venv/bin/pytest -q
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pytest

from pipeline.core import contract
from pipeline.core.base import Pipeline, SourceAdapter
from pipeline.core.classify import NLPClassifier
from pipeline.core.models import GenAIQuerySet, Hit, RawRecord
from pipeline.core.search import load_queries
from pipeline.core.store import StagingStore

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
QUERIES_PATH = ROOT / "config" / "genai_queries.yaml"


class _FixtureFileAdapter(SourceAdapter):
    """Offline stand-in for a real adapter: search()/fetch() read saved real
    payloads from tests/fixtures/<source_id>/*.json instead of the network.

    This does not touch the network itself — the fixtures were produced once,
    ahead of time, by the real adapter's own search()/fetch() (see the README
    next to each fixture folder for exactly when/how). Clone this class for the
    next source's smoke test; only `source_id` and `is_ocds` change.
    """

    def __init__(self, source_id: str, is_ocds: bool = True, **config_extra):
        config = {"source_id": source_id, "access_mode": "api", "is_ocds": is_ocds}
        config.update(config_extra)
        super().__init__(config)
        self.fixture_dir = FIXTURES / source_id

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        for path in sorted(self.fixture_dir.glob("*.json")):
            yield Hit(self.source_id, path.stem, ref=path)

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        for hit in hits:
            path = Path(hit.ref)
            payload = json.loads(path.read_text(encoding="utf-8"))
            yield RawRecord(
                source_id=self.source_id,
                native_id=hit.native_id,
                payload=payload,
                fetched_at="2026-08-29T00:00:00+00:00",
                raw_payload_ref=str(path),
            )


def test_smoke_first_api_source(tmp_path):
    """End-to-end on the full REAL fixture set for Uruguay's ARCE — the first
    OCDS-API source (roadmap Phase 2; adapter verified live 2026-08-10). As of
    2026-09-19 this is the n=100 live bounded probe's 101-payload set (replaced
    the original 2026-08-29 5-record hand-picked set, archived at
    archive/ury_fixtures_n5-superseded-2026-09-19/). See
    tests/fixtures/ury_compras_estatales_arce_open_contracting_ocds/README.md
    for exactly what this set is and why it changed.

    This proves the shared extract_ocds() path survives real payload shapes,
    including the sparse/empty ones a real source actually returns (an empty
    awards array, a tender with no title) — not just the tidy synthetic
    _ocds_sample/ fixtures. It does NOT touch the network: the adapter's own
    search()/fetch() already did that, once, to produce the saved fixtures;
    this test replays them offline so it runs in CI/every `pytest -q`.

    This is a plumbing/QC proof, not a recall/precision/prevalence claim —
    same caveat as the live sample runs (PI, 2026-08-04, spec §8.4).
    """
    source_id = "ury_compras_estatales_arce_open_contracting_ocds"
    # Matches the real config/sources.yaml row (country_iso3/country_name/repo_name/
    # coverage_type are read from adapter.config by standardize(), not by the network).
    adapter = _FixtureFileAdapter(
        source_id,
        country_iso3="URY", country_name="Uruguay",
        repo_name="Compras Estatales (ARCE) – Open Contracting (OCDS)",
        coverage_type="both",
    )
    fixture_count = len(list(adapter.fixture_dir.glob("*.json")))
    assert fixture_count, (
        f"no fixtures found under tests/fixtures/{source_id}/ — see this file's docstring"
    )

    queries = load_queries(str(QUERIES_PATH))
    store = StagingStore(str(tmp_path / "staging"))
    classifier = NLPClassifier(queries)

    report = Pipeline(adapter, queries, classifier, store).run(limit=fixture_count, strict=True)

    assert report.fetched == fixture_count
    assert report.written >= fixture_count   # >= : one release can stage several awards/lots (ruling D6)
    assert not report.errors

    rows = list(store.iter_rows("records"))
    assert len(rows) == report.written
    for row in rows:
        assert row["source_id"] == source_id
        if row["genai_evidence_type"] is None:   # rule R8: not assessable, never coded
            assert "internal_insufficient_text" in row["review_flags"]
        else:
            assert row["genai_evidence_type"] in contract.GENAI_EVIDENCE
        assert row["notice_type"] in ("tender", "award", "unknown")

    store.close()
