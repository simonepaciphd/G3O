"""Frozen-input reproducibility regression harness (WS4 T1, 2026-06-11).

Pins the two deterministic surfaces an identical re-run depends on, against
goldens computed from frozen inputs committed to the repo:

1. **Sampling** — the stratified draw from ``tests/fixtures/frozen_master.csv``
   at the production seed must reproduce the exact golden institution list,
   checked with the same hash mechanism as the live dry-run gate
   (``sha256(json.dumps(ids))[:16]``).
2. **Request construction** — for each of the four LLM stages, the serialized
   Batch API JSONL line built from frozen inputs must hash to its golden.
   This pins the prompts, the JSON-schema ``response_format``, the pinned
   generation parameters (``reasoning_effort``), and the serializer itself:
   any change to what the pipeline sends shows up here as a failure.

A failure means a *deliberate* change to a reproducibility-bearing surface
(prompt edit, schema change, parameter pin, sampler change). After confirming
the change is intended — and recording it per the radical-transparency policy
— regenerate the goldens with::

    G3O_REGEN_GOLDENS=1 python -m pytest tests/test_reproducibility_regression.py

and commit ``tests/goldens/reproducibility.json`` alongside the change.
These tests run in the standard CI pytest gate; no network, no API keys.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from g3o.classify.official_site import build_official_site_job
from g3o.classify.url_triage import build_triage_job
from g3o.common.batch_client import DEFAULT_ENDPOINT, BatchJob, _serialize_job_line
from g3o.extract.batch import build_extract_jobs
from g3o.run.presweep import (
    institution_record,
    stratified_sample,
    synth_institution_id,
)
from g3o.scrape.render import FetchMetadata, RenderedPage
from g3o.validate.client import build_consolidate_job

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "frozen_master.csv"
GOLDENS_PATH = Path(__file__).parent / "goldens" / "reproducibility.json"
REGEN_ENV = "G3O_REGEN_GOLDENS"

# Production sampling parameters (Q2, 2026-05-09); the sample size is scaled
# to the 36-row fixture but exercises the same quota/deficit code paths.
FROZEN_SEED = 22294
FROZEN_SAMPLE_SIZE = 12
FROZEN_MODEL = "gpt-5-nano"

# Frozen Stage 2/3 candidate set and Stage 4 page. Synthetic but shaped like
# production values; what matters is that they never change.
FROZEN_CANDIDATE_URLS = [
    "https://digital.gov.at-example.org/ai-strategy",
    "https://digital.gov.at-example.org/news/genai-pilot",
    "https://news.example.org/atlantis-chatbot-launch",
]
FROZEN_PAGE_TEXT = (
    "The Ministry of Digital Affairs announced a generative AI pilot for "
    "citizen services. The chatbot, based on a large language model, will "
    "answer questions about permits and registrations. A procurement notice "
    "for the underlying platform was published alongside an internal usage "
    "policy for staff. "
) * 8
FROZEN_INPUT_ROWS: list[dict[str, Any]] = [
    {
        "institution_id": "INST-0000001",
        "activity_name": "Citizen-services GenAI chatbot pilot",
        "activity_type": "deployment",
        "genai_relevance": "explicit",
        "source_url": "https://digital.gov.at-example.org/news/genai-pilot",
        "access_date": "2026-06-11",
        "evidence_quote": "announced a generative AI pilot for citizen services",
    }
]


def _frozen_rows() -> list[dict[str, Any]]:
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _sample_hash(ids: list[str]) -> str:
    """Hash the draw the way the live dry-run gate does: sha256(json.dumps(ids))[:16].

    Same hashing approach, different input: this runs over the frozen fixture
    master, never the real one. It pins the sampler; it is not the live gate and
    carries no claim about the production master's hash.
    """
    return hashlib.sha256(json.dumps(ids).encode("utf-8")).hexdigest()[:16]


def _frozen_sample_ids() -> list[str]:
    sample = stratified_sample(
        _frozen_rows(), sample_size=FROZEN_SAMPLE_SIZE, seed=FROZEN_SEED
    )
    return [synth_institution_id(r) for r in sample]


def _stage_jobs() -> dict[str, BatchJob]:
    """One representative BatchJob per LLM stage, from frozen inputs only."""
    institution = institution_record(_frozen_rows()[0])
    inst_id = institution["institution_id"]
    page = RenderedPage(
        url=FROZEN_CANDIDATE_URLS[1],
        text=FROZEN_PAGE_TEXT,
        title="GenAI pilot announcement",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-06-11",
            http_status=200,
            final_url=None,
            fetch_method="html",
            elapsed_ms=10,
            wait_for=None,
        ),
    )
    return {
        "classify_official_site": build_official_site_job(
            institution, FROZEN_CANDIDATE_URLS, custom_id=inst_id
        ),
        "classify_triage": build_triage_job(
            institution,
            FROZEN_CANDIDATE_URLS,
            official_site=FROZEN_CANDIDATE_URLS[0],
            custom_id=inst_id,
        ),
        "extract": build_extract_jobs(
            [(institution, page)],
            batch_id="frozen-regression",
            institution_search_languages="en",
            model_label=FROZEN_MODEL,
        )[0],
        "validate": build_consolidate_job(
            institution,
            FROZEN_INPUT_ROWS,
            custom_id=inst_id,
            n_input_pages=1,
            model_label=FROZEN_MODEL,
        ),
    }


def _job_line_hashes() -> dict[str, str]:
    return {
        stage: hashlib.sha256(
            _serialize_job_line(
                job,
                model=FROZEN_MODEL,
                response_format=None,  # builders attach per-job response_format
                endpoint=DEFAULT_ENDPOINT,
            )
        ).hexdigest()
        for stage, job in _stage_jobs().items()
    }


def _current() -> dict[str, Any]:
    ids = _frozen_sample_ids()
    return {
        "fixture": "tests/fixtures/frozen_master.csv",
        "sample_seed": FROZEN_SEED,
        "sample_size": FROZEN_SAMPLE_SIZE,
        "sample_institution_ids": ids,
        "sample_hash": _sample_hash(ids),
        "job_line_sha256": _job_line_hashes(),
    }


def _golden() -> dict[str, Any]:
    if os.environ.get(REGEN_ENV):
        GOLDENS_PATH.parent.mkdir(exist_ok=True)
        GOLDENS_PATH.write_text(
            json.dumps(_current(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pytest.skip(
            "goldens regenerated; review and commit tests/goldens/"
            "reproducibility.json alongside the change that motivated it"
        )
    assert GOLDENS_PATH.exists(), (
        f"golden file missing at {GOLDENS_PATH}; regenerate deliberately with "
        f"{REGEN_ENV}=1"
    )
    return json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Invocation stability — same inputs, same process, twice
# ---------------------------------------------------------------------------


def test_sample_draw_is_invocation_stable():
    assert _frozen_sample_ids() == _frozen_sample_ids()


def test_job_lines_are_invocation_stable():
    assert _job_line_hashes() == _job_line_hashes()


# ---------------------------------------------------------------------------
# Golden regression — same inputs, any process, any day
# ---------------------------------------------------------------------------


def test_frozen_sample_reproduces_golden():
    golden = _golden()
    current = _current()
    assert current["sample_institution_ids"] == golden["sample_institution_ids"], (
        "the stratified draw from the frozen master CSV changed; if the "
        "sampler change is deliberate, regenerate goldens (see module docstring)"
    )
    assert current["sample_hash"] == golden["sample_hash"]


def test_frozen_job_lines_reproduce_golden():
    golden = _golden()["job_line_sha256"]
    current = _job_line_hashes()
    changed = sorted(s for s in current if current[s] != golden.get(s))
    assert not changed, (
        f"serialized LLM request line(s) changed for stage(s) {changed}: a "
        f"prompt, response schema, generation parameter, or the serializer "
        f"itself differs from the golden. If deliberate, regenerate goldens "
        f"(see module docstring)."
    )
    assert sorted(current) == sorted(golden), "stage set drifted from goldens"


def test_job_lines_carry_the_generation_parameter_pin():
    """The golden hashes pin reasoning_effort implicitly; this states it explicitly."""
    for stage, job in _stage_jobs().items():
        line = json.loads(
            _serialize_job_line(
                job, model=FROZEN_MODEL, response_format=None, endpoint=DEFAULT_ENDPOINT
            )
        )
        assert line["body"]["reasoning_effort"] == "medium", stage
