"""Leg 5 — what the public API can see, checked against an expectation.

The inversion is the design: a completed run is expected visible, a failed one
expected invisible, and either surprise is a failure. That is what lets the same
call serve the smoke gate ("it appears on the staging view") and the
induced-failure gate ("nothing published") without a second code path — and what
makes "no rows from a broken run are being served" something a test asserts
rather than something someone eyeballs.
"""

from __future__ import annotations

from pathlib import Path

from g3o.run.orchestrate import publish as pub
from g3o.run.orchestrate.status import run_status
from tests._orchestrate import event, make_run, write_final_csvs

API = "https://api.example.org"


def _getter(
    status_by_key: dict[str, int],
    *,
    wave: str = "w001",
    calls: list | None = None,
    mode: str = "full",
    default_wave: str | None = None,
    health_status: int = 200,
    evidence_status: str | None = "documented",
):
    """A stand-in for the network, shaped like the real worker.

    ``/health`` answers ``mode`` and ``default_wave`` and builds no ``meta``;
    ``/aggregates`` is plural; institution detail carries ``evidence_status``.
    Each of those three is a property of ``worker/src/index.js`` this leg now
    depends on, so the double models them rather than the leg's old assumptions.
    """

    def _get(url: str, params: dict) -> tuple[int, object]:
        if calls is not None:
            calls.append((url, params))
        if url.endswith("/health"):
            if health_status != 200:
                return health_status, None
            return 200, {
                "service": "g3o-read-api",
                "status": "ok",
                "mode": mode,
                "default_wave": default_wave if default_wave is not None else wave,
            }
        if url.endswith("/aggregates"):
            return 200, {"meta": {"wave": wave}, "data": {}}
        key = url.rsplit("/", 1)[-1]
        code = status_by_key.get(key, 404)
        if code == 200:
            data: dict[str, object] = {"institution_uid": key}
            if evidence_status is not None:
                data["evidence_status"] = evidence_status
            return 200, {"meta": {"wave": wave}, "data": data}
        return code, {"error": {"code": "not_found"}}

    return _get


def _completed_run(tmp_path: Path, *, uid_column: bool = True) -> tuple[Path, str]:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )
    write_final_csvs(run_dir, uid_column=uid_column)
    return runs_dir, run_dir.name


def _failed_run(tmp_path: Path) -> tuple[Path, str]:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"dry_run": False},
        events=[
            event(1, "run_launched"),
            event(2, "run_failed", error_class="RuntimeError", error_message="scrape died"),
        ],
    )
    write_final_csvs(run_dir, uid_column=True)
    return runs_dir, run_dir.name


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


def test_the_uid_column_is_preferred_when_present(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path, uid_column=True)
    keys, column = pub.read_institution_keys(runs_dir / run_id)

    assert column == pub.UID_COLUMN
    assert keys == ["G3O-I-00000001", "G3O-I-00000002"]


def test_institution_id_alone_is_not_verifiable(tmp_path: Path) -> None:
    """The identifiers are different, and guessing a join would be a false green."""
    runs_dir, run_id = _completed_run(tmp_path, uid_column=False)

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_getter({}))

    assert result.verdict == "not_verifiable"
    assert result.key_column == pub.ID_COLUMN
    assert "will not guess a join" in result.reason


def test_a_run_without_stage7_output_is_not_verifiable(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(runs_dir, events=[event(1, "run_failed", error_class="RuntimeError")])

    result = pub.verify_published(runs_dir, run_dir.name, api_base=API, getter=_getter({}))

    assert result.verdict == "not_verifiable"
    assert "Stage 7 has not run" in result.reason


# ---------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------


def test_a_completed_visible_run_passes(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    getter = _getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200})

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=getter)

    assert result.expect_visible is True
    assert result.verdict == "pass"
    assert result.n_visible == 2
    assert result.waves_seen == ("w001",)


def test_a_completed_run_the_api_cannot_see_fails(tmp_path: Path) -> None:
    """Loaded but not served: no wave window covers it, or the Worker's default differs."""
    runs_dir, run_id = _completed_run(tmp_path)

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_getter({}))

    assert result.verdict == "fail"
    assert "wave window" in result.reason


