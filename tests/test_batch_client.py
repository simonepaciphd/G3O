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
    poll_batch,
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
    """Disable retry waits so the retry tests run quickly."""
    for fn in (submit_batch, poll_batch):
        monkeypatch.setattr(fn.retry, "wait", wait_none())


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
