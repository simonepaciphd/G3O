"""Mocked end-to-end orchestration smoke test (Session F.1, 2026-06-10).

Runs the full ``presweep --execute`` path for a 3-institution sample through
Stage 6 (validate) with Serper, the scraper, and the OpenAI Batch API all
stubbed at their module boundaries. Encodes the invariants the chunked
submission (review F2) and metadata reconciliation (review F6) work must
preserve: the per-institution artifact tree, the ``_state/.done`` markers for
every stage, and the ``{g3o_run_id, g3o_stage, g3o_chunk}`` metadata on every
submit. Overlaps WS4 T4's smoke-test item by design.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from g3o.common import attrition, batch_client
from g3o.common.artifact_io import ARTIFACT_SUFFIX, glob_artifacts
from g3o.common.batch_client import BatchHandle, BatchResult, BatchStatus
from g3o.common.credentials import Credentials, fingerprint
from g3o.common.run_state import done_path, state_dir
from g3o.discovery import serper_client
from g3o.extract.batch import make_custom_id, url_hash
from g3o.run import presweep as ps
from g3o.run.api import launch
from g3o.run.presweep import STAGES, PresweepConfig, institution_record
from g3o.scrape.render import FetchMetadata, RenderedPage
from tests._layout import inst_dir as inst_dir_of

ACCESS_DATE = "2026-06-10"
CANNED_URLS = ["https://example.gov/ai-policy", "https://example.gov/news"]
URL_BY_HASH = {url_hash(u): u for u in CANNED_URLS}
OFFICIAL_SITE = CANNED_URLS[0]


# ---------------------------------------------------------------------------
# Sample fixture
# ---------------------------------------------------------------------------


def _write_master(path: Path) -> Path:
    fieldnames = [
        "institution_uid", "master_row_id", "country", "government_level",
        "branch", "institution_type", "institution_name", "website",
        "source_dataset_id", "source_url", "source_file",
        "retrieval_date", "notes",
    ]
    rows = [
        {
            "institution_uid": f"G3O-I-{i + 1:08d}",
            "master_row_id": str(i + 1),
            "country": f"COUNTRY-{i}",
            "government_level": "national",
            "branch": "executive",
            "institution_type": "ministry",
            "institution_name": f"Ministry {i}",
            "website": "",
            "source_dataset_id": "synth",
            "source_url": "",
            "source_file": "synth.csv",
            "retrieval_date": "",
            "notes": "synth",
        }
        for i in range(3)
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Canned LLM responses per stage
# ---------------------------------------------------------------------------


def _official_site_content(job: Any) -> str:
    return json.dumps(
        {"url": OFFICIAL_SITE, "confidence": "high", "rationale": "smoke"}
    )


def _triage_content(job: Any) -> str:
    # The candidate URLs are embedded in the user prompt's INPUT json;
    # keep all of them so Stage 4/5 see deterministic work.
    user = job.messages[1]["content"]
    payload = json.loads(user.split("INPUT:\n", 1)[1])
    decisions = [
        {"url": u, "decision": "keep", "rationale": "smoke"}
        for u in payload["candidate_urls"]
    ]
    return json.dumps({"decisions": decisions})


def _extract_content(job: Any, institutions: dict[str, dict[str, Any]]) -> str:
    inst_id, h = job.custom_id.split("::")
    inst = institutions[inst_id]
    url = URL_BY_HASH[h]
    row = {
        "row_id": 1,
        "batch_id": "b1",
        "institution_id": inst_id,
        "institution_name": inst["institution_name"],
        "country": inst["country"],
        "branch_of_government": inst["branch_of_government"],
        "level_of_government": inst["level_of_government"],
        "has_genai_activity": "no",
        "institution_summary": "All supplied pages reviewed; no GenAI evidence found.",
        "institution_search_languages": "en",
        **{
            k: "_NA_"
            for k in (
                "activity_name", "activity_type", "adoption_stage", "access_type",
                "interaction_type", "tool_name", "vendor", "deployment_mode",
                "target_users", "year_announced", "year_deployed",
                "has_human_oversight", "has_transparency_notice",
                "has_data_classification", "has_risk_assessment",
                "reported_outcomes", "reported_incidents", "scope_notes",
            )
        },
        "source_url": url,
        "source_title": "Smoke page",
        "source_publication_date": "2026-01-15",
        "source_access_date": ACCESS_DATE,
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_absence",
        "source_snippet": "Page contains no mention of generative AI.",
        "confidence": "high",
        "uncertainty_flags": "none",
    }
    meta = {
        "batch_id": "b1",
        "chat_type": "web",
        "model_label": "gpt-5-nano",
        "response_timestamp": "2026-06-10T10:00:00Z",
        "n_institutions_in_batch": 1,
        "n_institutions_with_genai": 0,
        "n_data_rows": 1,
        "search_languages": "en",
        "search_strategy_summary": "URLs supplied by the pipeline.",
        "notes": "none",
    }
    return json.dumps({"batch_metadata": meta, "data": [row]})


def _validate_content(job: Any, institutions: dict[str, dict[str, Any]]) -> str:
    inst_id = job.custom_id
    inst = institutions[inst_id]
    return json.dumps(
        {
            "consolidation_metadata": {
                "institution_id": inst_id,
                "n_input_pages": 2,
                "n_input_rows": 2,
                "response_timestamp": "2026-06-10T12:00:00Z",
                "model_label": "gpt-5-nano",
                "notes": "none",
            },
            "institution": {
                "institution_id": inst_id,
                "institution_name": inst["institution_name"],
                "country": inst["country"],
                "branch_of_government": inst["branch_of_government"],
                "level_of_government": inst["level_of_government"],
                "has_genai_activity": "no",
                "institution_summary": "No GenAI evidence in supplied texts.",
                "institution_search_languages": "en",
            },
            "activities": [],
            "sources": [
                {
                    "source_id": "S1",
                    "activity_id": "_NA_",
                    "source_url": CANNED_URLS[0],
                    "source_title": "Smoke page",
                    "source_publication_date": "2026-01",
                    "source_access_date": ACCESS_DATE,
                    "source_type": "official_gov",
                    "source_language": "en",
                    "source_credibility": "high",
                    "genai_evidence": "confirms_absence",
                    "source_snippet": "Page contains no mention of generative AI.",
                }
            ],
        }
    )


# ---------------------------------------------------------------------------
# The smoke test
# ---------------------------------------------------------------------------


def test_presweep_execute_end_to_end_through_validate(tmp_path: Path, monkeypatch):
    master = _write_master(tmp_path / "master.csv")
    config = PresweepConfig(
        run_id="smoke-1",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
        dry_run=False,
        stop_after="validate",
        poll_interval=0,
        max_wait_per_stage=10,
        # Offline smoke: skip robots.txt fetches + per-host sleeps (review F14
        # politeness is unit-tested in test_politeness.py).
        scrape_respect_robots=False,
        scrape_host_delay_seconds=0,
        # Use non-jev models so the test uses the mocked batch API path
        classify_official_site_model=None,
        classify_triage_model=None,
        validate_model=None,
    )

    # --- Live-mode startup gate (review F1): --execute now hard-fails without
    # keys. Provide dummy keys (the network is fully stubbed below) and reset the
    # Serper live-mode global via monkeypatch so run_presweep's set_live_mode(True)
    # cannot leak into other tests (monkeypatch restores the attribute on teardown).
    monkeypatch.setenv("SERPER_API_KEY", "test-serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)

    # --- Serper stub: same canned organic results for every query.
    monkeypatch.setattr(
        ps.stage_discovery, "search_google_detailed",
        lambda query, num_results=5, **kw: serper_client.SerperResult(
            results=[
                {"link": u, "title": "Smoke", "snippet": "s", "domain": "example.gov",
                 "position": i + 1, "date": None, "sitelinks": []}
                for i, u in enumerate(CANNED_URLS)
            ],
            search_parameters={"q": query, "num": num_results},
            from_cache=False,
            payload={"q": query, "num": num_results},
        ),
    )

    # --- Scrape stub: deterministic RenderedPage per URL, no network.
    def _scrape(url: str, **kwargs) -> RenderedPage:
        # Text must clear the empty-page filter (>= 50 non-whitespace chars,
        # review F5) so Stage 5 builds a job for it.
        return RenderedPage(
            url=url,
            text=(
                "This smoke-test page describes the institution's public "
                f"activities and contains enough text to clear the filter. {url}"
            ),
            title="Smoke page",
            content_type="html",
            fetch_metadata=FetchMetadata(
                access_date=ACCESS_DATE, http_status=200, final_url=url,
                fetch_method="html", elapsed_ms=10, wait_for=None,
            ),
        )

    monkeypatch.setattr(ps.stage_scrape, "scrape_url", _scrape)

    # --- Batch API stub: record every submit; answer per recorded stage.
    institutions: dict[str, dict[str, Any]] = {}
    batches: dict[str, dict[str, Any]] = {}
    submitted_metadata: list[dict[str, str]] = []

    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        batch_id = f"batch-{metadata['g3o_stage']}-{metadata['g3o_chunk']}"
        batches[batch_id] = {"stage": metadata["g3o_stage"], "jobs": list(jobs)}
        submitted_metadata.append(dict(metadata))
        return BatchHandle(
            batch_id=batch_id, input_file_id="file-x",
            submitted_at=datetime.now(timezone.utc), n_jobs=len(jobs),
        )

    def _poll(batch_id, *, client=None):
        return BatchStatus(
            batch_id=batch_id, status="completed", request_counts={},
            output_file_id="out", error_file_id=None,
        )

    def _fetch(batch_id, *, client=None, status=None):
        rec = batches[batch_id]
        for job in rec["jobs"]:
            if rec["stage"] == "classify_official_site":
                content = _official_site_content(job)
            elif rec["stage"] == "classify_triage":
                content = _triage_content(job)
            elif rec["stage"] == "extract":
                content = _extract_content(job, institutions)
            elif rec["stage"] == "validate":
                content = _validate_content(job, institutions)
            else:  # pragma: no cover
                raise AssertionError(f"unexpected stage {rec['stage']!r}")
            yield BatchResult(
                custom_id=job.custom_id,
                success=True,
                response={"body": {"choices": [{"message": {"content": content}}]}},
                error=None,
            )

    monkeypatch.setattr(batch_client, "submit_batch", _submit)
    monkeypatch.setattr(batch_client, "poll_batch", _poll)
    monkeypatch.setattr(batch_client, "fetch_results", _fetch)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])

    # Institution lookup for the canned responses (filled after plan).
    rows = list(csv.DictReader(open(master, encoding="utf-8")))
    for row in rows:
        rec = institution_record(row)
        institutions[rec["institution_id"]] = rec

    # Entered through `launch()` — the documented entry point since the Run API
    # (spec §1.1) — so this test also exercises the telemetry surface end to end:
    # a full 8-stage run is the only place the whole event sequence exists, and
    # the shape it must produce was published to the backend before it existed.
    receipt = launch(config, session_id="sess-smoke", invocation="api")
    summary = receipt.summary

    # --- Summary invariants.
    run_dir = Path(summary["run_dir"])
    assert summary["n_institutions"] == 3
    assert summary["dry_run"] is False
    assert summary["n_official_sites"] == 3
    assert summary["n_triaged_kept"] == 6  # 2 kept URLs × 3 institutions
    assert summary["n_pages_scraped"] == 6
    assert summary["n_extracted"] == 6
    assert summary["n_consolidated"] == 3
    assert summary["n_validate_failed"] == 0
    assert summary["validate_batch_ids"] == ["batch-validate-1"]

    # --- Every submit carried the full reconciliation metadata (review F6),
    # plus the submitting key's fingerprint (Run API spec §3.5) — which is also
    # the end-to-end proof that the run's resolved credentials reached the wire,
    # and that what reaches it is the fingerprint, never the key (§3.3).
    assert len(submitted_metadata) == 4  # stages 2, 3, 5, 6 — one chunk each
    expected_fp = fingerprint("test-openai-key")
    for md in submitted_metadata:
        assert set(md) == {
            "g3o_run_id", "g3o_stage", "g3o_chunk", "g3o_key_fingerprint",
        }
        assert md["g3o_run_id"] == "smoke-1"
        assert md["g3o_key_fingerprint"] == expected_fp
        assert "test-openai-key" not in json.dumps(md)
    assert [md["g3o_stage"] for md in submitted_metadata] == [
        "classify_official_site", "classify_triage", "extract", "validate",
    ]

    # --- The run's event log: the fixture's shape, over a complete run.
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert {e["run_id"] for e in events} == {"smoke-1"}
    assert {e["session_id"] for e in events} == {"sess-smoke"}
    assert events[0]["event"] == "run_launched"
    assert events[-1]["event"] == "run_completed"
    assert events[-1]["payload"]["stop_after"] == "validate"

    # Every stage in the roster reports a start and a completion, in roster order.
    started = [e["stage"] for e in events if e["event"] == "stage_started"]
    completed = [e["stage"] for e in events if e["event"] == "stage_completed"]
    assert started == list(STAGES) == completed

    # Only the four LLM stages submit chunks (fixture loader invariant 9), and
    # every chunk that submitted also reached a terminal state.
    llm_stages = ["classify_official_site", "classify_triage", "extract", "validate"]
    submitted = [e for e in events if e["event"] == "chunk_submitted"]
    terminal = [e for e in events if e["event"] == "chunk_terminal"]
    assert [e["stage"] for e in submitted] == llm_stages
    assert [e["stage"] for e in terminal] == llm_stages
    for event in submitted:
        assert set(event["payload"]) >= {"chunk", "batch_id", "n_jobs"}
        assert event["payload"]["chunk"] == 1  # 1-based (invariant 7)
    for event in terminal:
        assert event["payload"]["terminal_state"] == "completed"
        assert event["payload"]["n_output"] > 0

    # --- Per-institution artifact tree.
    for inst_id in institutions:
        inst_dir = inst_dir_of(run_dir, inst_id)
        assert (inst_dir / "institution.json").exists()
        assert (inst_dir / "1a_discovery_general.json").exists()
        assert (inst_dir / "2_official_site.json").exists()
        assert (inst_dir / "1b_discovery_site_restricted.json").exists()
        assert (inst_dir / "3_triage.json").exists()
        # Stage 4/5 artifacts are gzipped from Phase 2 on. Asserting the
        # concrete ``.json.gz`` name (not just the stem) keeps this test pinning
        # *which* format the pipeline writes, so a silent regression to plain
        # JSON — or a second, uncompressed twin — still fails here.
        assert [p.name for p in glob_artifacts(inst_dir / "scrape")] == sorted(
            f"{h}{ARTIFACT_SUFFIX}" for h in URL_BY_HASH
        )
        assert [p.name for p in glob_artifacts(inst_dir / "extract")] == sorted(
            f"{h}{ARTIFACT_SUFFIX}" for h in URL_BY_HASH
        )
        validate_payload = json.loads(
            (inst_dir / "6_validate.json").read_text(encoding="utf-8")
        )
        assert validate_payload["institution"]["institution_id"] == inst_id
        assert validate_payload["institution"]["has_genai_activity"] == "no"
        # Stage 2 artifact is the parsed classifier result (no bypass column).
        stage2 = json.loads(
            (inst_dir / "2_official_site.json").read_text(encoding="utf-8")
        )
        assert stage2["url"] == OFFICIAL_SITE

    # --- Final state markers: every stage done, no active state files left.
    for stage in STAGES:
        assert done_path(run_dir, stage).exists(), f"missing .done for {stage}"
    leftovers = [p.name for p in state_dir(run_dir).glob("*.json")]
    assert leftovers == []

    # --- Attrition ledger present and empty on the happy path (review F4/F15):
    # non-empty, short page text → no Serper/scrape failures, no empty-page
    # drops, no truncations, no parse failures.
    assert attrition.ledger_path(run_dir).exists()
    assert attrition.read_records(run_dir) == []

    # --- Extract custom_ids round-tripped (institution × page).
    extract_jobs = batches["batch-extract-1"]["jobs"]
    expected_ids = {
        make_custom_id(inst_id, url)
        for inst_id in institutions
        for url in CANNED_URLS
    }
    assert {j.custom_id for j in extract_jobs} == expected_ids


# ---------------------------------------------------------------------------
# v2.7 gate 5: language-id (lingua) timing (PI ruling 24, 2026-11-11)
# ---------------------------------------------------------------------------
#
# PI ruling 24: "No text cap for now; measure lingua time on the mocked
# end-to-end run before ruling." The mocked v2.7 e2e through ``run_presweep``
# cannot run green on this candidate (the followed page stops the per-page
# stage on the T-015 assembler's unproduced items; see the T-030 builder
# report), so lingua is timed here on the pipeline's own per-page call and on
# lingua directly. lingua is NOT mocked. Nothing here fails on timing.

LINGUA_SIZES = (2_000, 20_000, 100_000, 500_000)
TIMING_ENV = "G3O_E2E_TIMING_OUT"


def _synthetic_text(base: str, n_chars: int) -> str:
    """``base`` repeated and cut to exactly ``n_chars`` characters."""
    return (base * (n_chars // len(base) + 1))[:n_chars]


def _page(url: str, text: str) -> RenderedPage:
    return RenderedPage(
        url=url, text=text, title="Timing page", content_type="html",
        fetch_metadata=FetchMetadata(access_date=ACCESS_DATE, http_status=200, final_url=url,
                                     fetch_method="html", elapsed_ms=10, wait_for=None),
    )


def test_v27_language_id_timing(tmp_path: Path, monkeypatch, capsys):
    """Time the pipeline's language-id call and raw lingua on ~2k-500k-character pages (en, fr, de).

    Pipeline path: ``source_fields.source_language_of_page`` (the call
    ``perpage_inputs_v27.page_source_fields`` makes per stored page), with the
    real ``language_id.identify`` wrapped by a ``perf_counter`` timer via
    monkeypatch. Direct path: the same pinned detector's
    ``detect_multiple_languages_of``. The cold detector build is timed
    separately. JSON goes to ``$G3O_E2E_TIMING_OUT`` (else ``tmp_path``) and to
    stdout.
    """
    import os
    import platform
    import time
    from importlib.metadata import version

    from g3o.common import language_id as lid
    from g3o.common import source_fields as sf
    from tests.test_language_id import DE, EN, FR

    texts = {"en": EN, "fr": FR, "de": DE}
    pipeline_calls: list[dict[str, Any]] = []
    real_identify = lid.identify

    def timed_identify(main_text: str):
        t0 = time.perf_counter()
        res = real_identify(main_text)
        pipeline_calls.append({"chars": len(main_text), "seconds": time.perf_counter() - t0,
                               "tag": res.tag, "reason": res.reason})
        return res

    monkeypatch.setattr(lid, "identify", timed_identify)

    # Cold build of the pinned detector (all languages, high accuracy; models load lazily on first use).
    lid._detector.cache_clear()
    t0 = time.perf_counter()
    detector = lid._detector()
    build_seconds = time.perf_counter() - t0

    pipeline: list[dict[str, Any]] = []
    direct: list[dict[str, Any]] = []
    order = 0
    for size in LINGUA_SIZES:
        for lang, base in texts.items():
            text = _synthetic_text(base, size)
            order += 1
            value = sf.source_language_of_page(_page(f"https://example.gov/{lang}/{size}", text))
            call = pipeline_calls[-1]
            assert call["chars"] == size
            pipeline.append({"order": order, "lang": lang, "chars": size, "seconds": call["seconds"],
                             "tag": call["tag"], "reason": call["reason"], "value": value.value})
            order += 1
            t0 = time.perf_counter()
            spans = detector.detect_multiple_languages_of(text)
            direct.append({"order": order, "lang": lang, "chars": size,
                           "seconds": time.perf_counter() - t0, "n_spans": len(spans)})

    # Below MIN_MAIN_TEXT_CHARS (ruling 21: 200): unknown, lingua not consulted.
    short = sf.source_language_of_page(_page("https://example.gov/short", EN[:150]))
    assert pipeline_calls[-1]["reason"] == "below_min_length"

    timing = {
        "kind": "g3o_v27_lingua_timing",
        "lingua_version": version(lid.LIBRARY),
        "language_id_version": lid.LANGUAGE_ID_VERSION,
        "min_main_text_chars": lid.MIN_MAIN_TEXT_CHARS,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "detector_build_seconds": build_seconds,
        "note": ("order is call order in one process: the first detection call includes lingua's lazy "
                 "model load; pipeline = source_language_of_page -> language_id.identify (real lingua, "
                 "timed by a monkeypatch wrapper); direct = detect_multiple_languages_of on the same text"),
        "pipeline_source_language_of_page": pipeline,
        "direct_detect_multiple_languages_of": direct,
        "below_min_length": {"chars": len(EN[:150]), "value": short.value,
                             "seconds": pipeline_calls[-1]["seconds"]},
        "totals_seconds": {"pipeline": sum(r["seconds"] for r in pipeline),
                           "direct": sum(r["seconds"] for r in direct)},
    }
    out = Path(os.environ.get(TIMING_ENV) or tmp_path / "lingua_timing.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timing, indent=2, sort_keys=True), encoding="utf-8")
    with capsys.disabled():
        print(f"\n[lingua timing -> {out}]\n{json.dumps(timing, indent=2, sort_keys=True)}")

    # Sanity only (never timing): single-language pages are identified as their language.
    for row in pipeline:
        assert row["tag"] == row["lang"], row


# ---------------------------------------------------------------------------
# v2.7 new-run entry (T-030, PI ruling 132 a, 2026-11-15)
# ---------------------------------------------------------------------------
#
# ``launch()`` with a v2.7 config and no injected ``V27Dispatch``: the run builds
# its real providers from ``config.v27_runtime`` and the resolved credentials
# (``g3o.run.presweep.v27_entry``). Mocks sit at the provider/client boundary
# only: Serper (``search_google_detailed``), the fetcher (``scrape_url``), the
# OpenAI Batch API (Stages 2/3), the TypeSafe SDK client (jev), the ``anthropic``
# SDK module (extractor), the X35 client seam, and a test-injected per-page
# builder (ruling 36 a: the default builder is refused at entry while
# ``MISSING_PRODUCERS`` is non-empty). No stage function is stubbed; the page
# layout is the real one. WITHOUT the follow leg (ruling 132 a: the follow-leg
# e2e waits for codebook r16 and T-026 P12), so the follow seam returns None.

V27_KEYS = dict(openai_api_key="sk-test", serper_api_key="serper-test", typesafe_api_key="typesafe-test",
                anthropic_api_key="anthropic-test")
V27_SENTENCE = "The council deployed Copilot for drafting letters in 2025."
V27_INSTITUTIONS = {
    # keyword (in every query / prompt of that institution): (master row, name, country, url, text, activities)
    "quillfield": (1, "Council Quillfield", "Australia", "https://quillfield.example.gov/ai-drafting",
                   "The council publishes notes on how its staff write letters to residents. "
                   + V27_SENTENCE + " Staff review every draft before it is sent, and the council "
                   "reports how many letters were drafted this way each quarter.",
                   [("Copilot drafting", "Copilot", V27_SENTENCE)]),
    "brackenmoor": (2, "Council Brackenmoor", "New Zealand", "https://brackenmoor.example.gov/services",
                    "The council publishes its bin collection calendar and its library opening hours on "
                    "this page. It does not use generative AI tools in any of its services, and all "
                    "letters to residents are written by council staff without software assistance.",
                    []),
    "valtorde": (3, "Conseil Valtorde", "France", "https://valtorde.example.gov/services",
                 "Le conseil municipal publie sur cette page le calendrier de collecte des déchets et "
                 "les horaires d'ouverture de la bibliothèque. Les courriers adressés aux habitants "
                 "sont rédigés par les agents du conseil, qui répondent aussi aux questions "
                 "posées au guichet de la mairie.",
                 []),
}
#: url -> (keyword, master row, name, country, url, text, activities)
V27_BY_URL = {v[3]: (k, *v) for k, v in V27_INSTITUTIONS.items()}


def _v27_write_master(path: Path) -> Path:
    columns = ["institution_uid", "master_row_id", "country", "government_level", "branch", "institution_type",
               "institution_name", "website", "source_dataset_id", "source_url", "source_file", "retrieval_date",
               "notes"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row, name, country, *_ in V27_INSTITUTIONS.values():
            w.writerow({"institution_uid": f"G3O-I-{row:08d}", "master_row_id": str(row), "country": country,
                        "government_level": "local", "branch": "executive", "institution_type": "council",
                        "institution_name": name, "website": "", "source_dataset_id": "synth", "source_url": "",
                        "source_file": "synth.csv", "retrieval_date": "", "notes": "synth"})
    return path


def _v27_config(tmp_path: Path, **kw: Any) -> PresweepConfig:
    from dataclasses import asdict

    from tests.test_e2e_perpage_v27 import SETTINGS

    values = dict(run_id="v27-entry", runs_dir=tmp_path / "runs", master_csv=_v27_write_master(tmp_path / "m.csv"),
                  sample_size=3, seed=22294, dry_run=False, stop_after="validate", poll_interval=0,
                  max_wait_per_stage=10, scrape_respect_robots=False, scrape_host_delay_seconds=0,
                  classify_official_site_model=None, classify_triage_model=None, validate_model=None,
                  pipeline_version="v2.7", v27_not_production_ready_opt_in=True, v27_runtime=asdict(SETTINGS))
    values.update(kw)
    return PresweepConfig(**values)


def _v27_keyword(text: str) -> str | None:
    low = text.lower()
    return next((k for k in V27_INSTITUTIONS if k in low), None)


def _v27_stub_stages_1_to_4_clients(monkeypatch) -> dict[str, list[Any]]:
    """Serper, the fetcher and the OpenAI Batch API (Stages 2/3), each at its client boundary."""
    seen: dict[str, list[Any]] = {"serper": [], "scrape": [], "openai_clients": []}
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)

    def search(query, num_results=5, **kw):
        seen["serper"].append(query)
        key = _v27_keyword(query)
        results = []
        if key is not None:
            url = V27_INSTITUTIONS[key][3]
            results = [{"link": url, "title": V27_INSTITUTIONS[key][1], "snippet": "s",
                        "domain": url.split("/")[2], "position": 1, "date": None, "sitelinks": []}]
        return serper_client.SerperResult(results=results, search_parameters={"q": query, "num": num_results},
                                          from_cache=False, payload={"q": query, "num": num_results})

    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", search)

    def scrape(url: str, **kwargs) -> RenderedPage:
        seen["scrape"].append(url)
        _key, _row, name, _country, _url, text, _acts = V27_BY_URL[url]
        return RenderedPage(url=url, text=text, title=name, content_type="html",
                            fetch_metadata=FetchMetadata(access_date=ACCESS_DATE, http_status=200, final_url=url,
                                                         fetch_method="html", elapsed_ms=10, wait_for=None))

    monkeypatch.setattr(ps.stage_scrape, "scrape_url", scrape)

    class OpenAIClient:  # the Batch API client object: constructed, never used (the calls below are stubbed)
        def __init__(self, *a, **kw):
            seen["openai_clients"].append(kw.get("api_key"))

    monkeypatch.setattr(batch_client, "OpenAI", OpenAIClient)
    batches: dict[str, dict[str, Any]] = {}

    def submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        batch_id = f"batch-{metadata['g3o_stage']}-{metadata['g3o_chunk']}"
        batches[batch_id] = {"stage": metadata["g3o_stage"], "jobs": list(jobs)}
        return BatchHandle(batch_id=batch_id, input_file_id="file-x", submitted_at=datetime.now(timezone.utc),
                           n_jobs=len(jobs))

    def fetch(batch_id, *, client=None, status=None):
        rec = batches[batch_id]
        for job in rec["jobs"]:
            if rec["stage"] == "classify_official_site":
                key = _v27_keyword(json.dumps(job.messages, ensure_ascii=False))
                content = json.dumps({"url": V27_INSTITUTIONS[key][3] if key else None,
                                      "confidence": "high", "rationale": "smoke"})
            elif rec["stage"] == "classify_triage":
                payload = json.loads(job.messages[1]["content"].split("INPUT:\n", 1)[1])
                content = json.dumps({"decisions": [{"url": u, "decision": "keep", "rationale": "smoke"}
                                                    for u in payload["candidate_urls"]]})
            else:  # pragma: no cover - a v2.7 run has no v2.5 Stage 5/6 batch
                raise AssertionError(f"unexpected batch stage {rec['stage']!r} on a v2.7 run")
            yield BatchResult(custom_id=job.custom_id, success=True,
                              response={"body": {"choices": [{"message": {"content": content}}]}}, error=None)

    monkeypatch.setattr(batch_client, "submit_batch", submit)
    monkeypatch.setattr(batch_client, "poll_batch", lambda batch_id, *, client=None: BatchStatus(
        batch_id=batch_id, status="completed", request_counts={}, output_file_id="out", error_file_id=None))
    monkeypatch.setattr(batch_client, "fetch_results", fetch)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])
    return seen


class _FakeTypeSafeClient:
    """Stands in for ``typesafe_sdk.TypeSafeClient``: answers through the e2e world's ``FakeJev``."""

    instances: list[_FakeTypeSafeClient] = []
    answer: Any = None

    def __init__(self, *, api_key=None, model=None, retry=None, **kw):
        self.api_key, self.model = api_key, model
        self.calls = 0
        type(self).instances.append(self)

    def system_one(self, state, questions, *, model=None, **kw):
        from types import SimpleNamespace

        import typesafe_sdk as ts

        self.calls += 1
        plain = {qid: {"instructions": q.instructions, "criteria": dict(q.criteria)} for qid, q in questions.items()}
        res = type(self).answer(state, plain)
        answers = {qid: ts.ChoiceAnswer(choice=a.choice, confidence=float(a.confidence),
                                        probabilities={k: float(v) for k, v in a.probabilities.items()})
                   for qid, a in res.answers.items()}
        return SimpleNamespace(answers=answers, model=res.response_model, request_id=res.request_id,
                               usage=SimpleNamespace(input_tokens=res.input_tokens, output_tokens=res.output_tokens))


