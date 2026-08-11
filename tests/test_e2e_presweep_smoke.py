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

from g3o.common import attrition, batch_client
from g3o.common.artifact_io import ARTIFACT_SUFFIX, glob_artifacts
from g3o.common.batch_client import BatchHandle, BatchResult, BatchStatus
from g3o.common.credentials import fingerprint
from g3o.common.run_state import done_path, state_dir
from g3o.discovery import serper_client
from g3o.extract.batch import make_custom_id, url_hash
from g3o.run import presweep as ps
from g3o.run.presweep import STAGES, PresweepConfig, institution_record, run_presweep
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
        "master_row_id", "country", "government_level", "branch",
        "institution_type", "institution_name", "website",
        "source_dataset_id", "source_url", "source_file",
        "retrieval_date", "notes",
    ]
    rows = [
        {
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

    summary = run_presweep(config)

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
