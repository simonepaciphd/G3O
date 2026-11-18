"""Bright Data Web Unlocker client (Phase 3, 2026-09-17).

A per-URL escalation for refused/blocked fetches. Deliberately NOT a fourth
always-on egress point: the unlocker fires only when the default fetch path
returns a refusal status (403/406-class) or an empty-after-strip page, and
only when the caller opts in via ``PresweepConfig.scrape_unlocker_on_block``
or ``scrape_unlocker_on_empty``. This preserves the all-three-move-together
invariant for the default identity: robots.txt, page fetches, and the render
still share ``G3O_SCRAPE_PROXY``; the unlocker is a separate instrument.

The Web Unlocker renders JS and solves captchas internally. Billing (PI,
2026-10-02): $8/GB on successful requests — see ``pricing.UNLOCKER_PRICING``.
Measured 2026-10-02 on 12 blocked URLs from run r20260912T001021Z-f4fb: 8 succeeded, mean body 128 KB,
so ~$0.001 per recovered page; a playwright render through the residential
proxy moves a measured 5.44 MB mean.

API contract (measured 2026-09-17):
    POST https://api.brightdata.com/request
    Authorization: Bearer <token>
    Content-Type: application/json
    Body: {"zone": "<zone>", "url": "<target>", "format": "raw"}

Success gate (the measured trap — see measured-recovery-probe-2026-09.md
§Session-1 finding 2): a response is a FAILURE when any of:
    - ``x-brd-error`` or ``x-brd-error-code`` header is present
    - ``x-brd-status-code`` header ≠ 200
    - body is empty (0 bytes)
Policy blocks (``policy_20000``) and dead-target 404s arrive as HTTP 200 from
the unlocker API itself, with 0 bytes and the truth in headers. Never trust
the transport status code alone.

Size cap (PI-approved 2026-11-09): the body is streamed under the same
``fetcher.MAX_RESPONSE_BYTES`` ceiling as a direct fetch, so one oversized
unlocker response cannot buffer unbounded bytes per worker thread. An over-cap
body is abandoned (response closed, no content returned) and is a FAILURE
whose ``error`` starts with :data:`RESPONSE_TOO_LARGE_ERROR`.

Credential hygiene: the Bearer token is a secret and must never appear in any
artifact (ledger, log, manifest, exception message). Every string that reaches
an artifact is passed through :func:`redact` before recording. The token is
read at call time from ``config.UNLOCKER_API_TOKEN``, not frozen at import.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from g3o.common import config, spend_meter

logger = logging.getLogger(__name__)

#: HTTP statuses that signal "the target refused the fetch" and are worth
#: escalating to the unlocker. These are the statuses ``_RETRYABLE_STATUSES``
#: in ``fetcher.py`` already refuses to retry (correctly — a 403 three times
#: is still a 403), and they are exactly the statuses the unlocker is
#: provisioned to defeat (bot detection, geo-block, captcha wall).
#:
#: 403 Forbidden: the target refused; the unlocker's rendered identity may
#:   pass where the observatory's did not.
#: 406 Not Acceptable: content-negotiation refusal; the unlocker sends a
#:   browser-shaped Accept header the target will honour.
#: 401 Unauthorized: auth wall; the unlocker cannot defeat this, but it is
#:   indistinguishable from a 403 at the network layer and the unlocker's
#:   attempt is cheap (~$0.002), so we try and let the inner status tell us.
#: 451 Unavailable For Legal Reasons: geo-legal block; the unlocker may route
#:   through a jurisdiction where the page is reachable.
UNLOCKER_TRIGGER_STATUSES: frozenset[int] = frozenset({403, 406, 401, 451})

#: Prefix of ``UnlockerResult.error`` when the body exceeded
#: ``fetcher.MAX_RESPONSE_BYTES`` and was abandoned (2026-11-10). Unlike every
#: other ``error`` value this one is set by G3O, not by Bright Data's
#: ``x-brd-error`` header; ``error_code`` stays None so the provider's code
#: field never carries a G3O string.
RESPONSE_TOO_LARGE_ERROR = "g3o_response_too_large"

#: Read granularity for the capped stream; same value and rationale as
#: ``fetcher._STREAM_CHUNK_BYTES`` (bounded overshoot past the cap).
_STREAM_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class UnlockerResult:
    """The outcome of one unlocker fetch attempt.

    ``success`` is the load-bearing field: True only when the inner fetch
    succeeded (no ``x-brd-error``, inner status 200, non-empty body). Every
    other field is telemetry — the inner status and error text are what make
    a policy block, a dead page, and a captcha defeat three distinguishable
    rows in the attrition ledger rather than one.

    ``content`` is the raw body, undecoded — the caller's parser does the
    encoding detection, same as the deterministic path. Empty on failure.
    ``inner_status`` is the target's HTTP status as reported by the unlocker
    (``x-brd-status-code``), or None when the unlocker never reached the
    target. ``error`` is the ``x-brd-error`` text, or None. ``elapsed_ms``
    is the wall-clock time the unlocker API took.
    """

    success: bool
    content: bytes
    inner_status: int | None
    error: str | None
    error_code: str | None
    elapsed_ms: int
    #: Response-body bytes Bright Data is taken to bill for this attempt
    #: (2026-10-02). Wider than ``success``: any delivered body without an
    #: ``x-brd-error`` counts, including an inner non-200 whose body the gate
    #: discards, because Bright Data's notion of a successful request is a
    #: delivered response, not our stricter gate. The conservative reading for a
    #: spend ceiling. Zero for errors, empty bodies and transport failures.
    #: For a body abandoned past the size cap (RC-D-025 B4 b, PI 2026-11-10)
    #: it is the advertised ``Content-Length`` when that header is present and
    #: parseable, otherwise the bytes actually read before abandoning (at most
    #: cap + one chunk).
    billable_bytes: int = 0


def enabled() -> bool:
    """Whether the unlocker is configured (token present and non-empty)."""
    return bool(config.UNLOCKER_API_TOKEN)


def redact(text: str) -> str:
    """Replace the Bearer token — if present — with a marker.

    Same floor as the proxy-password redactor: below 8 characters a "token"
    is a substring of ordinary English and blanking it damages the log more
    than it protects. The token is read at call time so a rotation takes
    effect without restart.
    """
    token = config.UNLOCKER_API_TOKEN
    if not token or not text or len(token) < 8:
        return text
    return text.replace(token, "<unlocker-token redacted>")


def _advertised_length(headers) -> int | None:
    """Parsed non-negative ``Content-Length``, or None when absent/unparseable."""
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return None
    return value if value >= 0 else None


def _read_capped(resp: requests.Response) -> tuple[bytes, int, str | None]:
    """Stream the body under ``fetcher.MAX_RESPONSE_BYTES``.

    Returns ``(body, bytes_read, too_large)``. ``too_large`` is None when the
    body fit, else a human-readable reason; the body is then ``b""`` and the
    rest of the stream is left unread (the caller closes the response). Mirrors
    ``fetcher._read_capped``: the advertised ``Content-Length`` is only an
    early exit, the streamed count is the real enforcement, and a body of
    exactly the cap is within it.
    """
    # Imported here, not at module top: fetcher imports this module.
    from g3o.scrape.fetcher import MAX_RESPONSE_BYTES

    advertised = resp.headers.get("content-length")
    if advertised is not None:
        try:
            if int(advertised) > MAX_RESPONSE_BYTES:
                return b"", 0, (
                    f"{RESPONSE_TOO_LARGE_ERROR}: advertised Content-Length "
                    f"{int(advertised):,} bytes is above the "
                    f"{MAX_RESPONSE_BYTES:,}-byte cap; not read"
                )
        except ValueError:
            pass  # unparseable header: fall through to the streaming check
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=_STREAM_CHUNK_BYTES):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            return b"", total, (
                f"{RESPONSE_TOO_LARGE_ERROR}: body exceeded the "
                f"{MAX_RESPONSE_BYTES:,}-byte cap; abandoned after "
                f"{total:,} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks), total, None


def _parse_response(
    resp: requests.Response,
    elapsed_ms: int,
    *,
    body: bytes,
    bytes_read: int | None = None,
    too_large: str | None = None,
) -> UnlockerResult:
    """Apply the success gate to a raw unlocker API response.

    The gate is the measured trap: a policy block arrives as HTTP 200 from
    the unlocker API with 0 bytes and ``x-brd-error: policy_20000`` in the
    headers. A dead target arrives as HTTP 200 with 0 bytes and
    ``x-brd-status-code: 404``. Only when all three conditions hold is the
    fetch a success:
        1. No ``x-brd-error`` / ``x-brd-error-code`` header
        2. ``x-brd-status-code`` == 200 (or absent, treated as success)
        3. Body is non-empty

    ``body`` is the already-read (capped) body. ``too_large`` set means it was
    abandoned past the size cap: a failure, checked after the header errors
    (which keep their own fields) and before the inner status. Its billable
    bytes follow the same rule as any delivered body, counted on
    ``bytes_read`` (defaults to ``len(body)``).
    """
    headers = resp.headers
    error = headers.get("x-brd-error")
    error_code = headers.get("x-brd-error-code")
    inner_status_str = headers.get("x-brd-status-code")
    inner_status: int | None = None
    if inner_status_str:
        try:
            inner_status = int(inner_status_str)
        except (ValueError, TypeError):
            pass
    n_read = len(body) if bytes_read is None else bytes_read
    billable = (
        n_read
        if resp.status_code == 200 and not (error or error_code) and n_read
        else 0
    )
    # The success gate: all three must hold.
    if error or error_code:
        return UnlockerResult(
            success=False, content=b"", inner_status=inner_status,
            error=error, error_code=error_code, elapsed_ms=elapsed_ms,
        )
    if too_large is not None:
        # RC-D-025 B4 b (PI 2026-11-10): an abandoned body is billed at the
        # advertised Content-Length when the header is present and parseable,
        # else at the bytes actually read. Same transport-200 / no-brd-error
        # condition as any delivered body.
        advertised = _advertised_length(headers)
        if advertised is not None and resp.status_code == 200:
            billable = advertised
        return UnlockerResult(
            success=False, content=b"", inner_status=inner_status,
            error=too_large, error_code=None, elapsed_ms=elapsed_ms,
            billable_bytes=billable,
        )
    if inner_status is not None and inner_status != 200:
        return UnlockerResult(
            success=False, content=b"", inner_status=inner_status,
            error=None, error_code=None, elapsed_ms=elapsed_ms,
            billable_bytes=billable,
        )
    if not body or not body.strip():
        return UnlockerResult(
            success=False, content=b"", inner_status=inner_status,
            error=error, error_code=error_code, elapsed_ms=elapsed_ms,
        )
    return UnlockerResult(
        success=True, content=body, inner_status=inner_status,
        error=None, error_code=None, elapsed_ms=elapsed_ms,
        billable_bytes=billable,
    )


def fetch(url: str, *, timeout: int | None = None) -> UnlockerResult:
    """Fetch one URL through the Web Unlocker and apply the success gate.

    Returns an :class:`UnlockerResult` regardless of outcome — the caller
    decides what to do with a failure. Raises only on transport errors
    (network failure, DNS, TLS) that the unlocker API itself never reached;
    a policy block or a dead target is a successful API call with a failure
    inside, and lands in the result's ``error`` / ``inner_status`` fields.

    ``timeout`` defaults to ``config.REQUEST_TIMEOUT * 3`` (the unlocker
    renders JS and solves captchas, so it is slower than a direct fetch;
    3× the page timeout is the measured ceiling from the recovery probe).
    """
    token = config.UNLOCKER_API_TOKEN
    if not token:
        raise RuntimeError(
            "Web Unlocker called but G3O_UNLOCKER_API_TOKEN is not set"
        )
    timeout_s = timeout if timeout is not None else config.REQUEST_TIMEOUT * 3
    started = time.monotonic()
    try:
        resp = requests.post(
            config.UNLOCKER_API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            json={
                "zone": config.UNLOCKER_ZONE,
                "url": url,
                "format": "raw",
            },
            timeout=timeout_s,
            # Streamed so the body is read under the size cap; the response
            # is closed below whether or not it was read in full.
            stream=True,
        )
    except requests.RequestException as exc:
        # Transport failure: the unlocker API was never reached. Redact the
        # token from the exception message before it reaches any artifact.
        safe_msg = redact(str(exc))
        raise requests.RequestException(safe_msg) from exc
    try:
        body, bytes_read, too_large = _read_capped(resp)
    except requests.RequestException as exc:
        # A mid-body transport failure: with stream=True it surfaces while
        # reading, not from ``post``. Same redaction and raise as above.
        safe_msg = redact(str(exc))
        raise requests.RequestException(safe_msg) from exc
    finally:
        resp.close()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if too_large is not None:
        logger.warning("Web Unlocker response for %s: %s", url, too_large)
    result = _parse_response(
        resp, elapsed_ms, body=body, bytes_read=bytes_read, too_large=too_large,
    )
    # Metered here, the one choke point every unlocker call passes, so both
    # triggers (block, empty) and any future caller are counted (2026-10-02).
    spend_meter.record(
        spend_meter.UNLOCKER,
        billable_bytes=result.billable_bytes,
        success=result.success,
    )
    return result


def is_refusal_status(status: int | None) -> bool:
    """Whether ``status`` is one the unlocker should be asked to defeat.

    Used by the dispatch wiring in ``fetcher.scrape_url`` to decide whether a
    download failure is worth escalating. None (a connect timeout, DNS
    failure, TLS error) is not a refusal — the unlocker cannot defeat a dead
    host — and returns False.
    """
    return status is not None and status in UNLOCKER_TRIGGER_STATUSES


__all__ = [
    "RESPONSE_TOO_LARGE_ERROR",
    "UNLOCKER_TRIGGER_STATUSES",
    "UnlockerResult",
    "enabled",
    "fetch",
    "is_refusal_status",
    "redact",
]