def _v27_fake_anthropic_module(record: dict[str, list[Any]], *,
                                pages: dict[str, tuple[str, list[Any]]] | None = None,
                                links: dict[str, list[tuple[str, str]]] | None = None) -> Any:
    """A stand-in ``anthropic`` module whose ``Anthropic`` client answers the v2.7 extractor requests.

    Answered from the request alone (as the real API sees it): pass-1 / pass-2 quote
    tasks get their part's text, pass 1's activity task the fixture's activities, and
    the Stage 6 quote step its first shown quote.

    ``pages`` (url -> (text, activities)) adds pages to :data:`V27_BY_URL` (a followed page).
    ``links`` (url -> [(link url, passage)]): the stored links pass 1's link task selects on
    that page. An X35 request (``x35_client`` wording, ``<text>`` first) is answered
    ``true`` at 0.95 and recorded under ``record["x35"]``. ``messages.batches`` is the
    Message Batches API: ``create`` records each request's ``custom_id`` under
    ``record["batched"]`` (and its params under ``record["batched_params"]``), every batch
    has ended at once, and its results are the same answers (no request id, as a batch
    result carries none).
    """
    import re
    import types
    from types import SimpleNamespace

    from g3o.extract.request_v27 import field_name

    by_url = {url: (v[5], v[6]) for url, v in V27_BY_URL.items()}
    by_url.update(pages or {})
    for key in ("x35", "batched", "batched_params"):
        record.setdefault(key, [])

    def answer(params: dict[str, Any]) -> dict[str, Any]:
        user = params["messages"][0]["content"]
        if user.startswith("<text>\n"):  # an X35 request (x35_client.X35_USER_TEMPLATE_DRAFT)
            record["x35"].append(params)
            return {"answer": "true", "probability": 0.95}
        if user.startswith("QUOTES:\n"):  # the Stage 6 quote step
            rows = json.loads(user.split("QUOTES:\n", 1)[1].split("\n\nTASK:\n", 1)[0])
            return {"quote_id": rows[0]["quote_id"], "quote": rows[0]["text"]}
        url = re.search(r"^PAGE ADDRESS: (.*)$", user, re.M).group(1)
        text, activities = by_url[url]
        tasks = json.loads(user.split("\nTASKS:\n", 1)[1])
        quotes = [{"task_id": t["task_id"], "part_id": t["part_id"], "quote": text.strip()}
                  for t in tasks["quote_tasks"]]
        if "field_tasks" in tasks:  # T-032 pass 2
            return {"quotes": quotes, "fields": [{"task_id": t["task_id"], "value": None, "part_id": None,
                                                  "supporting_text": None} for t in tasks["field_tasks"]]}
        payload: dict[str, Any] = {"quotes": quotes, "links": [], "activities": [], "publication_date": None}
        if tasks.get("link_task"):  # the stored links are listed as STORED LINKS (request_v27.build_user_message)
            part = re.search(r'<part id="([^"]+)">', user).group(1)
            stored = [json.loads(line) for line in user.split("\nSTORED LINKS:\n", 1)[1].split("\n\nTASKS:\n", 1)[0]
                      .splitlines() if line.strip()]
            ids = {ln["address"]: ln["link_id"] for ln in stored}
            payload["links"] = [{"link_id": ids[target], "part_id": part, "quote": passage}
                                for target, passage in (links or {}).get(url, []) if target in ids]
        if tasks["activity_task"] is not None:
            part = re.search(r'<part id="([^"]+)">', user).group(1)
            wanted = set(tasks["activity_task"]["fields"])
            for name, tool, sentence in activities:
                fields = [{"field": f, "value": v, "part_id": part, "supporting_text": sentence}
                          for f, v in ((field_name("core.activity_name"), name),
                                       (field_name("core.tool_name"), tool)) if f in wanted]
                payload["activities"].append({"part_id": part, "start_text": sentence, "end_text": sentence,
                                              "fields": fields})
        return payload

    batches: dict[str, list[dict[str, Any]]] = {}

    def message(params: dict[str, Any], n: int) -> dict[str, Any]:
        return {"model": "fake-extractor-response", "id": f"msgb-{n}", "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 10},
                "content": [{"type": "text", "text": json.dumps(answer(params))}]}

    def batch_create(*, requests):
        batch_id = f"msgbatch_{len(batches) + 1}"
        batches[batch_id] = list(requests)
        record["batched"].extend(r["custom_id"] for r in requests)
        record["batched_params"].extend(r["params"] for r in requests)
        return {"id": batch_id}

    def batch_results(batch_id):
        for n, r in enumerate(batches[batch_id], start=1):
            yield {"custom_id": r["custom_id"],
                   "result": {"type": "succeeded", "message": message(r["params"], n)}}

    class Anthropic:
        def __init__(self, *, api_key=None, **kw):
            record["clients"].append(api_key)
            record["max_retries"].append(kw.get("max_retries"))
            self.messages = SimpleNamespace(
                create=self._create,
                batches=SimpleNamespace(create=batch_create, results=batch_results,
                                        retrieve=lambda batch_id: {"processing_status": "ended"}))

        def _create(self, **params):
            record["params"].append(params)
            n = len(record["params"])
            return SimpleNamespace(model="fake-extractor-response", id=f"msg-{n}", _request_id=f"req-{n}",
                                   stop_reason="end_turn", usage={"input_tokens": 100, "output_tokens": 10},
                                   content=[{"type": "text", "text": json.dumps(answer(params))}])

    module = types.ModuleType("anthropic")
    module.Anthropic = Anthropic
    return module


