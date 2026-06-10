"""Tests for `g3o.common.batch_client` — OpenAI Batch API single-owner client."""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError, RateLimitError
from tenacity import wait_none

from g3o.common import batch_client
from g3o.common.batch_client import (
    BatchJob,
    fetch_results,
    find_batches_by_metadata,
    poll_batch,
    split_jobs_into_chunks,
    submit_batch,
)

# ---------------------------------------------------------------------------
# Helpers — build mocks that mimic the OpenAI SDK shape.
# ---------------------------------------------------------------------------


def _stub_openai(
    *,
    file_id: str = "file-abc123",
    batch_id: str = "batch-xyz789",
    batch_status: str = "completed",
    output_file_id: str | None = "out-file-1",
    error_file_id: str | None = None,
    output_lines: list[dict[str, Any]] | None = None,
    error_lines: list[dict[str, Any]] | None = None,
    request_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Build a MagicMock that emulates the OpenAI client surface we touch."""
    client = MagicMock()

    file_obj = MagicMock()
    file_obj.id = file_id
    client.files.create.return_value = file_obj

    batch_obj = MagicMock()
    batch_obj.id = batch_id
    batch_obj.status = batch_status
    batch_obj.output_file_id = output_file_id
    batch_obj.error_file_id = error_file_id
    batch_obj.created_at = 1_700_000_000
    batch_obj.completed_at = 1_700_001_000 if batch_status == "completed" else None
    counts = MagicMock()
    rc = request_counts or {"total": 1, "completed": 1, "failed": 0}
    counts.total = rc["total"]
    counts.completed = rc["completed"]
    counts.failed = rc["failed"]
    batch_obj.request_counts = counts
    client.batches.create.return_value = batch_obj
    client.batches.retrieve.return_value = batch_obj

    def _content(file_id_arg: str) -> MagicMock:
        if file_id_arg == output_file_id and output_lines is not None:
            payload = "\n".join(json.dumps(line) for line in output_lines)
        elif file_id_arg == error_file_id and error_lines is not None:
            payload = "\n".join(json.dumps(line) for line in error_lines)
        else:
            payload = ""
        resp = MagicMock()
        resp.read.return_value = payload.encode("utf-8")
        return resp

    client.files.content.side_effect = _content
    return client


def _job(custom_id: str = "job-1", **kwargs: Any) -> BatchJob:
    return BatchJob(
        custom_id=custom_id,
        messages=[
            {"role": "system", "content": "system prefix"},
            {"role": "user", "content": f"hello {custom_id}"},
        ],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# submit_batch — JSONL serialization
# ---------------------------------------------------------------------------


def test_submit_serializes_jsonl_correctly():
    client = _stub_openai()
    response_format = {"type": "json_schema", "json_schema": {"name": "x"}}

    handle = submit_batch(
        [_job("job-1"), _job("job-2")],
        model="gpt-5-nano",
        response_format=response_format,
        client=client,
    )

    assert handle.batch_id == "batch-xyz789"
    assert handle.input_file_id == "file-abc123"
    assert handle.n_jobs == 2

    # Inspect the JSONL the client was asked to upload.
    file_arg = client.files.create.call_args.kwargs["file"]
    _, payload_io, _ = file_arg
    payload_io.seek(0)
    records = [
        json.loads(line)
        for line in payload_io.read().decode("utf-8").splitlines()
        if line
    ]
    assert len(records) == 2
    assert records[0]["custom_id"] == "job-1"
    assert records[0]["method"] == "POST"
    assert records[0]["url"] == "/v1/chat/completions"
    assert records[0]["body"]["model"] == "gpt-5-nano"
    assert records[0]["body"]["response_format"] == response_format
    assert records[0]["body"]["messages"][1]["content"] == "hello job-1"


def test_submit_per_job_response_format_overrides_default():
    client = _stub_openai()
    job_default = _job("default")
    job_override = _job(
        "override", response_format={"type": "json_schema", "json_schema": {"name": "y"}}
    )

    submit_batch(
        [job_default, job_override],
        response_format={"type": "json_schema", "json_schema": {"name": "x"}},
        client=client,
    )

    file_arg = client.files.create.call_args.kwargs["file"]
    _, payload_io, _ = file_arg
    payload_io.seek(0)
    records = [
        json.loads(line)
        for line in payload_io.read().decode("utf-8").splitlines()
        if line
    ]
    assert records[0]["body"]["response_format"]["json_schema"]["name"] == "x"
    assert records[1]["body"]["response_format"]["json_schema"]["name"] == "y"


def test_submit_passes_prompt_cache_key():
    client = _stub_openai()
    submit_batch(
        [_job("c", prompt_cache_key="g3o-classify-stage2-v1")],
        client=client,
    )
    file_arg = client.files.create.call_args.kwargs["file"]
    _, payload_io, _ = file_arg
    payload_io.seek(0)
    record = json.loads(payload_io.read().decode("utf-8").splitlines()[0])
    assert record["body"]["prompt_cache_key"] == "g3o-classify-stage2-v1"


def test_submit_rejects_duplicate_custom_id():
    client = _stub_openai()
    with pytest.raises(ValueError, match="duplicate custom_id"):
        submit_batch([_job("dup"), _job("dup")], client=client)


def test_submit_rejects_empty_jobs():
    client = _stub_openai()
    with pytest.raises(ValueError, match="empty"):
        submit_batch([], client=client)


# ---------------------------------------------------------------------------
# poll_batch — status handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,is_terminal,is_completed",
    [
        ("validating", False, False),
        ("in_progress", False, False),
        ("finalizing", False, False),
        ("completed", True, True),
        ("failed", True, False),
        ("expired", True, False),
        ("cancelled", True, False),
    ],
)
def test_poll_status_classifications(status, is_terminal, is_completed):
    client = _stub_openai(batch_status=status)
    s = poll_batch("batch-xyz789", client=client)
    assert s.status == status
    assert s.is_terminal is is_terminal
    assert s.is_completed is is_completed


def test_poll_coerces_request_counts():
    client = _stub_openai(
        request_counts={"total": 100, "completed": 80, "failed": 5}
    )
    s = poll_batch("batch-xyz789", client=client)
    assert s.request_counts == {"total": 100, "completed": 80, "failed": 5}


# ---------------------------------------------------------------------------
# fetch_results — output and error files
# ---------------------------------------------------------------------------


def test_fetch_results_parses_successful_output():
    output_lines = [
        {
            "custom_id": "job-1",
            "response": {
                "status_code": 200,
                "body": {"choices": [{"message": {"content": "ok-1"}}]},
            },
            "error": None,
        },
        {
            "custom_id": "job-2",
            "response": {
                "status_code": 200,
                "body": {"choices": [{"message": {"content": "ok-2"}}]},
            },
            "error": None,
        },
    ]
    client = _stub_openai(output_lines=output_lines)
    results = list(fetch_results("batch-xyz789", client=client))
    assert len(results) == 2
    assert results[0].custom_id == "job-1"
    assert results[0].success
    assert results[0].parsed_content == "ok-1"
    assert results[1].parsed_content == "ok-2"


def test_fetch_results_includes_errors():
    output_lines = [
        {
            "custom_id": "job-good",
            "response": {
                "status_code": 200,
                "body": {"choices": [{"message": {"content": "ok"}}]},
            },
            "error": None,
        },
    ]
    error_lines = [
        {
            "custom_id": "job-bad",
            "error": {"code": "invalid_request_error", "message": "bad input"},
        },
    ]
    client = _stub_openai(
        output_file_id="out-file-1",
        error_file_id="err-file-1",
        output_lines=output_lines,
        error_lines=error_lines,
    )
    results = list(fetch_results("batch-xyz789", client=client))
    assert {(r.custom_id, r.success) for r in results} == {
        ("job-good", True),
        ("job-bad", False),
    }
    bad = next(r for r in results if r.custom_id == "job-bad")
    assert bad.error is not None
    assert bad.error.get("code") == "invalid_request_error"


def test_fetch_results_refuses_non_terminal_batch():
    client = _stub_openai(batch_status="in_progress")
    with pytest.raises(RuntimeError, match="not terminal"):
        list(fetch_results("batch-xyz789", client=client))


# ---------------------------------------------------------------------------
# Tenacity retry behavior
# ---------------------------------------------------------------------------


@pytest.fixture
def fast_retry(monkeypatch):
    """Disable retry waits so the retry tests run quickly.

    Session F.1: retries are per-call — ``_create_input_file`` (tenacity) and
    ``_create_batch_with_reconcile`` (hand-rolled, ``_retry_sleep``) — never
    around the whole upload+create pair (review F6a).
    """
    for fn in (batch_client._create_input_file, poll_batch):
        monkeypatch.setattr(fn.retry, "wait", wait_none())
    monkeypatch.setattr(batch_client, "_retry_sleep", lambda attempt: None)


def _rate_limit() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/files")
    response = httpx.Response(status_code=429, request=request)
    return RateLimitError(message="rate limited", response=response, body=None)


def _conn_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("GET", "https://api.test"))


def test_submit_retries_on_rate_limit(fast_retry):
    client = _stub_openai()
    file_obj = MagicMock()
    file_obj.id = "file-after-retry"
    client.files.create.side_effect = [_rate_limit(), file_obj]

    handle = submit_batch([_job()], client=client)
    assert handle.input_file_id == "file-after-retry"
    assert client.files.create.call_count == 2


def test_poll_retries_on_connection_error(fast_retry):
    client = _stub_openai(batch_status="in_progress")
    good = client.batches.retrieve.return_value
    client.batches.retrieve.side_effect = [_conn_error(), good]

    s = poll_batch("batch-xyz789", client=client)
    assert s.status == "in_progress"
    assert client.batches.retrieve.call_count == 2


# ---------------------------------------------------------------------------
# split_jobs_into_chunks (Session F.1, review F2)
# ---------------------------------------------------------------------------


def _line_size(job: BatchJob) -> int:
    return len(
        batch_client._serialize_job_line(
            job, model="gpt-5-nano", response_format=None,
            endpoint=batch_client.DEFAULT_ENDPOINT,
        )
    )


def test_split_by_size_cap_is_deterministic_and_order_preserving():
    jobs = [_job(f"job-{i}") for i in range(10)]
    per_line = max(_line_size(j) for j in jobs)
    chunks = split_jobs_into_chunks(jobs, model="gpt-5-nano", max_bytes=3 * per_line)
    assert [len(c) for c in chunks] == [3, 3, 3, 1]
    flat = [j.custom_id for c in chunks for j in c]
    assert flat == [f"job-{i}" for i in range(10)]  # input order preserved
    again = split_jobs_into_chunks(jobs, model="gpt-5-nano", max_bytes=3 * per_line)
    assert [[j.custom_id for j in c] for c in again] == [
        [j.custom_id for j in c] for c in chunks
    ]


def test_split_by_request_count_cap():
    jobs = [_job(f"job-{i}") for i in range(10)]
    chunks = split_jobs_into_chunks(jobs, model="gpt-5-nano", max_requests=4)
    assert [len(c) for c in chunks] == [4, 4, 2]


def test_split_single_fits_in_one_chunk_at_default_caps():
    jobs = [_job(f"job-{i}") for i in range(5)]
    chunks = split_jobs_into_chunks(jobs, model="gpt-5-nano")
    assert len(chunks) == 1
    assert len(chunks[0]) == 5


def test_split_oversized_single_job_raises_naming_job_and_f3():
    big = _job("oversized")
    big.messages[1]["content"] = "x" * 5000
    with pytest.raises(ValueError) as exc_info:
        split_jobs_into_chunks([big], model="gpt-5-nano", max_bytes=1024)
    msg = str(exc_info.value)
    assert "oversized" in msg
    assert "F3" in msg


def test_split_rejects_duplicate_custom_id_and_empty_list():
    with pytest.raises(ValueError, match="duplicate custom_id"):
        split_jobs_into_chunks([_job("d"), _job("d")], model="gpt-5-nano")
    with pytest.raises(ValueError, match="empty"):
        split_jobs_into_chunks([], model="gpt-5-nano")


def test_submit_refuses_payload_over_documented_file_limit(monkeypatch):
    client = _stub_openai()
    monkeypatch.setattr(batch_client, "BATCH_MAX_INPUT_FILE_BYTES", 64)
    with pytest.raises(ValueError, match="split_jobs_into_chunks"):
        submit_batch([_job("too-big")], client=client)
    client.files.create.assert_not_called()


# ---------------------------------------------------------------------------
# find_batches_by_metadata (Session F.1, review F6)
# ---------------------------------------------------------------------------


def _batch_obj(
    batch_id: str, *, status: str = "in_progress", metadata: dict | None = None
) -> MagicMock:
    b = MagicMock()
    b.id = batch_id
    b.status = status
    b.metadata = metadata or {}
    b.output_file_id = None
    b.error_file_id = None
    b.created_at = None
    b.completed_at = None
    b.request_counts = None
    return b


def _page(batches: list, *, has_more: bool = False) -> MagicMock:
    page = MagicMock()
    page.data = batches
    page.has_more = has_more
    return page


_CHUNK_MD = {"g3o_run_id": "run-1", "g3o_stage": "extract", "g3o_chunk": "1"}


def test_find_batches_by_metadata_exact_match_only():
    near_miss = dict(_CHUNK_MD, g3o_chunk="2")
    client = MagicMock()
    client.batches.list.return_value = _page(
        [
            _batch_obj("b-yes", metadata=_CHUNK_MD),
            _batch_obj("b-no", metadata=near_miss),
            _batch_obj("b-none", metadata=None),
        ]
    )
    matches = find_batches_by_metadata(_CHUNK_MD, client=client)
    assert [m.batch_id for m in matches] == ["b-yes"]


def test_find_batches_by_metadata_paginates_until_has_more_false():
    client = MagicMock()
    page1 = _page([_batch_obj("b-other", metadata={})], has_more=True)
    page2 = _page([_batch_obj("b-match", metadata=_CHUNK_MD)], has_more=False)
    client.batches.list.side_effect = [page1, page2]
    matches = find_batches_by_metadata(_CHUNK_MD, client=client)
    assert [m.batch_id for m in matches] == ["b-match"]
    assert client.batches.list.call_count == 2
    # Second call cursors after the last batch of page 1.
    assert client.batches.list.call_args.kwargs["after"] == "b-other"


def test_find_batches_by_metadata_bounded_pages():
    client = MagicMock()
    client.batches.list.return_value = _page(
        [_batch_obj("b-x", metadata={})], has_more=True
    )
    find_batches_by_metadata(_CHUNK_MD, client=client, max_pages=3)
    assert client.batches.list.call_count == 3


# ---------------------------------------------------------------------------
# batches.create reconcile-on-retry (Session F.1, review F6a)
# ---------------------------------------------------------------------------


def test_create_lost_response_reconciles_instead_of_double_creating(fast_retry):
    """A retryable failure of batches.create with identifying metadata must
    reconcile by metadata and adopt — never blindly re-create."""
    client = _stub_openai()
    client.batches.create.side_effect = _conn_error()
    client.batches.list.return_value = _page(
        [_batch_obj("batch-already-live", metadata=_CHUNK_MD)]
    )
    handle = submit_batch([_job()], metadata=_CHUNK_MD, client=client)
    assert handle.batch_id == "batch-already-live"
    assert client.batches.create.call_count == 1  # no second create


def test_create_retries_fresh_when_reconcile_finds_nothing(fast_retry):
    client = _stub_openai()
    good = client.batches.create.return_value
    client.batches.create.side_effect = [_conn_error(), good]
    client.batches.list.return_value = _page([])
    handle = submit_batch([_job()], metadata=_CHUNK_MD, client=client)
    assert handle.batch_id == "batch-xyz789"
    assert client.batches.create.call_count == 2


def test_create_without_identifying_metadata_plain_retry(fast_retry):
    """Metadata-less callers (standalone CLI) keep plain per-call retry and
    never hit the list endpoint."""
    client = _stub_openai()
    good = client.batches.create.return_value
    client.batches.create.side_effect = [_conn_error(), good]
    handle = submit_batch([_job()], client=client)
    assert handle.batch_id == "batch-xyz789"
    assert client.batches.create.call_count == 2
    client.batches.list.assert_not_called()


def test_create_reconcile_ambiguous_duplicates_raise(fast_retry):
    client = _stub_openai()
    client.batches.create.side_effect = _conn_error()
    client.batches.list.return_value = _page(
        [
            _batch_obj("b-dup-1", metadata=_CHUNK_MD),
            _batch_obj("b-dup-2", metadata=_CHUNK_MD),
        ]
    )
    with pytest.raises(RuntimeError, match="cancel the duplicates"):
        submit_batch([_job()], metadata=_CHUNK_MD, client=client)


# ---------------------------------------------------------------------------
# Live smoke test — gated on OPENAI_API_KEY presence.
# ---------------------------------------------------------------------------


@pytest.mark.network
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="live-smoke test requires OPENAI_API_KEY",
)
def test_live_smoke_batch_submit_and_poll():
    """Submit a single trivial gpt-5-nano job and confirm round-trip.

    Marked `network` so it is excluded from default `pytest -q` runs. Costs a
    few cents at most. Will also incur 24h Batch API turnaround if waited out;
    this test only checks that submit + first poll succeed.
    """
    job = BatchJob(
        custom_id="smoke-1",
        messages=[
            {"role": "system", "content": "Reply with the word OK only."},
            {"role": "user", "content": "ping"},
        ],
    )
    handle = submit_batch([job], model=batch_client.DEFAULT_MODEL)
    assert handle.batch_id.startswith("batch_")
    status = poll_batch(handle.batch_id)
    assert status.status in {
        "validating",
        "in_progress",
        "finalizing",
        "completed",
    }
