"""``scripts/verify_egress.py`` — the operator's pre-flight check.

Two things are worth testing here and they are not the same thing. That the
script reaches the right verdict is one. That **nothing it can print carries a
credential** is the other, and it is the load-bearing one: this script runs at
the moment something is wrong, and its output gets pasted into a terminal, a
ticket, or a chat thread. A verification tool that leaks while reporting a
failure would be worse than no tool, because it fires exactly when a human is
about to copy it somewhere.

So every test below drives a path — direct, refused, unreachable, same-IP,
live — and greps the captured stdout for the secret, rather than only asserting
the exit code.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from g3o.common import config
from g3o.scrape import egress

SECRET = "s3cr3t-longpass"
PROXY = f"http://user:{SECRET}@gw.residential.example:8080"
PROXY_MALFORMED = f"http://user:{SECRET}@gw.residential.example:8080 "

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_egress.py"


def _load() -> Any:
    """Import the script by path — it lives in ``scripts/``, not the package."""
    spec = importlib.util.spec_from_file_location("verify_egress", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _pinned_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the UA for every test in this file.

    ``egress.validate`` refuses a proxied run whose user-agent carries no
    contact, and the ambient value comes from whatever ``.env`` the box has:
    this machine's sets one, the droplet's sets no ``USER_AGENT`` at all.
    Inheriting it would make these tests pass here and fail there — which is
    precisely the divergence the guard exists to catch, so it must not also be
    the thing that decides whether the suite is green.
    """
    monkeypatch.setattr(
        config, "USER_AGENT", "G3O-Observatory/0.1 (+https://example.org/crawler)"
    )


@pytest.fixture
def script() -> Any:
    return _load()


def test_direct_is_reported_as_normal_not_as_an_error(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Exit 2, and prose that says so.

    An operator who has not set the variable has not made a mistake — direct is
    the pipeline's default. Returning 1 here would train people to ignore a 1.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    assert script.main([]) == 2
    out = capsys.readouterr().out
    assert "not an error" in out


def test_a_malformed_proxy_is_refused_without_echoing_it(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY_MALFORMED)
    assert script.main([]) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert SECRET not in out
    assert PROXY_MALFORMED.strip() not in out


def test_an_unreachable_gateway_fails_and_names_only_the_exception_class(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """The most likely leak, and the reason ``_fetch_ip`` returns a class name.

    A real ``requests`` proxy exception is used as the failure, not a bare
    ``Exception``, so the test exercises what the library actually raises.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)

    import requests

    leaky = requests.exceptions.InvalidURL(f"Failed to parse: {PROXY}")
    assert SECRET in str(leaky), "fixture is vacuous — it holds no secret"

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise leaky

    monkeypatch.setattr(script.requests, "get", boom)
    assert script.main([]) == 1
    out = capsys.readouterr().out
    assert SECRET not in out, "the failure path echoed the credential"
    assert "InvalidURL" in out, "the operator was told nothing useful"


def test_the_same_ip_on_both_arms_is_a_failure(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """The quiet one. Nothing raises, every request 200s, and the proxy is
    simply not in the path — which a bare 'did it work' check would pass."""
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)

    class _Resp:
        text = "203.0.113.7"

        def raise_for_status(self) -> None:
            pass

    monkeypatch.setattr(script.requests, "get", lambda *a, **k: _Resp())
    assert script.main([]) == 1
    out = capsys.readouterr().out
    assert "NOT in the path" in out
    assert SECRET not in out


def test_a_live_proxy_passes_and_still_prints_no_credential(
    script: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)

    class _Resp:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            pass

    def fake_get(url: str, **kwargs: Any) -> _Resp:
        # Distinguished by whether a proxy was passed, which is the same
        # distinction the script itself draws.
        return _Resp("198.51.100.4" if kwargs.get("proxies") else "203.0.113.7")

    monkeypatch.setattr(script.requests, "get", fake_get)
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert SECRET not in out
    assert "user" not in out.replace("credentialed", "")
    # The endpoint is reported — that is the point, and it is what the manifest
    # already records, so it is not a leak.
    assert "gw.residential.example:8080" in out
    # And the honest caveat survives: a different IP is not a residential IP.
    assert "ASN" in out


def test_it_reads_the_proxy_through_the_same_module_stage4_does(
    script: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guard against the script growing its own parsing.

    If it ever read ``os.environ`` directly it could pass on a value the
    pipeline rejects, or refuse one the pipeline accepts, and the check would
    be worse than useless — it would be misleading.
    """
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", PROXY)
    assert script.egress is egress
    assert egress.proxy_url() == PROXY