class _ExplicitRowValues:
    """The test-injected per-page builder (ruling 36 a): the real default builder over the stored
    scrape artifacts, plus the row values whose producers are missing (T-015 / T-022 / T-024),
    declared as ``test_e2e_perpage_v27.World.upstream`` declares them, keyed to the real page ids
    and the real one-part layout (``<page_id>#p001``). The URL, access date and A3 language of each
    source row are the builder's own values (A3: real lingua)."""

    def __init__(self, extra_activities: dict[str, list[Any]] | None = None) -> None:
        self.page_fields: dict[str, Any] = {}
        self.n = 0
        #: url -> activities of a page outside V27_INSTITUTIONS (a followed page)
        self.extra_activities = dict(extra_activities or {})
        self.bound: Any = None
        self.instrument: Any = None
        #: url -> the source values injected for that page (by page unit)
        self.source_values: dict[str, dict[str, Any]] = {}

    def activities(self, url: str) -> list[Any]:
        return V27_BY_URL[url][6] if url in V27_BY_URL else self.extra_activities[url]

    def _code(self, bound, instrument, sources, chunk, aid, item, value, text):
        from g3o.classify.questions.v27 import JEV_QUESTION_SET_VERSION as QSV
        from g3o.common.jev_client import JevAnswer, JevResult
        from g3o.common.jev_record import CoderRecord
        from g3o.common.storage_fields import FIELDS
        from g3o.common.support_check import CodeEvidence, check_code
        from tests.test_e2e_perpage_v27 import TRUE, _no_quote_value

        quote = None if _no_quote_value(item, value) else text
        sr = check_code(CodeEvidence(item, value, chunk, probability=0.95, quote=quote,
                                     quote_chunk_id=chunk if quote else None,
                                     entailment=TRUE if quote else None, activity_id=aid), sources)
        self.n += 1
        context = dict(item_id=item, item_part=None, support_id=None, observation_id=None, chunk_id=chunk,
                       coder_version="fake-upstream-v1", question_set_version=QSV,
                       setup_pointer=instrument["instrument_id"])
        if FIELDS[item]["coder"] == "classifier":  # core.source_type: T-015's classifier
            res = JevResult({"Q": JevAnswer("Q", "choice", choice=value, confidence=0.95,
                                            probabilities={value: 0.95})}, "fake-jev-response", f"up-{self.n}", 1, 1)
            rec = CoderRecord.from_jev(res, question_id="Q", configured_model=bound.settings.jev_model,
                                       classifier_rule=bound.activity_config.rules[(item, None)], **context)
        else:
            rec = CoderRecord(question_id=None, coder_type="quote_step",
                              configured_model=bound.settings.extractor_model,
                              actual_response_model="fake-extractor-response", request_id=f"upx-{self.n}",
                              answer_type="extracted", chosen_value=value, confidence=None,
                              probability_distribution=None, **context)
        return sr, rec

    def _rows(self, bound, instrument, page, page_fields):
        from g3o.classify import jev_page_code as jpc
        from g3o.common.storage_fields import FIELDS
        from g3o.common.support_check import PageSources
        from g3o.run.presweep import stage_perpage_v27 as pp
        from tests._storage_fixture import _values

        pid, chunk = page.page_id, f"{page.page_id}#p001"  # a short page is one part (page_chunks.chunk_page)
        sources = PageSources(pid, {chunk: page.text}, jpc.contact_text(page))
        real = {"core.source_url": page_fields.url.value, "core.source_access_date": page_fields.access_date.value,
                "core.source_language": page_fields.language.value,
                "core.syndication_group": page_fields.syndication_group.value}  # A4, read by A7 independence

        def source_values():
            sv = {k: v for k, v in _values("sources").items()
                  if k in pp.SOURCE_ROW_ITEMS and (FIELDS[k]["coder"] != "classifier" or k == "core.source_type")}
            sv.update({k: v for k, v in real.items() if k in sv})
            sv.update({"core.source_title": page.title, "core.content_contact_emails": [],
                       "core.source_publication_date": "not_documented", "core.date_upper_bound": "not_asked"})
            return sv

        def code(aid, item, value, text):
            return self._code(bound, instrument, sources, chunk, aid, item, value, text)

        a_vals, s_vals, codes = {}, {}, {}
        for n, (name, tool, sentence) in enumerate(self.activities(page.url), start=1):
            aid = f"{pid}#a{n:03d}"  # the id the pass-1 parser assigns
            av = {k: v for k, v in _values("activities").items()
                  if k in pp.ACTIVITY_ITEMS and FIELDS[k]["coder"] != "classifier" and k != "core.uncertainty_flags"}
            av.update({"core.activity_name": name, "core.tool_name": [tool], "core.reported_outcomes": [],
                       "core.deployment_scale_number": "not_documented", "core.unit_credit": "no"})
            sv = source_values()
            codes[aid] = [code(aid, "core.activity_name", name, sentence), code(aid, "core.tool_name", tool, sentence),
                          code(aid, "core.observed_actor_name", av["core.observed_actor_name"], None),
                          code(aid, "core.contracting_party", av["core.contracting_party"], None),
                          code(aid, "core.deployment_scale_number", "not_documented", None),
                          code(aid, "core.source_type", sv["core.source_type"], sentence),
                          code(aid, "core.source_publication_date", "not_documented", None),
                          code(aid, "core.source_snippet", sv["core.source_snippet"], None)]
            a_vals[aid], s_vals[aid] = av, sv
        if not self.activities(page.url):  # RC-D-030 Y2 a: the page-level source row
            sv = source_values()
            s_vals[pp.NO_ACTIVITY] = sv
            codes[pp.NO_ACTIVITY] = [code(None, "core.source_type", sv["core.source_type"], page.text),
                                     code(None, "core.source_publication_date", "not_documented", None),
                                     code(None, "core.source_snippet", sv["core.source_snippet"], None)]
        return a_vals, s_vals, codes

    def followed(self, upstream: Any, page: Any) -> Any:
        """A followed page's upstream (``FollowLeg.followed_upstream``, its real page fields and hop) with
        the same declared row values as a searched page's, its discovery path and text source the
        follow leg's (ruling 61 a, ruling 62 a)."""
        from dataclasses import replace

        from g3o.common import source_fields as sf

        self.page_fields[page.url] = upstream.page_fields
        a_vals, s_vals, codes = self._rows(self.bound, self.instrument, page, upstream.page_fields)
        follow_values = {sf.DISCOVERY: sf.discovery_path(followed=True, hop=upstream.hop).value,
                         sf.TEXT_SOURCE: upstream.page_fields.text_source.value}
        for sv in s_vals.values():
            sv.update({k: v for k, v in follow_values.items() if k in sv})
        self.source_values[page.url] = s_vals
        return replace(upstream, activity_values=a_vals, source_values=s_vals, codes=codes)

    def __call__(self, run_dir, sample, scraped, bound, instrument):
        from dataclasses import replace

        from g3o.run.presweep import perpage_inputs_v27 as pin

        self.bound, self.instrument = bound, instrument
        out = []
        for inst in pin.build_perpage_inputs(run_dir, sample, scraped, bound, instrument):
            specs = []
            for spec in inst.pages:
                self.page_fields[spec.page.url] = spec.upstream.page_fields
                a_vals, s_vals, codes = self._rows(bound, instrument, spec.page, spec.upstream.page_fields)
                specs.append(replace(spec, upstream=replace(spec.upstream, activity_values=a_vals,
                                                            source_values=s_vals, codes=codes)))
            out.append(replace(inst, pages=specs))
        return out


