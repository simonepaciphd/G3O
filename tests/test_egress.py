"""Stage 4 egress (#90): all three fetch paths move together, secrets do not leak.

The behaviour under test is the one measured on 2026-08-26 — from the run droplet
0 of 120 previously-failed URLs returned a body, from a residential IP 91 of the
same 120 did — so the proxy is the lever that recovers about 12.4% of a run's
institutions. What these tests protect is not the recovery itself (that is the
network's) but the three properties a *correct* use of it needs:

* page fetches, ``robots.txt`` fetches and the headless render all leave from the
  same egress, so politeness is decided by the identity that then acts on it;
* the proxy URL's credentials never reach a manifest or a log;
* a run records which egress it used, and cannot be resumed onto a different one.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from g3o.common import config
from g3o.scrape import egress

PROXY = "http://user:s3cr3t-longpass@gw.residential.example:8080"
#: The same credential in a URL requests cannot parse -- a trailing space,
#: which is what a copy-paste out of a password manager leaves behind.
PROXY_MALFORMED = "http://user:s3cr3t-longpass@gw.residential.example:8080 "


@pytest.fixture
def direct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")


@pytest.fixture
def proxied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)
    # Pinned, not inherited. ``validate`` refuses a proxied run whose user-agent
    # carries no contact, and the ambient value comes from whatever ``.env`` the
    # box has: this machine's sets a contact, the droplet's sets no USER_AGENT
    # at all. Leaving it ambient would make these tests pass here and fail
    # there, which is the worst of both.
    monkeypatch.setattr(
        config, "USER_AGENT", "G3O-Observatory/0.1 (+https://example.org/crawler)"
    )


# ---------------------------------------------------------------------------
# The module's own surface
# ---------------------------------------------------------------------------


def test_direct_is_the_default(direct: None) -> None:
    assert egress.enabled() is False
    assert egress.requests_proxies() is None
    assert egress.playwright_proxy() is None
    assert egress.describe() == {
        "mode": "direct", "endpoint": None, "credentialed": False
    }


def test_requests_proxies_covers_both_schemes(proxied: None) -> None:
    # An https-only mapping would send plain-HTTP fetches out of the wrong
    # egress — half of Stage 4 measured from the blocked identity, silently.
    assert egress.requests_proxies() == {"http": PROXY, "https": PROXY}


def test_playwright_proxy_splits_credentials_out_of_the_server_url(
    proxied: None,
) -> None:
    assert egress.playwright_proxy() == {
        "server": "http://gw.residential.example:8080",
        "username": "user",
        "password": "s3cr3t-longpass",
    }


def test_playwright_proxy_omits_absent_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "http://gw.example:3128")
    assert egress.playwright_proxy() == {"server": "http://gw.example:3128"}


def test_describe_records_the_endpoint_and_never_the_secret(proxied: None) -> None:
    described = egress.describe()
    assert described == {
        "mode": "proxy",
        "endpoint": "gw.residential.example:8080",
        "credentialed": True,
    }
    # The whole point: this dict is written to manifest.json.
    assert "s3cr3t-longpass" not in json.dumps(described)
    assert "user" not in json.dumps(described)


def test_redact_scrubs_the_url_and_the_bare_password(proxied: None) -> None:
    log = f"GET via {PROXY} failed; auth s3cr3t-longpass rejected"
    out = egress.redact(log)
    assert PROXY not in out
    assert "s3cr3t-longpass" not in out
    assert "<proxy redacted>" in out


def test_redact_is_a_passthrough_when_direct(direct: None) -> None:
    assert egress.redact("nothing to hide") == "nothing to hide"


def test_redact_leaves_a_short_password_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same floor as the DSN redactor: below 8 chars a "password" is a substring
    # of ordinary English, and blanking it damages the log more than it protects.
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "http://u:pass@gw.example:1")
    assert egress.redact("please pass the report") == "please pass the report"


# ---------------------------------------------------------------------------
# Path 1 of 3 — page fetches
# ---------------------------------------------------------------------------


def _fresh_session(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A fetcher Session built now, not the one this thread already cached."""
    from g3o.scrape import fetcher

    monkeypatch.setattr(fetcher, "_thread_local", type(fetcher._thread_local)())
    return fetcher._get_session()


