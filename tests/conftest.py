"""Suite-wide fixtures.

Hermetic API keys (Run API spec §3, 2026-08-11)
----------------------------------------------
Key resolution is per call now (:mod:`g3o.common.credentials`), so a developer's
``.env`` — which importing :mod:`g3o.common.config` loads into ``os.environ`` —
otherwise reaches every test that does not supply a key of its own. Before §3
those tests neutralised the key by monkeypatching a module-level constant; that
patch is a no-op against a per-call read, and the resulting failure mode is
silent rather than loud:

* ``test_search_google_returns_mock_when_key_missing`` would take the *live*
  branch, not the mock branch it is named for;
* a stubbed ``_execute`` that raises ``TypeError`` gets swallowed by the dev-mode
  "search failed -> return []" path and the assertion **passes vacuously** — the
  same class of defect as PR #63.

So every provider key variable (Serper, OpenAI, TypeSafe) is cleared for every
test; TypeSafe joined on 2026-10-02, after an ambient developer key made three
preflight tests pass locally that failed without it. Tests marked ``network`` are
exempt: they are the ones that legitimately want the operator's real key (the
live batch smoke, the CI Serper smoke), and they are excluded from the default
``pytest -m "not network"`` run anyway.

Serper live mode
----------------
``serper_client._live_mode`` is a module global that any ``dry_run=False`` run
switches on. ``test_pipeline_hardening_f2`` has guarded itself against a stale
value since 2026-06-10, but a module-local guard only protects the module that
owns it: a live run in *any* other test file leaks the flag onward, and the
symptom lands somewhere else entirely (``test_search_google_returns_mock_when_key_missing``
fails with ``SerperConfigError``, because live mode refuses the mock path). The
guard belongs here, once, for the whole suite.
"""

from __future__ import annotations

import pytest

from g3o.common import deployment, spend_meter
from g3o.common.credentials import OPENAI_ENV_VAR, SERPER_ENV_VAR, TYPESAFE_ENV_VAR
from g3o.discovery import serper_client


@pytest.fixture(autouse=True)
def _no_ambient_api_keys(request: pytest.FixtureRequest, monkeypatch) -> None:
    """Clear provider keys from the environment unless the test wants network."""
    if "network" in request.keywords:
        return
    for var in (SERPER_ENV_VAR, OPENAI_ENV_VAR, TYPESAFE_ENV_VAR):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _reset_serper_live_mode(monkeypatch) -> None:
    """Start every test with live mode off, and undo whatever the test sets."""
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)


@pytest.fixture(autouse=True)
def _no_spend_meter_leak():
    """The spend meter is process-wide; a run that dies mid-test must not leave
    its sink installed for the next test."""
    yield
    spend_meter.uninstall()


@pytest.fixture(autouse=True)
def _no_remote_deployment_check(request: pytest.FixtureRequest, monkeypatch) -> None:
    """``g3o presweep --preflight`` and ``g3o doctor`` run ``git ls-remote``;
    keep the suite off the network unless a test is marked ``network``."""
    if "network" in request.keywords:
        return
    real = deployment.deployment_status
    monkeypatch.setattr(
        deployment, "deployment_status",
        lambda *, check_remote=True: real(check_remote=False),
    )