def _v27_refuse_real_clients(monkeypatch) -> None:
    """Tripwires: any TypeSafe or Anthropic client construction fails the test."""
    import sys
    import types

    from g3o.common import jev_client

    def refuse(*_a, **_k):
        raise AssertionError("a provider client was constructed")

    monkeypatch.setattr(jev_client.ts, "TypeSafeClient", refuse)
    module = types.ModuleType("anthropic")
    module.Anthropic = refuse
    monkeypatch.setitem(sys.modules, "anthropic", module)


def test_v27_launch_builds_the_real_providers_and_runs_to_stage6_without_the_follow_leg(tmp_path: Path,
                                                                                       monkeypatch):
    """PI ruling 132 a: ``launch()`` on a v2.7 config with no injected dispatch builds the real
    providers from config and runs Stages 1-4, the v2.7 per-page stage and v2.7 Stage 6, every
    provider mocked at its client boundary; no follow leg."""
    import sys
    from dataclasses import asdict

    from g3o.classify import jev_page_code as jpc
    from g3o.common import jev_client
    from g3o.common.storage import StorageEnvelope
    from g3o.report.outcomes import compute_institution_report
    from g3o.run.presweep import planning, v27_entry
    from g3o.run.presweep import stage_perpage_v27 as pp
    from g3o.run.presweep import stage_validate_v27 as svv
    from tests.test_e2e_perpage_v27 import ANSWERS, RELATIONS, SETTINGS, TRUE, FakeJev

    seen = _v27_stub_stages_1_to_4_clients(monkeypatch)
    # jev: the TypeSafe SDK client, answered by the e2e world's FakeJev (verdict by page content).
    jev = FakeJev({**ANSWERS, jpc.VERDICT: lambda st: "confirms_activity" if "Copilot" in st.get("page_text", "")
                   else "no_genai"}, RELATIONS)
    monkeypatch.setattr(_FakeTypeSafeClient, "instances", [])
    monkeypatch.setattr(_FakeTypeSafeClient, "answer", jev)
    monkeypatch.setattr(jev_client.ts, "TypeSafeClient", _FakeTypeSafeClient)
    # The extractor: the anthropic SDK module.
    extractor: dict[str, list[Any]] = {"clients": [], "max_retries": [], "params": []}
    monkeypatch.setitem(sys.modules, "anthropic", _v27_fake_anthropic_module(extractor))
    # The X35 client (bound, ruling 139 a; Q160 approved): a fake entry stands in for it.
    x35_calls: list[Any] = []
    monkeypatch.setattr(v27_entry, "x35_entail_fn",
                        lambda settings, creds: lambda q, text: x35_calls.append((q, text)) or TRUE)
    # Ruling 36 a: the default builder is refused at entry, so the builder is injected.
    builder = _ExplicitRowValues()
    monkeypatch.setattr(v27_entry, "perpage_inputs_builder", lambda config: builder)
    # Ruling 132 a: no follow leg in this e2e.
    monkeypatch.setattr(v27_entry, "follow_fetch", lambda config: None)

    # PI ruling 134: this run keeps the all-live extractor path (no_batch); the batched default (mix)
    # is exercised by the follow-leg e2e below.
    receipt = launch(_v27_config(tmp_path, v27_extractor_mode="no_batch"), credentials=Credentials(**V27_KEYS),
                     session_id="sess-v27", invocation="api")
    summary = receipt.summary
    run_dir = Path(summary["run_dir"])

    # The real providers were built from config, lazily, over the mocked clients only.
    assert [c.api_key for c in _FakeTypeSafeClient.instances] == ["typesafe-test"]
    assert _FakeTypeSafeClient.instances[0].model == SETTINGS.jev_model
    assert _FakeTypeSafeClient.instances[0].calls == len(jev.calls) > 0
    assert extractor["clients"] == ["anthropic-test"] and extractor["params"]
    assert extractor["max_retries"] == [0]  # PI ruling 135 a: no SDK-internal retry
    assert {p["model"] for p in extractor["params"]} == {SETTINGS.extractor_model}
    assert x35_calls
    assert set(seen["openai_clients"]) == {"sk-test"}
    assert sorted(set(seen["scrape"])) == sorted(v[3] for v in V27_INSTITUTIONS.values())

    # Stages 1-4 and both v2.7 stages ran; nothing held or failed.
    assert summary["pipeline_version"] == "v2.7" and summary["n_institutions"] == 3
    assert summary["n_pages_scraped"] == 3
    assert summary["n_perpage_held"] == 0 and summary["n_perpage_failed_pages"] == 0
    assert summary["n_stage6_written"] == 3
    assert summary["n_stage6_held"] == summary["n_stage6_failed"] == 0
    assert "n_extracted" not in summary and "n_consolidated" not in summary
    assert pp.DONE_MARKER == "perpage_v27" and svv.DONE_MARKER == "stage6_v27"
    assert done_path(run_dir, pp.DONE_MARKER).exists() and done_path(run_dir, svv.DONE_MARKER).exists()

    # The manifest records the runtime settings the instrument was bound from, and the bound instrument.
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["v27_runtime"] == asdict(SETTINGS)
    instrument_id = manifest[planning.RUN_PIPELINE_KEY]["instrument_id"]
    assert summary["instrument_id"] == instrument_id

    # One non-English page: the builder's own A3 language (real lingua) is French.
    languages = {url: fields.language.value for url, fields in builder.page_fields.items()}
    assert languages == {V27_INSTITUTIONS["quillfield"][3]: "en", V27_INSTITUTIONS["brackenmoor"][3]: "en",
                         V27_INSTITUTIONS["valtorde"][3]: "fr"}

    # Every 6_storage.json loads as a validated storage envelope against the bound instrument.
    for key, (row, *_rest) in V27_INSTITUTIONS.items():
        inst_id = f"INST-{row:07d}"
        envelope = StorageEnvelope.load(inst_dir_of(run_dir, inst_id) / "6_storage.json",
                                        run_dir / "final" / "instruments", artifact_root=run_dir)
        assert envelope.data["setup_pointer"] == instrument_id and envelope.data["institution_id"] == inst_id
        if key == "valtorde":
            assert any(r.get("values", {}).get("core.source_language") == "fr"
                       for r in envelope.data["sources"].values())

    # Outcomes from the run report.
    report = {r["institution_id"]: r for r in compute_institution_report(run_dir)}
    assert {k: r["final_status"] for k, r in report.items()} == {
        "INST-0000001": "EVIDENCE_FOUND", "INST-0000002": "NO_EVIDENCE_FOUND",
        "INST-0000003": "NO_EVIDENCE_FOUND"}
    assert report["INST-0000001"]["consolidated_row_count"] >= 1


