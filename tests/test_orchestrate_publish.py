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


def _getter(status_by_key: dict[str, int], *, wave: str = "w001", calls: list | None = None):
    """A stand-in for the network. Records the URLs it was asked for."""

    def _get(url: str, params: dict) -> tuple[int, object]:
        if calls is not None:
            calls.append((url, params))
        if url.endswith("/aggregate"):
            return 200, {"meta": {"wave": wave}, "data": {}}
        key = url.rsplit("/", 1)[-1]
        code = status_by_key.get(key, 404)
        if code == 200:
            return 200, {"meta": {"wave": wave}, "data": {"institution_uid": key}}
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
    assert "not reach the API" in result.reason


def test_the_wave_is_pinned_on_every_request(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path)
    calls: list = []

    pub.verify_published(
        runs_dir, run_id, api_base=API, wave="w002",
        getter=_getter({"G3O-I-00000001": 200, "G3O-I-00000002": 200}, calls=calls),
    )

    assert calls and all(params == {"wave": "w002"} for _url, params in calls)


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