def test_a_failed_run_passes_by_being_invisible(tmp_path: Path) -> None:
    runs_dir, run_id = _failed_run(tmp_path)

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_getter({}))

    assert result.expect_visible is False
    assert result.verdict == "pass"
    assert result.n_visible == 0


def test_a_failed_run_that_IS_visible_is_a_defect(tmp_path: Path) -> None:
    """The assertion the induced-failure gate rests on."""
    runs_dir, run_id = _failed_run(tmp_path)
    getter = _getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200})

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=getter)

    assert result.verdict == "fail"
    assert "must publish nothing" in result.reason
    assert "data-integrity defect" in result.reason


def test_the_expectation_can_be_stated_explicitly(tmp_path: Path) -> None:
    """The out-of-window check: completed, loaded, and deliberately not yet served."""
    runs_dir, run_id = _completed_run(tmp_path)

    result = pub.verify_published(
        runs_dir, run_id, api_base=API, getter=_getter({}), expect_visible=False
    )

    assert result.verdict == "pass"
    assert "as expected" in result.reason


# ---------------------------------------------------------------------------
# Mechanics
# ---------------------------------------------------------------------------


def test_a_transport_failure_is_unknown_not_absent(tmp_path: Path) -> None:
    """An unreachable API says nothing about visibility, and must not read as "hidden"."""
    runs_dir, run_id = _failed_run(tmp_path)

    def _dead(_url: str, _params: dict):
        raise pub.PublishVerifyError("GET failed: connection refused")

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_dead)

    assert result.verdict == "not_verifiable"
    # Since 2026-08-20 the first thing to fail is the /health probe, and it says
    # something more useful than the per-institution loop did: a dead endpoint
    # means the base URL is wrong or nothing is deployed there, NOT that the run
    # is invisible. Either way the invariant under test holds -- unreachable is
    # never reported as absent.
    assert "did not answer" in result.reason
    assert "not that the run" in result.reason
    assert result.deployment["http_status"] is None


def test_the_wave_is_pinned_on_every_request(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    calls: list = []

    pub.verify_published(
        runs_dir, run_id, api_base=API, wave="w002",
        getter=_getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200}, calls=calls),
    )

    scoped = [(u, p) for u, p in calls if not u.endswith("/health")]
    assert scoped and all(params == {"wave": "w002"} for _url, params in scoped)
    # /health is a deployment probe, not a wave-scoped query, and must not be
    # sent a wave: its job is to say which wave the deployment serves.
    assert [p for u, p in calls if u.endswith("/health")] == [{}]


def test_the_sample_is_deterministic(tmp_path: Path) -> None:
    """A re-run checks the same institutions, so two reports are comparable."""
    runs_dir, run_id = _completed_run(tmp_path)
    args = dict(api_base=API, sample=1, getter=_getter({"G3O-I-00000001": 200}))

    first = pub.verify_published(runs_dir, run_id, **args)
    second = pub.verify_published(runs_dir, run_id, **args)

    assert [c.key for c in first.checks] == [c.key for c in second.checks] == ["G3O-I-00000001"]


def test_sample_zero_checks_every_institution(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(
        runs_dir, run_id, api_base=API, sample=0, getter=_getter({})
    )
    assert result.n_checked == result.n_institutions_in_run == 2


def test_the_leg_only_ever_issues_gets() -> None:
    """Structural, not aspirational: no other verb appears in the module."""
    source = Path(pub.__file__).read_text(encoding="utf-8")
    for verb in ("requests.post", "requests.put", "requests.delete", "requests.patch"):
        assert verb not in source


def test_the_verdict_is_recorded_as_a_leg(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    pub.verify_published(
        runs_dir, run_id, api_base=API,
        getter=_getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200}),
    )
    assert run_status(runs_dir, run_id).legs["publish"]["outcome"] == "pass"


def test_rendering_says_it_publishes_nothing(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_getter({}))
    assert "read-only" in pub.render_publish(result)


# ---------------------------------------------------------------------------
# The deployment pre-flight (G3O #81/#82, 2026-08-20)
#
# `visible = (code == 200)` and nothing else, against a worker that serves the
# frame, is a FALSE GREEN: every sampled uid answers 200 from g3o.institutions
# whether or not the run was ever loaded. These assert the leg now refuses to
# call that a pass.
# ---------------------------------------------------------------------------