def test_v27_launch_with_the_real_factory_is_refused_at_entry_before_any_spend(tmp_path: Path, monkeypatch):
    """With no injected mocks the real factory's dispatch is refused at entry (ruling 36 a: the default
    per-page builder; and the X35 gate, were the wording off its Q160 pin), before planning or
    any Stage 1-4 call, and no client is constructed. A missing extractor key or an unset
    v27_runtime is refused too."""
    from g3o.persist.stage6_adapters import MissingUpstreamError
    from g3o.run.presweep import perpage_inputs_v27 as pin
    from g3o.run.presweep import v27_entry
    from tests.test_e2e_perpage_v27 import TRUE

    _v27_refuse_real_clients(monkeypatch)
    calls: list[str] = []

    def no_spend(*_a, **_k):
        calls.append("stage 1-4 client")
        raise AssertionError("a Stage 1-4 client was called before the v2.7 entry refusal")

    monkeypatch.setattr(ps.stage_discovery, "search_google_detailed", no_spend)
    monkeypatch.setattr(ps.stage_scrape, "scrape_url", no_spend)
    monkeypatch.setattr(batch_client, "submit_batch", no_spend)
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)
    config = _v27_config(tmp_path)
    run_dir = config.runs_dir / config.run_id

    from g3o.extract import x35_client

    # Codebook r16 leaves nothing unproduced (MISSING_PRODUCERS is empty: the default builder is allowed at
    # entry); ruling 36 a's refusal is tested with a simulated missing producer.
    assert pin.MISSING_PRODUCERS == ()
    monkeypatch.setattr(pin, "MISSING_PRODUCERS", (pin.VALUES_MISSING,))
    with pytest.raises(MissingUpstreamError, match="ruling 36 a"):  # Q160 approved: X35 passes entry
        launch(config, credentials=Credentials(**V27_KEYS))
    assert not run_dir.exists() and calls == []

    monkeypatch.setattr(x35_client, "X35_INSTRUCTION_APPROVED_SHA256", "0" * 64)  # a wording off the pin
    with pytest.raises(ValueError, match="run_entailment"):  # the X35 gate comes first
        launch(config, credentials=Credentials(**V27_KEYS))
    assert not run_dir.exists() and calls == []
    monkeypatch.setattr(v27_entry, "x35_entail_fn", lambda settings, creds: lambda q, text: TRUE)

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        launch(config, credentials=Credentials(**{**V27_KEYS, "anthropic_api_key": None}))
    with pytest.raises(ValueError, match="no default client"):
        launch(_v27_config(tmp_path, v27_runtime=None), credentials=Credentials(**V27_KEYS))
    assert not run_dir.exists() and calls == []


