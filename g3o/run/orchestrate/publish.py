"""Leg 5 — ask the public API what it can see, and report the answer.

*"it verifies, it never flips anything."* That is the whole brief for this leg,
and it is enforced structurally rather than by intention: the only HTTP verb in
this module is GET, and the only thing it does with a response is count it.
Making a run visible is the wave window the PI cuts and the ``DEFAULT_WAVE`` the
Worker is configured with (Run API spec §5.4, §5.7) — both deliberately outside
this orchestrator.

The check is written as an **expectation**, not as a search for good news. A
completed, ingested run is expected to be visible; a failed, killed, or dry run
is expected to be **invisible**, and finding it visible is a defect worth
failing on. That inversion is what lets one code path serve both the smoke gate
("the run appears on the staging view with no manual refresh") and the
induced-failure gate ("nothing published"), instead of the second being a thing
someone remembers to eyeball.

Two honest limitations, stated in the report rather than papered over:

* **Joining on ``institution_uid``.** The public API addresses institutions by
  ``institution_uid`` (``GET /institutions/{uid}``). Since uid stamping (#71,
  2026-08-16) the Stage-7 CSVs carry that column and this leg joins on it
  directly. The fallback is retained deliberately: a run whose CSVs carry only
  ``institution_id`` — ``INST-{master_row_id:07d}``, which is not the registry
  key and is not stable across a master rebuild — still reports
  ``not_verifiable`` rather than guessing a join, because a fuzzy match would
  produce a green publish-verify for rows the API is not actually serving. Any
  run planned before stamping lands in that branch.
* **A sample, not a census.** The default is a deterministic sample of the run's
  institutions (sorted, first N), so re-running checks the same ones. Visibility
  is a property of the wave view, not of individual rows, so a sample answers the
  question; ``--sample 0`` checks every institution when someone wants the census.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from g3o.run.orchestrate.status import RunStatus, record_leg, run_status, utc_now_iso

logger = logging.getLogger(__name__)

API_BASE_ENV_VAR = "G3O_API_BASE"

#: Stage-7 outputs to look for institution identity in, in preference order.
_IDENTITY_CSV_GLOBS = (
    "g3o_institution_summary_v*.csv",
    "g3o_activities_v*.csv",
)

#: The API's key, and the pipeline's. They are not the same column, and that is
#: the point of :func:`read_institution_keys`.
UID_COLUMN = "institution_uid"
ID_COLUMN = "institution_id"

#: ``/health`` is the one endpoint that builds no ``meta``, so it answers even
#: when everything downstream of it is broken (g3o-api ``worker/src/index.js``:
#: *"the one endpoint whose job is to answer when things are wrong"*). It reports
#: ``mode`` and ``default_wave``, which is what makes :func:`check_deployment`
#: possible at all.
HEALTH_PATH = "/health"

#: **Plural.** The worker routes ``/aggregates``; ``/aggregate`` is a 404. This
#: leg asked for the singular until 2026-08-20 and treated the 404 as data.
AGGREGATES_PATH = "/aggregates"

#: The mode in which the worker refuses to serve any fact at all: every
#: institution reads ``not_reviewed`` with zero findings, by construction rather
#: than by configuration. No ``DEFAULT_WAVE`` gets a real answer out of it.
REGISTRY_ONLY_MODE = "registry_only"

#: ``evidence_status`` for an institution no run has reviewed. An institution
#: served with this value proves frame membership and nothing more.
NOT_REVIEWED = "not_reviewed"

DEFAULT_SAMPLE = 10
DEFAULT_TIMEOUT = 30

Verdict = Literal["pass", "fail", "not_verifiable"]

#: ``(url, params) -> (http_status, parsed_json_or_None)``.
Getter = Callable[[str, dict[str, Any]], "tuple[int, Any]"]


class PublishVerifyError(RuntimeError):
    """The check could not be run. Never raised because a run is invisible."""


def requests_getter(timeout: int = DEFAULT_TIMEOUT) -> Getter:
    """The default getter: one GET, JSON body if there is one.

    A non-200 is data, not an exception — a 404 from ``/institutions/{uid}`` is
    the API saying "no such record in this wave", which is exactly one of the two
    answers this leg is asking for.
    """

    def _get(url: str, params: dict[str, Any]) -> tuple[int, Any]:
        import requests  # noqa: PLC0415 - already a pipeline dependency

        try:
            response = requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            raise PublishVerifyError(f"GET {url} failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body

    return _get


@dataclass(frozen=True)
class InstitutionCheck:
    key: str
    http_status: int | None
    visible: bool
    wave: str | None = None
    evidence_status: str | None = None
    error: str | None = None

    @property
    def reviewed(self) -> bool:
        """Whether the API served a verdict, rather than a frame row.

        ``evidence_status`` is a ``left join`` onto the rollup and coalesces to
        ``not_reviewed``, so this is the difference between *"the institution is
        in the frame"* and *"a run has been loaded for it"*.
        """
        return self.evidence_status is not None and self.evidence_status != NOT_REVIEWED

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "http_status": self.http_status,
            "visible": self.visible,
            "wave": self.wave,
            "evidence_status": self.evidence_status,
            "error": self.error,
        }


@dataclass(frozen=True)
class PublishVerifyResult:
    """What the public API can see of one run, and whether that is what we expect."""

    run_id: str
    api_base: str
    expect_visible: bool
    verdict: Verdict
    reason: str
    checks: tuple[InstitutionCheck, ...] = ()
    key_column: str | None = None
    waves_seen: tuple[str, ...] = ()
    n_institutions_in_run: int = 0
    aggregate: dict[str, Any] = field(default_factory=dict)
    deployment: dict[str, Any] = field(default_factory=dict)
    expect_wave: str | None = None

    @property
    def n_visible(self) -> int:
        return sum(1 for c in self.checks if c.visible)

    @property
    def n_reviewed(self) -> int:
        """Sampled institutions the API served a real verdict for."""
        return sum(1 for c in self.checks if c.reviewed)

    @property
    def n_checked(self) -> int:
        return len(self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "api_base": self.api_base,
            "expect_visible": self.expect_visible,
            "verdict": self.verdict,
            "reason": self.reason,
            "key_column": self.key_column,
            "n_institutions_in_run": self.n_institutions_in_run,
            "n_checked": self.n_checked,
            "n_visible": self.n_visible,
            "waves_seen": list(self.waves_seen),
            "checks": [c.to_dict() for c in self.checks],
            "aggregate": self.aggregate,
            "deployment": self.deployment,
            "expect_wave": self.expect_wave,
            "n_reviewed": self.n_reviewed,
        }


def read_institution_keys(run_dir: Path) -> tuple[list[str], str | None]:
    """The run's institution keys and which column they came from.

    Returns ``(keys, column)``. ``column`` is ``institution_uid`` when the CSVs
    carry it — the only column the public API can be queried by — and
    ``institution_id`` when they do not, which the caller must treat as
    "not verifiable", never as a key to try.
    """
    final = run_dir / "final"
    if not final.is_dir():
        return [], None
    for glob in _IDENTITY_CSV_GLOBS:
        matches = sorted(final.glob(glob))
        if not matches:
            continue
        path = matches[-1]
        try:
            with open(path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames or []
                column = UID_COLUMN if UID_COLUMN in columns else (
                    ID_COLUMN if ID_COLUMN in columns else None
                )
                if column is None:
                    continue
                keys = sorted(
                    {
                        (row.get(column) or "").strip()
                        for row in reader
                        if (row.get(column) or "").strip()
                    }
                )
        except OSError as exc:
            raise PublishVerifyError(f"could not read {path}: {exc}") from exc
        return keys, column
    return [], None


def _wave_of(body: Any) -> str | None:
    """The wave the API says it served (contract §0: every response echoes it)."""
    if isinstance(body, dict):
        meta = body.get("meta")
        if isinstance(meta, dict):
            wave = meta.get("wave")
            return str(wave) if wave is not None else None
    return None


def _evidence_status_of(body: Any) -> str | None:
    """``data.evidence_status`` from an institution detail response, if present."""
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            status = data.get("evidence_status")
            return str(status) if status is not None else None
    return None


@dataclass(frozen=True)
class DeploymentCheck:
    """Which deployment answered, before anything is asked of it.

    ``mode`` and ``default_wave`` are deployment properties, not request
    properties: ``DEFAULT_WAVE`` is a static worker binding set once at deploy
    time and deliberately not derived per request. So "the right database, wrong
    wave" is a state the caller can be in, and nothing in an institution response
    body complains about it.
    """

    http_status: int | None
    mode: str | None = None
    default_wave: str | None = None
    error: str | None = None

    @property
    def registry_only(self) -> bool:
        return self.mode == REGISTRY_ONLY_MODE

    def to_dict(self) -> dict[str, Any]:
        return {
            "http_status": self.http_status,
            "mode": self.mode,
            "default_wave": self.default_wave,
            "error": self.error,
        }


def check_deployment(api_base: str, get: Getter) -> DeploymentCheck:
    """Ask ``/health`` which worker this is, before trusting anything it serves.

    One request. It exists because *"the endpoint answered"* must not be able to
    read as *"the endpoint was the right one"* — the same argument as the submit
    record's ``skipped`` verdict, one hop earlier. A guessed or stale
    ``G3O_API_BASE`` that happens to resolve is worse than an unset one: this leg
    would sample a wave that is not the run's and report ``pass``.
    """
    try:
        code, body = get(f"{api_base.rstrip('/')}{HEALTH_PATH}", {})
    except PublishVerifyError as exc:
        return DeploymentCheck(http_status=None, error=str(exc))
    mode = default_wave = None
    if isinstance(body, dict):
        mode = body.get("mode")
        default_wave = body.get("default_wave")
    return DeploymentCheck(
        http_status=code,
        mode=str(mode) if mode is not None else None,
        default_wave=str(default_wave) if default_wave is not None else None,
    )


def verify_published(
    runs_dir: Path,
    run_id: str,
    *,
    api_base: str,
    wave: str | None = None,
    sample: int = DEFAULT_SAMPLE,
    getter: Getter | None = None,
    status: RunStatus | None = None,
    expect_visible: bool | None = None,
    expect_wave: str | None = None,
) -> PublishVerifyResult:
    """Query the public API for this run's institutions and report what it finds.

    ``expect_visible`` defaults to the run's own publishability
    (:attr:`~g3o.run.orchestrate.status.RunStatus.publishable`), so a failed or
    killed run is checked for **absence** and passes by being absent. Override it
    when the expectation is known independently — for instance verifying that a
    completed run is still invisible because its wave window has not been cut yet,
    which is the out-of-window case the smoke gate checks.
    """
    run_dir = Path(runs_dir) / run_id
    state = status or run_status(Path(runs_dir), run_id)
    expected = state.publishable if expect_visible is None else expect_visible
    base = api_base.rstrip("/")
    get = getter or requests_getter()
    started_at = utc_now_iso()

    # Which deployment answered, before anything is asked of it. A registry-only
    # worker serves every institution as not_reviewed with zero findings, from
    # the frame, so every sampled uid answers 200 and this leg would report
    # "visible, as expected" about a database that has never seen the run. That
    # is a false green, and a false green closes a leg instead of opening an
    # investigation.
    deployment = check_deployment(base, get)
    wanted_wave = expect_wave or wave

    def _refuse(reason: str) -> PublishVerifyResult:
        res = PublishVerifyResult(
            run_id=run_id, api_base=base, expect_visible=expected,
            verdict="not_verifiable", reason=reason,
            n_institutions_in_run=0, deployment=deployment.to_dict(),
            expect_wave=wanted_wave,
        )
        record_leg(run_dir, "publish", outcome=res.verdict, started_at=started_at, **res.to_dict())
        return res

    if deployment.http_status != 200:
        detail = deployment.error or f"HTTP {deployment.http_status}"
        return _refuse(
            f"{base}{HEALTH_PATH} did not answer ({detail}). That endpoint builds "
            f"no meta and answers when the rest is broken, so a failure here means "
            f"the base URL is wrong or nothing is deployed at it — not that the run "
            f"is invisible."
        )
    if deployment.registry_only:
        return _refuse(
            f"{base} is deployed in {REGISTRY_ONLY_MODE!r} mode: it refuses to "
            f"serve any fact, so every institution reads {NOT_REVIEWED!r} with zero "
            f"findings by construction. Every sampled uid would answer 200 from the "
            f"frame and this leg would pass without touching the run. Point "
            f"{API_BASE_ENV_VAR} at a worker with REGISTRY_ONLY dropped."
        )
    if wanted_wave and deployment.default_wave and not wave and deployment.default_wave != wanted_wave:
        return _refuse(
            f"{base} serves wave {deployment.default_wave!r} by default and this "
            f"run belongs to {wanted_wave!r}. DEFAULT_WAVE is a static deployment "
            f"binding, not a request property, so the right database with the wrong "
            f"wave is a state this leg can be in and no response body complains "
            f"about it. Re-pin the worker, or pass --wave to override per request."
        )

    keys, column = read_institution_keys(run_dir)
    if column is None or not keys:
        result = PublishVerifyResult(
            run_id=run_id, api_base=base, expect_visible=expected,
            verdict="not_verifiable",
            reason=(
                f"no institution keys in {run_dir / 'final'} — Stage 7 has not run, "
                f"or its CSVs carry neither {UID_COLUMN} nor {ID_COLUMN}."
            ),
            key_column=column, n_institutions_in_run=len(keys),
            deployment=deployment.to_dict(), expect_wave=wanted_wave,
        )
        record_leg(run_dir, "publish", outcome=result.verdict, started_at=started_at, **result.to_dict())
        return result

    if column != UID_COLUMN:
        result = PublishVerifyResult(
            run_id=run_id, api_base=base, expect_visible=expected,
            verdict="not_verifiable",
            reason=(
                f"the run's Stage-7 CSVs carry {column!r} but the public API is keyed "
                f"by {UID_COLUMN!r}. These are different identifiers — "
                f"{ID_COLUMN} is minted per master build and is not the registry "
                f"key — so this leg will not guess a join. Visibility becomes "
                f"verifiable when the pipeline stamps {UID_COLUMN}."
            ),
            key_column=column, n_institutions_in_run=len(keys),
            deployment=deployment.to_dict(), expect_wave=wanted_wave,
        )
        record_leg(run_dir, "publish", outcome=result.verdict, started_at=started_at, **result.to_dict())
        return result

    checked = keys if sample <= 0 else keys[:sample]
    params: dict[str, Any] = {"wave": wave} if wave else {}
    checks: list[InstitutionCheck] = []
    waves: set[str] = set()
    for key in checked:
        try:
            code, body = get(f"{base}/institutions/{key}", params)
        except PublishVerifyError as exc:
            checks.append(InstitutionCheck(key=key, http_status=None, visible=False, error=str(exc)))
            continue
        served = _wave_of(body)
        if served:
            waves.add(served)
        checks.append(
            InstitutionCheck(
                key=key, http_status=code, visible=code == 200, wave=served,
                evidence_status=_evidence_status_of(body),
            )
        )

    aggregate: dict[str, Any] = {}
    try:
        code, body = get(f"{base}{AGGREGATES_PATH}", params)
        aggregate = {"http_status": code, "wave": _wave_of(body)}
        if _wave_of(body):
            waves.add(str(_wave_of(body)))
    except PublishVerifyError as exc:
        aggregate = {"http_status": None, "error": str(exc)}

    n_visible = sum(1 for c in checks if c.visible)
    n_reviewed = sum(1 for c in checks if c.reviewed)
    transport_errors = [c for c in checks if c.http_status is None]
    if transport_errors:
        verdict: Verdict = "not_verifiable"
        reason = (
            f"{len(transport_errors)} of {len(checks)} request(s) did not reach the "
            f"API ({transport_errors[0].error}). Visibility is unknown, not absent."
        )
    elif expected and wanted_wave and any(
        c.wave is not None and c.wave != wanted_wave for c in checks
    ):
        served_other = sorted({c.wave for c in checks if c.wave and c.wave != wanted_wave})
        verdict = "not_verifiable"
        reason = (
            f"the API served wave {', '.join(served_other)} for a run that belongs "
            f"to {wanted_wave!r}. Those rows are visible, but they are not this "
            f"run's — a wave mismatch reads as success on every count this leg "
            f"kept before 2026-08-20."
        )
    elif expected and n_visible == len(checks) and n_reviewed == 0 and any(
        c.evidence_status is not None for c in checks
    ):
        verdict = "not_verifiable"
        reason = (
            f"all {len(checks)} sampled institution(s) answered 200, and every one "
            f"reads {NOT_REVIEWED!r}. A 200 proves the uid is in the frame — the "
            f"detail query is a left join onto the rollup and coalesces to "
            f"{NOT_REVIEWED!r} — so this is what a run that was never loaded looks "
            f"like, not what a published one looks like. Visibility of the frame is "
            f"not publication of the run."
        )
    elif expected and n_visible == len(checks):
        reviewed_note = (
            f" {n_reviewed} of them carry a loaded verdict."
            if any(c.evidence_status is not None for c in checks)
            else " The API served no evidence_status, so publication is inferred "
                 "from visibility alone."
        )
        verdict = "pass"
        reason = (
            f"all {len(checks)} sampled institution(s) are visible, as expected."
            + reviewed_note
        )
    elif not expected and n_visible == 0:
        verdict = "pass"
        reason = (
            f"none of the {len(checks)} sampled institution(s) is visible, as expected "
            f"for a run in state {state.state!r}."
        )
    elif expected:
        verdict = "fail"
        reason = (
            f"only {n_visible} of {len(checks)} sampled institution(s) are visible. "
            f"The run loaded but the wave view is not serving it — check that a wave "
            f"window covers {state.run_started_at} and that the Worker's DEFAULT_WAVE "
            f"is the one you are querying."
        )
    else:
        verdict = "fail"
        reason = (
            f"{n_visible} of {len(checks)} sampled institution(s) ARE visible for a "
            f"run in state {state.state!r}, which must publish nothing. This is a "
            f"data-integrity defect: rows from an incomplete run are being served."
        )

    result = PublishVerifyResult(
        run_id=run_id,
        api_base=base,
        expect_visible=expected,
        verdict=verdict,
        reason=reason,
        checks=tuple(checks),
        key_column=column,
        waves_seen=tuple(sorted(waves)),
        n_institutions_in_run=len(keys),
        aggregate=aggregate,
        deployment=deployment.to_dict(),
        expect_wave=wanted_wave,
    )
    record_leg(run_dir, "publish", outcome=verdict, started_at=started_at, **result.to_dict())
    return result


def render_publish(result: PublishVerifyResult) -> str:
    lines = [
        f"Publish-verify — run {result.run_id}",
        f"  {result.verdict.upper()}: {result.reason}",
        "",
        f"  API base            : {result.api_base}",
        f"  Deployment          : mode={result.deployment.get('mode') or '?'} "
        f"default_wave={result.deployment.get('default_wave') or '?'}"
        + (f" (expected {result.expect_wave})" if result.expect_wave else ""),
        f"  Expectation         : {'visible' if result.expect_visible else 'NOT visible'}",
        f"  Institutions in run : {result.n_institutions_in_run} (key column: {result.key_column})",
        f"  Sampled / visible   : {result.n_checked} / {result.n_visible}",
    ]
    if result.waves_seen:
        lines.append(f"  Wave(s) served      : {', '.join(result.waves_seen)}")
    if result.aggregate:
        lines.append(f"  /aggregate          : HTTP {result.aggregate.get('http_status')}")
    misses = [c for c in result.checks if not c.visible][:10]
    if misses:
        lines.append("  Not visible:")
        for check in misses:
            lines.append(f"      {check.key}: HTTP {check.http_status}{f' ({check.error})' if check.error else ''}")
    lines.append("  (read-only — this leg issues GET requests and publishes nothing)")
    return "\n".join(lines)


__all__ = [
    "AGGREGATES_PATH",
    "API_BASE_ENV_VAR",
    "DEFAULT_SAMPLE",
    "HEALTH_PATH",
    "ID_COLUMN",
    "NOT_REVIEWED",
    "REGISTRY_ONLY_MODE",
    "UID_COLUMN",
    "DeploymentCheck",
    "Getter",
    "InstitutionCheck",
    "PublishVerifyError",
    "PublishVerifyResult",
    "Verdict",
    "check_deployment",
    "read_institution_keys",
    "render_publish",
    "requests_getter",
    "verify_published",
]
