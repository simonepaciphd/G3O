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


@pytest.fixture
def direct(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")


@pytest.fixture
def proxied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)


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