# ---------------------------------------------------------------------------
# v2.7 follow-leg e2e (gate 5, second half; overnight 2026-11-16 O3-3)
# ---------------------------------------------------------------------------
#
# ``launch()`` on a v2.7 config with the follow leg on: the real ``FollowLeg``
# over a fake fetch serving one followed page, X35 through the real
# ``AnthropicX35Client`` over the fake ``anthropic`` module (its three gates,
# Q158 a, Q159 a and Q160, are open in the shipped defaults),
# and the default extractor mode ``mix`` (PI ruling 134): first-round page
# requests go through the fake Message Batches API, so the per-page stage runs
# in waves (``perpage_batch_v27.run_waves``); follow-ups and Stage 6 are live.
#
# Codebook dependence. Under the signed r15 pin the per-page assembler refuses
# ``core.developer`` / ``developer_basis`` / ``stage_as_of_basis`` on any page
# with an activity (``REFUSED_ACTIVITY_ITEMS_R15``: a stage stop), and the
# default builder is refused at entry (ruling 36 a). So the r15 case follows to a
# page with NO activity and injects that page's row values as it injects the
# searched pages' (``_ExplicitRowValues.followed``). The r16 case (the UNSIGNED
# candidate, ``r16_candidate.R16_CANDIDATE_SHA256``) runs on the default builder
# and the real assembler, with an activity on the followed page; it is skipped
# unless the generated codebook pin is the candidate. Assertions that depend on
# the candidate are marked ``# r16-candidate``.

