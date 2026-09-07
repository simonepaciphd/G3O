"""Tests for the T1 reproducibility floor (Session F.6, 2026-06-11).

Covers the three T1 surfaces:

1. The pinned generation parameter — every serialized Batch API job line
   carries ``reasoning_effort`` at the signed-off value (``"medium"``), and
   the chunk-size computation counts the pinned bytes.
2. Response-side provenance capture — ``run_chunked_stage`` records the
   versioned model id(s) and ``system_fingerprint``(s) per fetched chunk.
3. The manifest surface — ``run_generation_parameters`` at plan time, the
   resume guard on a changed pin, and ``update_manifest_llm_provenance``
   folding state-file provenance into ``manifest.json``.

The frozen-input golden harness lives in ``test_reproducibility_regression.py``.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from g3o.common import batch_client
from g3o.common.batch_client import (
    DEFAULT_ENDPOINT,
    DEFAULT_REASONING_EFFORT,
    BatchHandle,
    BatchJob,
    BatchResult,
    BatchStatus,
    _serialize_job_line,
)
from g3o.common.run_state import done_path, run_chunked_stage
from g3o.run.presweep import (
    PresweepConfig,
    build_manifest,
    plan_run,
    stratified_sample,
    update_manifest_llm_provenance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job(custom_id: str = "job-1") -> BatchJob:
    return BatchJob(
        custom_id=custom_id,
        messages=[{"role": "user", "content": f"hello {custom_id}"}],
    )


def _write_master(path: Path, n: int) -> Path:
    fields = [
        "institution_uid", "master_row_id", "institution_name", "country",
        "branch", "government_level", "institution_type", "website",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for i in range(1, n + 1):
            w.writerow(
                {
                    "institution_uid": f"G3O-I-{i:08d}",
                    "master_row_id": str(i),
                    "institution_name": f"Institution {i}",
                    "country": f"C{i % 3}",
                    "branch": "executive",
                    "government_level": "national" if i % 2 else "subnational",
                    "institution_type": "agency",
                    "website": "",
                }
            )
    return path


def _config(tmp_path: Path, master: Path, *, run_id: str) -> PresweepConfig:
    return PresweepConfig(
        run_id=run_id,
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=4,
        seed=22294,
    )


# ---------------------------------------------------------------------------
# 1. The reasoning_effort pin
# ---------------------------------------------------------------------------


def test_pin_value_is_the_signed_off_medium():
    # The pin itself is a researcher decision (2026-06-11); a silent change
    # to the constant must trip a test, not just the golden hashes.
    assert DEFAULT_REASONING_EFFORT == "medium"


def test_serialized_job_line_carries_the_pin_by_default():
    line = json.loads(
        _serialize_job_line(
            _job(), model="gpt-5-nano", response_format=None, endpoint=DEFAULT_ENDPOINT
        )
    )
    assert line["body"]["reasoning_effort"] == "medium"


def test_serialize_reasoning_effort_none_omits_the_param():
    line = json.loads(
        _serialize_job_line(
            _job(), model="gpt-5-nano", response_format=None,
            endpoint=DEFAULT_ENDPOINT, reasoning_effort=None,
        )
    )
    assert "reasoning_effort" not in line["body"]


def test_chunk_sizing_counts_the_pinned_bytes():
    # split_jobs_into_chunks must size the exact bytes submit_batch uploads,
    # pin included — the F2 size-cap guarantee depends on the two paths
    # serializing identically.
    with_pin = _serialize_job_line(
        _job(), model="gpt-5-nano", response_format=None, endpoint=DEFAULT_ENDPOINT
    )
    without = _serialize_job_line(
        _job(), model="gpt-5-nano", response_format=None,
        endpoint=DEFAULT_ENDPOINT, reasoning_effort=None,
    )
    assert len(with_pin) > len(without)
    chunks = batch_client.split_jobs_into_chunks(
        [_job("a"), _job("b")], model="gpt-5-nano",
        max_bytes=len(with_pin) + 1,  # room for one pinned line, not two
    )
    assert [len(c) for c in chunks] == [1, 1]


# ---------------------------------------------------------------------------
# 2. BatchResult provenance properties
# ---------------------------------------------------------------------------


def test_batch_result_exposes_response_model_and_fingerprint():
    r = BatchResult(
        custom_id="x", success=True,
        response={
            "body": {
                "model": "gpt-5-nano-2025-08-07",
                "system_fingerprint": "fp_abc123",
                "choices": [{"message": {"content": "{}"}}],
            }
        },
        error=None,
    )
    assert r.response_model == "gpt-5-nano-2025-08-07"
    assert r.system_fingerprint == "fp_abc123"


def test_batch_result_provenance_absent_is_none():
    r = BatchResult(
        custom_id="x", success=True,
        response={"body": {"choices": [{"message": {"content": "{}"}}]}},
        error=None,
    )
    assert r.response_model is None
    assert r.system_fingerprint is None
    failed = BatchResult(custom_id="y", success=False, response=None, error={"m": "e"})
    assert failed.response_model is None
    assert failed.system_fingerprint is None


# ---------------------------------------------------------------------------
# 3. run_chunked_stage records per-chunk provenance
# ---------------------------------------------------------------------------


def test_fetched_chunk_records_response_provenance(tmp_path: Path, monkeypatch):
    def _submit(jobs, *, model, completion_window, endpoint, metadata, client=None):
        return BatchHandle(
            batch_id="batch-1", input_file_id="file-1",
            submitted_at=datetime.now(timezone.utc), n_jobs=len(jobs),
        )

    def _poll(batch_id, *, client=None):
        return BatchStatus(
            batch_id=batch_id, status="completed", request_counts={},
            output_file_id=None, error_file_id=None,
        )

    def _fetch(batch_id, *, client=None, status=None):
        for cid, fp in (("J0", "fp_aaa"), ("J1", None)):
            body: dict[str, Any] = {
                "model": "gpt-5-nano-2025-08-07",
                "choices": [{"message": {"content": "ok"}}],
            }
            if fp is not None:
                body["system_fingerprint"] = fp
            yield BatchResult(
                custom_id=cid, success=True, response={"body": body}, error=None
            )

    monkeypatch.setattr(batch_client, "submit_batch", _submit)
    monkeypatch.setattr(batch_client, "poll_batch", _poll)
    monkeypatch.setattr(batch_client, "fetch_results", _fetch)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda *a, **k: [])

    seen: list[str] = []
    run_chunked_stage(
        tmp_path, "extract", [_job("J0"), _job("J1")],
        run_id="r1", model="gpt-5-nano", poll_interval=0, max_wait=10,
        process_chunk_results=lambda results: seen.extend(
            r.custom_id for r in results
        ),
    )
    assert sorted(seen) == ["J0", "J1"]
    done = json.loads(done_path(tmp_path, "extract").read_text(encoding="utf-8"))
    entry = done["chunks"]["1"]
    assert entry["response_models"] == ["gpt-5-nano-2025-08-07"]
    assert entry["system_fingerprints"] == ["fp_aaa"]


# ---------------------------------------------------------------------------
# 4. Manifest surface
# ---------------------------------------------------------------------------


def test_manifest_records_generation_parameters(tmp_path: Path):
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, run_id="t1a")
    rows = list(csv.DictReader(open(master, encoding="utf-8")))
    sample = stratified_sample(rows, sample_size=4, seed=22294)
    manifest = build_manifest(config, sample)
    assert manifest["run_generation_parameters"] == {"reasoning_effort": "medium"}


def _seed_resume_state(run_dir: Path) -> None:
    (run_dir / "_state").mkdir(parents=True, exist_ok=True)
    (run_dir / "_state" / "discovery_general.json").write_text("{}", encoding="utf-8")


def test_manifest_guard_aborts_on_changed_generation_parameters(tmp_path: Path):
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, run_id="t1b")
    plan_run(config)
    run_dir = config.runs_dir / "t1b"
    _seed_resume_state(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_generation_parameters"] = {"reasoning_effort": "low"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="run_generation_parameters"):
        plan_run(config)


def test_manifest_guard_passes_legacy_manifest_without_generation_params(
    tmp_path: Path,
):
    # Manifests written before 2026-06-11 lack the key; resume must not trip.
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, run_id="t1c")
    plan_run(config)
    run_dir = config.runs_dir / "t1c"
    _seed_resume_state(run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["run_generation_parameters"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    plan_run(config)  # no raise


def test_update_manifest_llm_provenance_aggregates_state(tmp_path: Path):
    run_dir = tmp_path / "runs" / "t1d"
    (run_dir / "_state" / ".done").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "t1d"}), encoding="utf-8"
    )
    # A completed stage in .done/ ...
    (run_dir / "_state" / ".done" / "extract.json").write_text(
        json.dumps(
            {
                "schema_version": 2, "stage": "extract", "run_id": "t1d",
                "model": "gpt-5-nano",
                "chunks": {
                    "1": {
                        "batch_id": "batch-a", "fetched_at": "2026-06-11T00:00:00Z",
                        "response_models": ["gpt-5-nano-2025-08-07"],
                        "system_fingerprints": ["fp_aaa"],
                    },
                    "2": {
                        "batch_id": "batch-b", "fetched_at": "2026-06-11T00:01:00Z",
                        "response_models": ["gpt-5-nano-2025-08-07"],
                        "system_fingerprints": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    # ... an in-flight stage in _state/ ...
    (run_dir / "_state" / "validate.json").write_text(
        json.dumps(
            {
                "schema_version": 2, "stage": "validate", "run_id": "t1d",
                "model": "gpt-5-nano",
                "chunks": {
                    "1": {
                        "batch_id": "batch-c", "fetched_at": None,
                        "response_models": None, "system_fingerprints": None,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    # ... and a no-batch done marker that must be skipped.
    (run_dir / "_state" / ".done" / "scrape.json").write_text(
        json.dumps({"stage": "scrape", "no_batch": True}), encoding="utf-8"
    )

    block = update_manifest_llm_provenance(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["llm_provenance"] == block
    assert sorted(block) == ["extract", "validate"]
    extract = block["extract"]
    assert extract["request_model"] == "gpt-5-nano"
    assert extract["response_models"] == ["gpt-5-nano-2025-08-07"]
    assert extract["system_fingerprints"] == ["fp_aaa"]
    assert extract["batch_ids"] == ["batch-a", "batch-b"]
    assert extract["n_chunks_planned"] == 2
    assert extract["n_chunks_fetched"] == 2
    validate = block["validate"]
    assert validate["batch_ids"] == ["batch-c"]
    assert validate["n_chunks_fetched"] == 0
    assert validate["response_models"] == []


def test_update_manifest_llm_provenance_noop_without_state(tmp_path: Path):
    run_dir = tmp_path / "runs" / "t1e"
    run_dir.mkdir(parents=True)
    before = json.dumps({"run_id": "t1e"})
    (run_dir / "manifest.json").write_text(before, encoding="utf-8")
    assert update_manifest_llm_provenance(run_dir) == {}
    # Dry-run manifests are left byte-identical (no empty block written).
    assert (run_dir / "manifest.json").read_text(encoding="utf-8") == before
    # And no manifest at all is tolerated.
    assert update_manifest_llm_provenance(tmp_path / "nope") == {}