def test_page_fetch_session_carries_the_proxy(
    proxied: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _fresh_session(monkeypatch).proxies == {"http": PROXY, "https": PROXY}


def test_page_fetch_session_is_unchanged_when_direct(
    direct: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # requests defaults Session.proxies to {}; a direct run must look exactly
    # like it did before this module existed.
    assert _fresh_session(monkeypatch).proxies == {}


# ---------------------------------------------------------------------------
# Path 2 of 3 — robots.txt
# ---------------------------------------------------------------------------


def test_robots_fetch_uses_the_same_egress_as_the_pages(
    proxied: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from g3o.scrape import politeness

    seen: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = "User-agent: *\nAllow: /\n"

    def fake_get(url: str, **kwargs: Any) -> _Resp:
        seen["url"] = url
        seen["proxies"] = kwargs.get("proxies")
        return _Resp()

    monkeypatch.setattr(politeness.requests, "get", fake_get)
    body = politeness._fetch_robots_txt(
        "https://host.example/robots.txt", user_agent="G3O-Observatory/0.1", timeout=5
    )
    assert body is not None
    assert seen["proxies"] == {"http": PROXY, "https": PROXY}


def test_robots_fetch_passes_no_proxy_when_direct(
    direct: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from g3o.scrape import politeness

    seen: dict[str, Any] = {}

    class _Resp:
        status_code = 200
        text = ""

    def fake_get(url: str, **kwargs: Any) -> _Resp:
        seen["proxies"] = kwargs.get("proxies")
        return _Resp()

    monkeypatch.setattr(politeness.requests, "get", fake_get)
    politeness._fetch_robots_txt(
        "https://host.example/robots.txt", user_agent="ua", timeout=5
    )
    assert seen["proxies"] is None


# ---------------------------------------------------------------------------
# Path 3 of 3 — the headless render
# ---------------------------------------------------------------------------


class _Chromium:
    def __init__(self) -> None:
        self.launch_kwargs: list[dict[str, Any]] = []

    def launch(self, **kwargs: Any) -> Any:
        self.launch_kwargs.append(kwargs)
        return _Browser()


class _Context:
    def close(self) -> None:
        pass


class _Browser:
    def new_context(self) -> Any:
        return _Context()

    def close(self) -> None:
        pass


class _Pw:
    def __init__(self, chromium: _Chromium) -> None:
        self.chromium = chromium

    def stop(self) -> None:
        pass


class _Starter:
    def __init__(self, pw: _Pw) -> None:
        self._pw = pw

    def start(self) -> _Pw:
        return self._pw


def _launch_kwargs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from g3o.scrape import render

    chromium = _Chromium()
    monkeypatch.setattr(
        render, "_import_sync_playwright", lambda: (lambda: _Starter(_Pw(chromium)))
    )
    with render.RenderSession() as session:
        session._context_obj()
    assert len(chromium.launch_kwargs) == 1
    return chromium.launch_kwargs[0]


def test_render_launches_chromium_through_the_proxy(
    proxied: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _launch_kwargs(monkeypatch)
    assert kwargs["proxy"] == {
        "server": "http://gw.residential.example:8080",
        "username": "user",
        "password": "s3cr3t-longpass",
    }


def test_render_launch_is_byte_identical_when_direct(
    direct: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not ``proxy=None``: the key must be absent so a direct launch is the same
    # call it has always been.
    assert _launch_kwargs(monkeypatch) == {"headless": True}


# ---------------------------------------------------------------------------
# Run identity — recorded, and guarded on resume
# ---------------------------------------------------------------------------


_COLUMNS = [
    "institution_uid", "master_row_id", "country", "country_iso3",
    "government_level", "institution_type", "branch", "institution_name",
    "website", "disambiguation",
]


def _config(tmp_path: Any) -> Any:
    import csv

    from g3o.run.presweep import PresweepConfig

    master = tmp_path / "master.csv"
    with master.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        row = {c: "" for c in _COLUMNS}
        row.update({
            "institution_uid": "G3O-I-00000001",
            "master_row_id": "1",
            "branch": "executive",
            "institution_name": "Ministry of Test",
            "country": "Testland",
        })
        writer.writerow(row)
    return PresweepConfig(
        run_id="egress-test",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=1,
        seed=22294,
        dry_run=True,
    )


def test_manifest_records_the_egress_and_not_the_secret(
    proxied: None, tmp_path: Any
) -> None:
    from g3o.run.presweep import plan_run

    plan = plan_run(_config(tmp_path))
    on_disk = json.loads((plan.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["run_egress"] == {
        "mode": "proxy",
        "endpoint": "gw.residential.example:8080",
        "credentialed": True,
    }
    assert "s3cr3t-longpass" not in json.dumps(on_disk)
    # The proxy is an environment parameter, not a PresweepConfig field: putting
    # it in the config snapshot would move config_hash for every run.
    assert "run_egress" not in on_disk["config"]


def test_manifest_records_direct_when_no_proxy_is_set(
    direct: None, tmp_path: Any
) -> None:
    from g3o.run.presweep import plan_run

    plan = plan_run(_config(tmp_path))
    on_disk = json.loads((plan.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["run_egress"]["mode"] == "direct"


def test_resume_guard_trips_when_the_egress_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Non-vacuous: a run started direct cannot be resumed through a proxy.

    Half a run measured from a blocked identity and half from an unblocked one is
    two scrape instruments in one artifact, with no column recording which
    institution got which.
    """
    from g3o.common.run_state import state_dir
    from g3o.run.presweep import plan_run
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)
    with pytest.raises(RuntimeError, match="run_egress"):
        _assert_manifest_matches_on_resume(
            plan.run_dir, build_manifest(cfg, plan.sample)
        )

    # Negative control — same egress resumes clean.
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    _assert_manifest_matches_on_resume(plan.run_dir, build_manifest(cfg, plan.sample))


def test_resume_guard_tolerates_a_manifest_that_predates_the_key(
    proxied: None, tmp_path: Any
) -> None:
    """A manifest written before 2026-08-26 has no ``run_egress``.

    Every such run predates the proxy existing and so ran direct by construction;
    refusing to resume it would be a cost with no safety gain. Same precedent the
    ``genai_terms_roster_hash`` tolerance set.
    """
    from g3o.common.run_state import state_dir
    from g3o.run.presweep import plan_run
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)
    path = plan.run_dir / "manifest.json"
    stripped = json.loads(path.read_text(encoding="utf-8"))
    del stripped["run_egress"]
    path.write_text(json.dumps(stripped), encoding="utf-8")

    _assert_manifest_matches_on_resume(plan.run_dir, build_manifest(cfg, plan.sample))


# ---------------------------------------------------------------------------
# Adversarial credential hygiene (2026-08-27, card 3)
#
# The tests above prove the *happy path*: describe() and redact() do what the
# module docstring says. These prove the surfaces the docstring does not name,
# and each asserts the ABSENCE of the secret rather than the presence of the
# marker -- absence is the property that matters, and a marker can be present
# while a second copy of the secret survives elsewhere in the same string.
#
# The leak they were written against is real and was measured, not assumed. Two
# realistic operator typos in G3O_SCRAPE_PROXY -- a trailing space, and a
# non-numeric port -- make requests raise
#     InvalidURL: Failed to parse: http://user:s3cr3t-longpass@host:port
# with the credentials intact, and Stage 4 wrote that string to _attrition.jsonl
# and _scrape_telemetry.jsonl unredacted, once per URL. The trailing-space case
# is the dangerous one: it survives a copy-paste out of a password manager, the
# proxy then never works, and the run leaks for its whole length.
#
# Three surfaces were tested and found already clean, so they get no test here
# beyond this note: connection-level ProxyErrors (the message names the proxy
# host and port, never the userinfo), urllib3's DEBUG logs, and Playwright's
# launch errors -- the last by construction, since playwright_proxy() splits the
# credential out of the server URL before it is ever passed.
# ---------------------------------------------------------------------------

SECRET = "s3cr3t-longpass"


def _requests_url_parse_error(proxy: str) -> Exception:
    """The real exception, from the real library, not a hand-written stand-in.

    Building this by hand would test the redactor against our own guess at what
    requests says. The bug was that the guess would have been wrong in the
    reassuring direction, so the fixture is the genuine article: a Session with
    a malformed proxy, pointed at a host that does not resolve. Nothing leaves
    the machine -- the URL fails to parse before any socket is opened.
    """
    import requests

    session = requests.Session()
    session.proxies = {"http": proxy, "https": proxy}
    try:
        session.get("http://g3o-egress-test.invalid/x", timeout=1)
    except Exception as exc:  # noqa: BLE001 - the exception *is* the fixture
        return exc
    raise AssertionError("expected the malformed proxy URL to raise")


@pytest.mark.parametrize(
    "label, proxy",
    [
        ("trailing space", f"http://user:{SECRET}@gw.residential.example:8080 "),
        ("non-numeric port", f"http://user:{SECRET}@gw.residential.example:notaport"),
    ],
)
def test_a_malformed_proxy_url_really_does_leak_before_redaction(
    label: str, proxy: str
) -> None:
    """Non-vacuity guard, in the shape ``test_credentials`` established.

    If requests ever stops echoing the URL, every redaction test below would
    pass against a string that never held a secret. This one fails first and
    says so, rather than letting the suite quietly stop testing anything.
    """
    assert SECRET in str(_requests_url_parse_error(proxy)), (
        f"requests no longer echoes the proxy URL for {label!r} -- the redaction "
        "tests below are now vacuous and should be re-grounded, not deleted"
    )


@pytest.mark.parametrize(
    "proxy",
    [
        f"http://user:{SECRET}@gw.residential.example:8080 ",
        f"http://user:{SECRET}@gw.residential.example:notaport",
    ],
)
def test_redact_scrubs_a_real_library_exception(
    proxy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", proxy)
    assert SECRET not in egress.redact(str(_requests_url_parse_error(proxy)))


def test_stage4_writes_no_secret_to_either_ledger(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_attrition.jsonl`` and ``_scrape_telemetry.jsonl`` -- neither is named
    in the module docstring, and both had the gap.

    Drives the real Stage 4 runner with a fetcher that raises the real requests
    exception, then greps the ledger bytes on disk. Asserting on the files
    rather than on the formatting expression means a new call site that forgets
    to redact is caught here rather than in production.
    """
    from g3o.common import attrition, scrape_telemetry
    from g3o.run.presweep import stage_scrape

    leaky = _requests_url_parse_error(PROXY_MALFORMED)
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY_MALFORMED)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise leaky

    monkeypatch.setattr(stage_scrape, "scrape_url", boom)

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    attrition._seen.clear()
    scrape_telemetry._seen.clear()
    sessions = stage_scrape._ThreadLocalRenderSessions()
    sessions.init_thread()

    stage_scrape._scrape_one(
        run_dir,
        {"master_row_id": "1", "institution_name": "Ministry of Test",
         "country": "Testland", "branch": "executive"},
        ["https://host.example/a"],
        stage="4_scrape",
        # None, not a real cache: robots must not be what stops the fetch, or
        # the exception under test never fires.
        robots=None,
        throttle=stage_scrape.HostThrottle(0.0),
        render_on_download_failure=False,
        empty_page_min_chars=1,
        sessions=sessions,
    )

    wrote = False
    for path in (attrition.ledger_path(run_dir), scrape_telemetry.ledger_path(run_dir)):
        if not path.exists():
            continue
        blob = path.read_bytes()
        if blob:
            wrote = True
        assert SECRET.encode() not in blob, f"proxy password leaked into {path.name}"
    assert wrote, "neither ledger was written -- this grep would be vacuous"
    # Non-vacuous in the other direction: the failure really was recorded, so a
    # future change that simply stopped writing a detail would not pass here.
    assert b"scrape_failed" in attrition.ledger_path(run_dir).read_bytes()


def test_the_events_log_never_receives_the_secret(tmp_path: Any) -> None:
    """``events.jsonl`` -- also unnamed in the docstring, and it had the gap.

    ``run_failed`` recorded ``str(exc)`` on the argument that this pipeline's
    own exceptions name variables, not values. A dependency's exception is not
    bound by that rule, and #90 put one on the path.
    """
    from g3o.run import telemetry as telemetry_mod

    leaky = _requests_url_parse_error(PROXY_MALFORMED)
    events = tmp_path / "events.jsonl"

    emitter = telemetry_mod.RunTelemetry(session_id="egress-test")
    emitter.run_id = "egress-test"
    emitter.events_path = events

    original = config.SCRAPE_PROXY_URL
    config.SCRAPE_PROXY_URL = PROXY_MALFORMED
    try:
        emitter.run_failed(leaky, stop_after="scrape")
    finally:
        config.SCRAPE_PROXY_URL = original

    blob = events.read_bytes()
    assert blob, "no event was written -- this grep would be vacuous"
    assert SECRET.encode() not in blob


def test_the_resume_guard_message_names_the_endpoint_not_the_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """``planning.py`` prints *both* egress values when they disagree.

    It prints the ``describe()`` dicts, which is right -- but nothing asserted
    it, so a later change to print the raw values would have been invisible.
    """
    from g3o.common.run_state import state_dir
    from g3o.run.presweep import plan_run
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)
    with pytest.raises(RuntimeError) as caught:
        _assert_manifest_matches_on_resume(
            plan.run_dir, build_manifest(cfg, plan.sample)
        )
    message = str(caught.value)
    assert SECRET not in message
    assert "user:" not in message
    # Non-vacuous: it really did report the mismatch it was asked about.
    assert "gw.residential.example:8080" in message


def test_no_proxy_credential_anywhere_in_a_planned_run_tree(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The §3.3 whole-tree grep, extended to the third secret.

    ``tests/test_credentials.py`` greps a dry-run tree for the OpenAI and Serper
    keys. The proxy URL is the third secret this pipeline handles and was never
    in that net.
    """
    from g3o.run.presweep import plan_run

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)
    monkeypatch.setattr(
        config, "USER_AGENT", "G3O-Observatory/0.1 (+https://example.org/crawler)"
    )
    plan = plan_run(_config(tmp_path))
    files = [p for p in plan.run_dir.rglob("*") if p.is_file()]
    assert files, "the plan wrote nothing -- the grep would be vacuous"
    for path in files:
        blob = path.read_bytes()
        assert SECRET.encode() not in blob, f"proxy password leaked into {path}"
        assert b"user:s3cr3t" not in blob, f"proxy userinfo leaked into {path}"


def test_a_planted_proxy_secret_would_actually_fail_that_grep(tmp_path: Any) -> None:
    """Guard against the walk passing because it looks in the wrong place."""
    run_dir = tmp_path / "runs" / "planted"
    (run_dir / "institutions" / "ab").mkdir(parents=True)
    (run_dir / "institutions" / "ab" / "x.json").write_text(
        json.dumps({"leak": PROXY}), encoding="utf-8"
    )
    found = [
        p for p in run_dir.rglob("*")
        if p.is_file() and SECRET.encode() in p.read_bytes()
    ]
    assert found, "the walk cannot see a planted secret -- the grep above is vacuous"


# ---------------------------------------------------------------------------
# validate() — the guardrail at the top of the run (2026-08-27)
#
# Redaction at the ledger sinks is a net under a fall. These test the fall.
# ---------------------------------------------------------------------------


def test_validate_is_a_no_op_when_direct(direct: None) -> None:
    """The default path must not pay for, or be able to fail on, this check."""
    egress.validate()


def test_validate_accepts_a_well_formed_credentialed_gateway(proxied: None) -> None:
    egress.validate()


@pytest.mark.parametrize(
    "label, url",
    [
        ("trailing space", f"http://user:{SECRET}@gw.example:8080 "),
        ("leading space", f" http://user:{SECRET}@gw.example:8080"),
        ("bad scheme", f"socks5://user:{SECRET}@gw.example:8080"),
        ("no host", f"http://user:{SECRET}@:8080"),
        ("non-numeric port", f"http://user:{SECRET}@gw.example:notaport"),
        ("no port", f"http://user:{SECRET}@gw.example"),
        ("no credentials", "http://gw.example:8080"),
    ],
)
def test_validate_refuses_an_unusable_proxy_and_names_no_secret(
    label: str, url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two assertions, and the second is the one that matters.

    That it raises is the guardrail. That the message carries no credential is
    the property — an error message is the most-copied string in an incident,
    into a terminal, a ticket, a Slack thread. A guardrail that leaks while
    refusing would be worse than no guardrail, because it fires exactly when a
    human is about to paste it somewhere.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", url)
    with pytest.raises(egress.EgressConfigError) as caught:
        egress.validate()
    message = str(caught.value)
    assert SECRET not in message, f"{label}: the refusal leaked the password"
    assert url.strip() not in message, f"{label}: the refusal leaked the URL"


def test_a_run_refuses_to_plan_through_an_unparseable_proxy(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guardrail is wired, not merely available.

    Without this, ``validate`` could be correct and never called — which is the
    state the module was in before 2026-08-27, when the docstring's promise was
    right and the exception path had never been exercised.
    """
    from g3o.run.presweep import plan_run

    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY_MALFORMED)
    with pytest.raises(egress.EgressConfigError):
        plan_run(_config(tmp_path))
    # And nothing was written: the refusal comes before the run directory does,
    # so a bad launch leaves no half-built run to clean up or resume onto.
    assert not (tmp_path / "runs").exists()


def test_a_run_still_plans_normally_with_no_proxy_set(
    direct: None, tmp_path: Any
) -> None:
    """Off by default stays off by default, proven rather than asserted."""
    from g3o.run.presweep import plan_run

    plan = plan_run(_config(tmp_path))
    manifest = json.loads((plan.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_egress"]["mode"] == "direct"


def test_describe_does_not_raise_on_an_unparseable_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``describe`` is the manifest's identity field and must never be the thing
    that raises.

    ``urlsplit`` defers the port parse to attribute access, so a non-numeric
    port raised a bare ``ValueError`` about integer casting from inside
    ``build_manifest`` — which reads as a bug in the manifest writer rather than
    as a typo in an environment variable. ``validate`` is what refuses such a
    URL, and it runs first in ``plan_run``; this covers any other caller.
    """
    monkeypatch.setattr(
        config, "SCRAPE_PROXY_URL", f"http://user:{SECRET}@gw.example:notaport"
    )
    described = egress.describe()
    assert described["mode"] == "proxy"
    # The host survives; the unusable port is dropped rather than recorded, so
    # two runs differing only in a typo cannot compare as different instruments.
    assert described["endpoint"] == "gw.example"
    assert SECRET not in json.dumps(described)


# ---------------------------------------------------------------------------
# The remote-browser endpoint guard (2026-08-31)
#
# Bright Data's console for the zone G3O was actually issued hands out two
# strings, and only one of them was refused by the checks that existed. These
# cover the other one, which is the whole reason the guard was added.
# ---------------------------------------------------------------------------

#: Verbatim shapes from the Bright Data console for zone
#: ``g3o_pipeline_scraper1``, with the real password replaced. Kept as literals
#: rather than assembled from parts: the point of these tests is that *these
#: strings* are refused, and a helper that built them could drift away from what
#: the console actually emits.
BROWSER_API_CDP = (
    f"wss://brd-customer-hl_xxxx-zone-g3o_pipeline_scraper1:{SECRET}"
    "@brd.superproxy.io:9222"
)
BROWSER_API_WEBDRIVER = (
    f"https://brd-customer-hl_xxxx-zone-g3o_pipeline_scraper1:{SECRET}"
    "@brd.superproxy.io:9515"
)


@pytest.mark.parametrize(
    "label, url, port",
    [
        ("CDP / Puppeteer", BROWSER_API_CDP, 9222),
        ("WebDriver / Selenium", BROWSER_API_WEBDRIVER, 9515),
    ],
)
def test_validate_refuses_a_remote_browser_endpoint(
    label: str, url: str, port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Browser API zone is not a forward proxy, and must not read as one.

    The CDP form was already refused by the scheme check; the WebDriver form
    passed *every* check — https is a legal proxy scheme, the host resolves,
    9515 is a number, the userinfo is present — and would then have failed every
    fetch, which is the silent whole-run collapse ``validate`` exists to stop.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", url)
    monkeypatch.setattr(config, "USER_AGENT", UA_WITH_CONTACT)
    with pytest.raises(egress.EgressConfigError) as caught:
        egress.validate()
    message = str(caught.value)
    assert SECRET not in message, f"{label}: the refusal leaked the password"
    assert url not in message, f"{label}: the refusal leaked the URL"


def test_the_webdriver_refusal_names_the_product_not_just_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message has to be actionable, because the fix is a console action.

    An operator who reads "port 9515 is invalid" re-reads the port. An operator
    who reads "that is a WebDriver endpoint, provision a Web Unlocker zone"
    goes and does the thing that actually resolves it. This asserts the second.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", BROWSER_API_WEBDRIVER)
    monkeypatch.setattr(config, "USER_AGENT", UA_WITH_CONTACT)
    with pytest.raises(egress.EgressConfigError) as caught:
        egress.validate()
    message = str(caught.value)
    assert "WebDriver" in message
    assert "Web Unlocker" in message or "Residential" in message


def test_the_remote_browser_guard_precedes_the_credential_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Order matters: a remote-browser endpoint is fully credentialed.

    Were the userinfo check first, an uncredentialed CDP URL would be refused
    for the wrong reason and the operator would go fix the password.
    """
    monkeypatch.setattr(
        config, "SCRAPE_PROXY_URL", "https://brd.superproxy.io:9515"
    )
    monkeypatch.setattr(config, "USER_AGENT", UA_WITH_CONTACT)
    with pytest.raises(egress.EgressConfigError) as caught:
        egress.validate()
    assert "remote-browser" in str(caught.value)
    assert "username:password" not in str(caught.value)


def test_a_real_forward_proxy_port_is_still_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard must not make Bright Data unreachable, only its wrong product.

    33335 is the conventional Web Unlocker / Residential proxy port and is the
    endpoint this whole seam was built for.
    """
    monkeypatch.setattr(
        config,
        "SCRAPE_PROXY_URL",
        f"http://brd-customer-hl_xxxx-zone-unlocker1:{SECRET}"
        "@brd.superproxy.io:33335",
    )
    monkeypatch.setattr(config, "USER_AGENT", UA_WITH_CONTACT)
    egress.validate()
    assert egress.describe()["endpoint"] == "brd.superproxy.io:33335"


# ---------------------------------------------------------------------------
# The user-agent contact guard (2026-08-27)
#
# Not a general UA policy — it fires only when the proxy is on. Going opaque at
# the network layer and at the identity layer at once is a different thing from
# going opaque at one, and it should not be reachable by omission.
# ---------------------------------------------------------------------------

UA_WITH_CONTACT = "G3O-Observatory/0.1 (+https://example.org/crawler)"
UA_BARE = "G3O-Observatory/0.1"


def test_a_direct_run_does_not_require_a_contact_in_the_user_agent(
    direct: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard must not become a general UA policy by accident.

    Every run before 2026-08-27 went out under the bare default; refusing those
    would be a change to the pipeline's behaviour with no proxy in sight.
    """
    monkeypatch.setattr(config, "USER_AGENT", UA_BARE)
    egress.validate()


def test_a_proxied_run_refuses_a_user_agent_with_no_contact(
    proxied: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "USER_AGENT", UA_BARE)
    with pytest.raises(egress.EgressConfigError, match="contact"):
        egress.validate()


@pytest.mark.parametrize(
    "ua",
    [
        "G3O-Observatory/0.1 (+https://example.org/crawler)",
        "G3O-Observatory/0.1 (+http://example.org/crawler)",
        "G3O-Observatory/0.1 (contact@example.org)",
        # The value actually set in this machine's .env, which the droplet's
        # .env does not set at all — the divergence that motivated the guard.
        "G3O-Observatory/0.1 (https://github.com/x/G3O; someone@example.edu)",
    ],
)
def test_a_proxied_run_accepts_a_reachable_user_agent(
    ua: str, proxied: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "USER_AGENT", ua)
    egress.validate()


def test_a_contact_suffix_cannot_change_which_robots_rules_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """The guard would be unacceptable if it moved the politeness goalposts.

    ``urllib.robotparser`` compares only the token before the first ``/``, so a
    parenthesised suffix is invisible to it. Asserted against the real parser
    and a real ``Disallow``, not against our reading of the stdlib.
    """
    from urllib import robotparser

    parser = robotparser.RobotFileParser()
    parser.parse(["User-agent: G3O-Observatory", "Disallow: /private"])
    for ua in (UA_BARE, UA_WITH_CONTACT):
        assert parser.can_fetch(ua, "https://host.example/public") is True
        assert parser.can_fetch(ua, "https://host.example/private") is False