V27_FOLLOWED_URL = "https://quillfield.example.gov/annual-report"  # the official host: typed by rule, no residual
V27_FOLLOWED_TEXT = ("The council's annual report lists its services, its staff numbers and its budget for the "
                     "year. It describes how letters to residents are reviewed by a senior officer before they "
                     "are sent, and how complaints are answered within ten working days.")
V27_FOLLOWED_SENTENCE = "Staff in the complaints team now use Copilot to draft first replies."
#: the quillfield passage the pass-1 link task quotes for its one stored link (jev: page_complete yes)
V27_LINK_PASSAGE = "Staff review every draft before it is sent"


def _v27_follow_world(tmp_path: Path, monkeypatch, *, followed_text: str,
                      followed_activities: list[Any]) -> dict[str, Any]:
    """Stages 1-4 stubbed (quillfield's page stores one link, to the followed page), jev, the fake
    ``anthropic`` module (extractor, Message Batches, X35), the X35 gates opened for this test,
    and the follow seam: a ``FakeFetch`` serving the followed page."""
    import sys

    from g3o.classify import jev_page_code as jpc
    from g3o.common import cost_monitor, jev_client
    from g3o.extract import x35_client
    from g3o.run.presweep import v27_entry
    from tests.test_e2e_perpage_v27 import ANSWERS, RELATIONS, FakeJev
    from tests.test_follow_v27 import FakeFetch

    seen = _v27_stub_stages_1_to_4_clients(monkeypatch)
    quill = V27_INSTITUTIONS["quillfield"][3]
    stub_scrape = ps.stage_scrape.scrape_url

    def scrape(url: str, **kwargs) -> RenderedPage:  # T-014: quillfield's stored links name the followed page
        page = stub_scrape(url, **kwargs)
        if url != quill:
            return page
        return page.model_copy(update={"links": [{"url": V27_FOLLOWED_URL, "anchor_text": "annual report",
                                                  "context": V27_LINK_PASSAGE, "source": "html"}]})

    monkeypatch.setattr(ps.stage_scrape, "scrape_url", scrape)

    def verdict(st: dict[str, Any]) -> str:  # "Copilot" confirms an activity, as in the e2e above
        return "confirms_activity" if "Copilot" in st.get("page_text", "") else "no_genai"

    def complete(st: dict[str, Any]) -> str | None:  # only quillfield's searched page refers onward
        return "yes" if V27_LINK_PASSAGE in st.get("page_text", "") else None

    jev = FakeJev({**ANSWERS, jpc.VERDICT: verdict, jpc.COMPLETE: complete}, RELATIONS)
    monkeypatch.setattr(_FakeTypeSafeClient, "instances", [])
    monkeypatch.setattr(_FakeTypeSafeClient, "answer", jev)
    monkeypatch.setattr(jev_client.ts, "TypeSafeClient", _FakeTypeSafeClient)
    # The extractor, the Message Batches API and X35: one fake anthropic SDK module.
    extractor: dict[str, list[Any]] = {"clients": [], "max_retries": [], "params": []}
    module = _v27_fake_anthropic_module(extractor, pages={V27_FOLLOWED_URL: (followed_text, followed_activities)},
                                        links={quill: [(V27_FOLLOWED_URL, V27_LINK_PASSAGE)]})
    monkeypatch.setitem(sys.modules, "anthropic", module)
    # X35: Q159 a (probability source "stated"), Q158 a (pricing) and Q160 (wording) are ruled in the
    # module defaults.
    assert x35_client.X35_PROBABILITY_SOURCE == "stated"
    assert cost_monitor.X35_PRICING_RULED is True and cost_monitor.V27_UNPRICED_PARTS == {}
    assert x35_client.X35_INSTRUCTION_APPROVED_SHA256 == x35_client.x35_instruction_sha256()
    # The follow seam (T-025): the real FollowLeg over a fake fetch serving the followed page.
    fetch = FakeFetch({V27_FOLLOWED_URL: followed_text})
    monkeypatch.setattr(v27_entry, "follow_fetch", lambda config: fetch)
    return {"seen": seen, "jev": jev, "extractor": extractor, "fetch": fetch}


def _v27_page_requests(params: list[dict[str, Any]]) -> list[str]:
    """The user messages of the per-page extractor requests (pass 1 / pass 2) among ``params``."""
    return [p["messages"][0]["content"] for p in params if "\nPAGE ADDRESS: " in p["messages"][0]["content"]]