def test_a_registry_only_worker_is_refused_before_anything_is_sampled(tmp_path: Path) -> None:
    """The false green that would have closed the item-4 publish leg."""
    runs_dir, run_id = _completed_run(tmp_path)
    calls: list = []
    result = pub.verify_published(
        runs_dir, run_id, api_base=API,
        getter=_getter(
            {"G3O-I-00000001": 200, "G3O-I-00000002": 200},
            calls=calls, mode="registry_only",
        ),
    )
    assert result.verdict == "not_verifiable"
    assert "registry_only" in result.reason
    # Refused BEFORE sampling: nothing but /health was asked for. Sampling a
    # registry worker is what produced "all N visible, as expected" about a
    # database holding zero findings for the run.
    assert [u for u, _p in calls if "/institutions/" in u] == []


def test_a_worker_on_the_wrong_default_wave_is_refused(tmp_path: Path) -> None:
    """DEFAULT_WAVE is a deployment binding; no response body complains about it."""
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(
        runs_dir, run_id, api_base=API, expect_wave="w001",
        getter=_getter({"G3O-I-00000001": 200}, wave="w000", default_wave="w000"),
    )
    assert result.verdict == "not_verifiable"
    assert "w000" in result.reason and "w001" in result.reason
    assert result.deployment["default_wave"] == "w000"


def test_an_explicit_wave_overrides_the_deployment_default(tmp_path: Path) -> None:
    """`--wave` is a per-request override, so a differing default is not a refusal."""
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(
        runs_dir, run_id, api_base=API, wave="w001", expect_wave="w001",
        getter=_getter(
            {"G3O-I-00000001": 200, "G3O-I-00000002": 200},
            wave="w001", default_wave="w000",
        ),
    )
    assert result.verdict == "pass"


def test_a_dead_health_endpoint_is_not_read_as_invisible(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(
        runs_dir, run_id, api_base=API,
        getter=_getter({"G3O-I-00000001": 200}, health_status=503),
    )
    assert result.verdict == "not_verifiable"
    assert "did not answer" in result.reason


def test_every_institution_not_reviewed_is_not_a_pass(tmp_path: Path) -> None:
    """A 200 proves frame membership; the rollup join coalesces to not_reviewed."""
    runs_dir, run_id = _completed_run(tmp_path)
    result = pub.verify_published(
        runs_dir, run_id, api_base=API,
        getter=_getter(
            {"G3O-I-00000001": 200, "G3O-I-00000002": 200},
            evidence_status="not_reviewed",
        ),
    )
    assert result.verdict == "not_verifiable"
    assert "not_reviewed" in result.reason
    assert result.n_visible == result.n_checked   # all visible...
    assert result.n_reviewed == 0                 # ...and none of it means anything


def test_a_partly_reviewed_sample_still_passes(tmp_path: Path) -> None:
    """A thin run is legitimate: 13 of 14 institutions with no findings is a real
    result, so the guard must key on 'none reviewed', never on 'all reviewed'."""
    runs_dir, run_id = _completed_run(tmp_path)

    inner = _getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200})

    def _mixed(url: str, params: dict):
        code, body = inner(url, params)
        if "/institutions/" in url and url.endswith("2") and isinstance(body, dict):
            body["data"]["evidence_status"] = "not_reviewed"
        return code, body

    result = pub.verify_published(runs_dir, run_id, api_base=API, getter=_mixed)
    assert result.verdict == "pass"
    assert result.n_reviewed == 1


def test_the_aggregate_endpoint_is_plural(tmp_path: Path) -> None:
    """`/aggregate` is a 404 the old code recorded as data and never read."""
    runs_dir, run_id = _completed_run(tmp_path)
    calls: list = []
    pub.verify_published(
        runs_dir, run_id, api_base=API,
        getter=_getter({"G3O-I-00000001": 200}, calls=calls),
    )
    urls = [u for u, _p in calls]
    assert f"{API}{pub.AGGREGATES_PATH}" in urls
    assert f"{API}/aggregate" not in urls


def test_check_deployment_reports_what_it_found(tmp_path: Path) -> None:
    got = pub.check_deployment(API, _getter({}, mode="full", default_wave="w001"))
    assert got.http_status == 200
    assert got.mode == "full"
    assert got.default_wave == "w001"
    assert not got.registry_only
    assert pub.check_deployment(API, _getter({}, mode="registry_only")).registry_only
