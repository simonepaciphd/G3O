"""T-052: the 2026-10-09 n=100 Uruguay replay (RS-047), reproduced offline from
the committed ARCE fixtures with the repo's own pipeline code.

RS-047 is the 2026-10-09 replay (replay_n100.py, replay_summary_nomatch.json;
see planning/RESOURCES.md). That run's code hash 398167e2...
is the pipeline at commit 55fe353. Since then only pipeline/cli.py:code_hash
has changed (as_posix), which does not touch processing, so this test does
not assert the hash.

What this test does NOT cover:
- Institution matching (RS-047: 0 linked, 132 in review). That needs the
  read-only institution master, which is not in the repo, so the run here has
  no index and no review queue.
- The 101st fixture, adjudicacion-1370285.json. The original fetch pulled it
  because of the --limit off-by-one (fixed in pipeline/core/base.py) and never
  staged it, so RS-047 covers the other 100 (the reconciliation payload
  inventory, referenced_by_staging). It is excluded here by name.

The URY source is `unverified_snapshot`. That guard belongs to the CLI and
Pipeline.run does not apply it. This test calls Pipeline directly, as the
replay did, and makes no network calls.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from pipeline.cli import load_source_config
from pipeline.core.base import Pipeline, SourceAdapter
from pipeline.core.classify import NLPClassifier
from pipeline.core.models import Hit, RawRecord
from pipeline.core.search import load_queries
from pipeline.core.store import StagingStore

ROOT = Path(__file__).parents[1]
SOURCE_ID = "ury_compras_estatales_arce_open_contracting_ocds"
FIXTURES = ROOT / "tests" / "fixtures" / SOURCE_ID
NOT_STAGED_IN_ORIGINAL_RUN = "adjudicacion-1370285.json"


class _ReplayAdapter(SourceAdapter):
    """Reads the saved payloads instead of the network (same shape as replay_n100.py)."""

    def __init__(self, config: dict, files: list[Path]):
        super().__init__(config)
        self.files = files

    def search(self, queries):
        return [Hit(self.source_id, p.stem, ref=str(p)) for p in self.files]

    def fetch(self, hits):
        for hit in hits:
            path = Path(hit.ref)
            yield RawRecord(source_id=self.source_id, native_id=hit.native_id,
                            payload=json.loads(path.read_text(encoding="utf-8")),
                            fetched_at="2026-09-15T00:00:00+00:00",
                            raw_payload_ref=path.relative_to(ROOT).as_posix())


def _replay_files() -> list[Path]:
    committed = sorted(FIXTURES.glob("*.json"))
    assert len(committed) == 101, "the committed n=100 probe set has 101 payloads"
    files = [p for p in committed if p.name != NOT_STAGED_IN_ORIGINAL_RUN]
    assert len(files) == 100
    return files


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    config = load_source_config(str(ROOT / "config" / "sources.yaml"), SOURCE_ID)
    queries = load_queries(str(ROOT / "config" / "genai_queries.yaml"))
    store = StagingStore(str(tmp_path_factory.mktemp("replay_ury")))
    try:
        report = Pipeline(_ReplayAdapter(config, _replay_files()), queries,
                          NLPClassifier(queries), store).run(strict=True)
        records = list(store.iter_rows("records"))
        extensions = list(store.iter_rows("extensions"))
    finally:
        store.close()   # release the SQLite file so Windows can remove the temp dir
    return report, records, extensions


def _flagged(records, flag):
    return sum(1 for r in records if flag in (r.get("review_flags") or []))


def test_replay_reproduces_rs047_counts(replay):
    report, records, _ = replay
    assert report.errors == []
    assert report.fetched == 100
    assert report.written == len(records) == 132
    assert report.candidate_no == 71
    assert report.candidate_not_assessable == 61
    assert report.candidate_yes == 0
    assert report.candidate_unclear == 0
    assert report.review_queue == 0
    assert report.cannot_type == 0
    assert report.fetch_failed == 0
    assert len({r.get("buyer_name") for r in records}) == 48


def test_replay_rows_split_into_absence_and_not_assessable(replay):
    _, records, _ = replay
    assert Counter(r["genai_evidence_type"] for r in records) == {"confirms_absence": 71, None: 61}
    for row in records:
        if row["genai_evidence_type"] is None:   # rule R8: no text is never absence
            assert "internal_insufficient_text" in row["review_flags"]


def test_replay_text_and_money_figures_match_rs047(replay):
    _, records, extensions = replay
    assert sum(1 for r in records if r.get("title") or r.get("description")) == 71
    assert _flagged(records, "internal_description_from_items") == 63
    priced = [e for e in extensions if e.get("value_amount") is not None]
    assert len(priced) == 63
    assert _flagged(records, "internal_value_from_items") == 63
    assert _flagged(records, "internal_value_partial_items_unpriced") == 0
    assert _flagged(records, "internal_value_mixed_currency") == 0
    assert _flagged(records, "internal_value_currency_missing") == 0
    assert Counter(e.get("value_currency") for e in priced) == {"UYU": 60, "USD": 3}