def test_v27_launch_follows_a_link_through_stage6_in_mix_mode_with_x35(tmp_path: Path, monkeypatch):
    """Gate 5 (second half): the follow leg through Stage 6 on the real entry, every provider faked.

    quillfield's searched page selects its one stored link; the real follow leg fetches it (once),
    the followed page (no activity: r15) is coded like a searched page and its source row reaches
    Stage 6, where ``core.confidence`` is produced (PI ruling 140, P12). X35 runs through
    ``AnthropicX35Client``; the extractor runs in mix mode (first-round page requests batched, the
    rest live). Holds under r15 and under the r16 candidate (one branch marked ``# r16-candidate``)."""
    from g3o.codebook.r16_candidate import r16_active
    from g3o.common import cost_monitor
    from g3o.common import source_fields as sf
    from g3o.common.paths import institution_dir
    from g3o.common.storage import StorageEnvelope
    from g3o.report.outcomes import compute_institution_report
    from g3o.run.presweep import follow_v27 as fv
    from g3o.run.presweep import orchestrator as orch
    from g3o.run.presweep import perpage_batch_v27 as pb
    from g3o.run.presweep import source_row_v27 as srow
    from g3o.run.presweep import stage_perpage_v27 as pp
    from g3o.run.presweep import v27_entry
    from tests.test_e2e_perpage_v27 import SETTINGS

    world = _v27_follow_world(tmp_path, monkeypatch, followed_text=V27_FOLLOWED_TEXT, followed_activities=[])
    extractor, fetch = world["extractor"], world["fetch"]
    builder = _ExplicitRowValues(extra_activities={V27_FOLLOWED_URL: []})
    monkeypatch.setattr(v27_entry, "perpage_inputs_builder", lambda config: builder)
    real_followed = fv.FollowLeg.followed_upstream

    def followed_upstream(self, rendered, page, hop, grouping):  # the real leg's upstream, rows injected
        return builder.followed(real_followed(self, rendered, page, hop, grouping), page)

    monkeypatch.setattr(fv.FollowLeg, "followed_upstream", followed_upstream)

    # Ruling 140: no standing source-row refusal, so nothing refuses the run at entry for a source item.
    assert srow.REFUSED_SOURCE_ITEMS == {}
    if r16_active():  # r16-candidate: no activity item is refused either
        assert srow.entry_refused_items() == ()
    else:  # r15: only the three r16 activity items (so ruling 36 a keeps the injected builder)
        assert set(srow.entry_refused_items()) == set(srow.REFUSED_ACTIVITY_ITEMS_R15)

    config = _v27_config(tmp_path, run_id="v27-follow")
    assert config.v27_extractor_mode == pb.MIX == pb.DEFAULT_EXTRACTOR_MODE  # PI ruling 134 default
    receipt = launch(config, credentials=Credentials(**V27_KEYS), session_id="sess-v27-follow", invocation="api")
    summary = receipt.summary
    run_dir = Path(summary["run_dir"])

    # The follow leg: the one selected link was fetched once, at hop 1 from quillfield's searched page.
    assert fetch.calls == [V27_FOLLOWED_URL]
    quill_dir = institution_dir(run_dir, "INST-0000001")
    state = json.loads((quill_dir / fv.FOLLOW_DIR / fv.STATE_FILE).read_text(encoding="utf-8"))
    assert [(r["url"], r["hop"]) for r in state["records"]] == [(V27_FOLLOWED_URL, 1)]
    assert V27_FOLLOWED_URL in builder.page_fields  # its D1 a page fields were built by the real leg
    for n in (2, 3):  # nothing else was followed
        # The leg saves its state after any round with a coded page (review L4), so the file may exist;
        # it must hold no follow record and no link left unfollowed (build 7c1483eb).
        other = institution_dir(run_dir, f"INST-{n:07d}") / fv.FOLLOW_DIR / fv.STATE_FILE
        if other.exists():
            other_state = json.loads(other.read_text(encoding="utf-8"))
            assert other_state["records"] == [] and other_state["not_followed"] == []
            assert other_state["followed"] == 0

    # Mix mode (PI ruling 134): first-round page requests were batched, each answered once; nothing
    # batched was also sent live (no double spend); any later request would be live.
    usage = summary[orch.V27_USAGE_KEY]
    batched, batched_users = extractor["batched"], _v27_page_requests(extractor["batched_params"])
    live_users = _v27_page_requests(extractor["params"])
    assert batched and all(pb.is_first_round(cid) for cid in batched)
    assert len(set(batched)) == len(batched)
    assert usage[orch.V27_PERPAGE_SPAN]["batched_requests"] == len(batched)
    assert not set(batched_users) & set(live_users)
    assert any(f"PAGE ADDRESS: {V27_INSTITUTIONS['quillfield'][3]}\n" in u for u in batched_users)
    assert extractor["max_retries"] and set(extractor["max_retries"]) == {0}  # PI ruling 135 a
    lines = pb.batch_journal_path(run_dir).read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in lines if line.strip()]
    assert kinds.count("submitted") == kinds.count("submit_intent") == kinds.count("collected") >= 1

    # X35 through the real AnthropicX35Client on the pinned x35_model, journaled per call.
    x35 = extractor["x35"]
    assert x35 and {p["model"] for p in x35} == {SETTINGS.x35_model}
    assert sum(usage[span].get("x35_calls", 0) for span in usage) == len(x35)
    # Every extractor request, live or batched, is on the pinned extractor model. In this world every
    # extractor request is a first-round page request, so all were batched and the live calls are X35
    # only (build ab73f90b: the live non-X35 set was empty).
    live_models = {p["model"] for p in extractor["params"] if p not in x35}
    assert live_models | {p["model"] for p in extractor["batched_params"]} == {SETTINGS.extractor_model}
    cost = json.loads((run_dir / "_cost_report.json").read_text(encoding="utf-8"))[orch.V27_COST_KEY]
    assert cost
    for span in cost.values():  # Q158 a: X35 is priced, never reported as pending
        assert span["parts"]["x35"].get("reason") != cost_monitor.X35_PRICING_PENDING

    # Every institution was ready after the waves and written by Stage 6; nothing held or failed.
    assert summary["n_institutions"] == 3
    assert summary["n_perpage_ready"] == 3
    assert summary["n_perpage_held"] == 0 and summary["n_perpage_failed_pages"] == 0
    assert summary["n_stage6_written"] == 3
    assert summary["n_stage6_held"] == summary["n_stage6_failed"] == 0

    # The followed page's source row is in quillfield's Stage 6 storage, with core.confidence
    # produced by Stage 6 (P12): the per-page row never carries it.
    envelope = StorageEnvelope.load(quill_dir / "6_storage.json", run_dir / "final" / "instruments",
                                    artifact_root=run_dir)
    rows = [r.get("values", {}) for r in envelope.data["sources"].values()]
    followed = [v for v in rows if v.get(sf.URL) == V27_FOLLOWED_URL]
    assert len(followed) == 1
    (row,) = followed
    assert row[sf.DISCOVERY] == "followed_hop_1"
    assert row[sf.TEXT_SOURCE] == sf.TEXT_SOURCE_NEW_RUN
    assert sf.CONFIDENCE not in pp.SOURCE_ROW_ITEMS
    assert all(sf.CONFIDENCE not in sv for sv in builder.source_values[V27_FOLLOWED_URL].values())
    assert row.get(sf.CONFIDENCE) is not None

    report = {r["institution_id"]: r for r in compute_institution_report(run_dir)}
    assert {k: r["final_status"] for k, r in report.items()} == {
        "INST-0000001": "EVIDENCE_FOUND", "INST-0000002": "NO_EVIDENCE_FOUND",
        "INST-0000003": "NO_EVIDENCE_FOUND"}


def _r16_candidate_active() -> bool:
    from g3o.codebook.r16_candidate import r16_active

    return r16_active()


@pytest.mark.skipif(not _r16_candidate_active(),
                    reason="r16-candidate: needs the generated codebook pin to equal the UNSIGNED r16 candidate "
                           "(R16_CANDIDATE_SHA256); under the signed r15 pin the default builder is refused "
                           "at entry (ruling 36 a) and a followed activity stops the per-page assembler")
def test_v27_launch_follows_to_an_activity_page_on_the_default_builder_r16_candidate(tmp_path: Path,
                                                                                     monkeypatch):
    """r16-candidate (every assertion): the default per-page builder and the real T-015 assembler, no
    injected row values; the followed page carries an activity (``core.developer`` is a pass-1 field
    under the candidate). The run is not refused at entry and not stopped: the followed page is fetched,
    coded and assembled (followed, hop 1), and every institution ends ready or held on its own row data
    (ruling 97 b). Which of the two is not fixed here: in mix mode a batched pass-1 response carries no
    request id, which the D-007 provenance of a quote-step record requires (open question Q178)."""
    from g3o.common.paths import institution_dir
    from g3o.extract.batch import url_hash
    from g3o.run.presweep import perpage_inputs_v27 as pin
    from g3o.run.presweep import source_row_v27 as srow
    from g3o.run.presweep import stage_perpage_v27 as pp
    from tests.test_e2e_perpage_v27 import assemble_spy

    assert pin.MISSING_PRODUCERS == ()  # r16-candidate: the default builder is allowed at entry
    text = V27_FOLLOWED_TEXT + " " + V27_FOLLOWED_SENTENCE
    world = _v27_follow_world(tmp_path, monkeypatch, followed_text=text,
                              followed_activities=[("Copilot replies", "Copilot", V27_FOLLOWED_SENTENCE)])
    assembled: dict[str, dict[str, Any]] = {}

    def record(page, rows, kw):  # records the assembler's keywords; returns None so the rows are kept
        assembled.setdefault(page.page_id, kw)

    monkeypatch.setattr(srow, "assemble", assemble_spy(srow.assemble, record))

    receipt = launch(_v27_config(tmp_path, run_id="v27-follow-r16"), credentials=Credentials(**V27_KEYS),
                     session_id="sess-v27-follow-r16", invocation="api")
    summary = receipt.summary
    run_dir = Path(summary["run_dir"])

    assert world["fetch"].calls == [V27_FOLLOWED_URL]
    kw = assembled[url_hash(V27_FOLLOWED_URL)]
    assert (kw["followed"], kw["hop"]) == (True, 1)
    assert world["extractor"]["batched"] and world["extractor"]["x35"]
    assert summary["n_perpage_ready"] + summary["n_perpage_held"] == 3
    for n in range(1, 4):
        held = institution_dir(run_dir, f"INST-{n:07d}") / pp.WORK_DIR / pp.HELD_FILE
        if held.exists():
            stages = {h["stage"] for h in json.loads(held.read_text(encoding="utf-8"))["held"]}
            assert stages <= {pp.ROW_VALUE_REFUSED}, stages
