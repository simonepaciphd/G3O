"""Per-call credentials — Run API spec v0.1 §3 (PR A).

Four things are pinned here, in the order the spec states them:

* §3.1 precedence — explicit ``Credentials`` field, then process env, then unset,
  resolved per provider and **per call**;
* §3.2 plumbing — the key a stage actually sends is the one that was threaded
  down, not whatever the environment held when the module was imported, and no
  module in the package reads the deprecated ``config`` constants any more;
* §3.3 secrecy — key material appears in no artifact, no log, no repr, no
  exception; only ``sha256(key)[:8]`` and the operator's label are recordable;
* §3.5 attribution — every batch submit carries the submitting key's fingerprint,
  while reconciliation still matches on chunk identity alone.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.common import batch_client
from g3o.common import config as g3o_config
from g3o.common import credentials as creds
from g3o.common.credentials import (
    Credentials,
    ResolvedCredentials,
    fingerprint,
    resolve,
)
from g3o.common.run_state import _chunk_metadata, _submit_metadata
from g3o.discovery import serper_client
from g3o.run.presweep import PresweepConfig, run_presweep

# Distinctive, obviously-fake keys. Every secrecy assertion below greps for these
# literals, so they must not appear in any expected output for an unrelated
# reason — hence the improbable spelling.
EXPLICIT_OPENAI = "sk-explicit-QQQ-openai-7f3a1e"
EXPLICIT_SERPER = "explicit-ZZZ-serper-9b2c4d"
ENV_OPENAI = "sk-env-QQQ-openai-1a2b3c"
ENV_SERPER = "env-ZZZ-serper-4d5e6f"


# ---------------------------------------------------------------------------
# §3.3 — fingerprints
# ---------------------------------------------------------------------------


def test_fingerprint_is_the_first_8_hex_of_sha256() -> None:
    expected = hashlib.sha256(EXPLICIT_OPENAI.encode("utf-8")).hexdigest()[:8]
    assert fingerprint(EXPLICIT_OPENAI) == expected
    assert len(fingerprint(EXPLICIT_OPENAI)) == creds.FINGERPRINT_CHARS == 8
    assert re.fullmatch(r"[0-9a-f]{8}", fingerprint(EXPLICIT_OPENAI))


def test_fingerprint_of_unset_key_is_none_not_the_hash_of_empty() -> None:
    """A null fingerprint must not be mistakable for a real one in telemetry."""
    assert fingerprint(None) is None
    assert fingerprint("") is None


def test_fingerprints_distinguish_keys() -> None:
    assert fingerprint(EXPLICIT_OPENAI) != fingerprint(ENV_OPENAI)


# ---------------------------------------------------------------------------
# §3.1 — precedence, per provider and per call
# ---------------------------------------------------------------------------


def test_explicit_beats_env() -> None:
    resolved = resolve(
        Credentials(openai_api_key=EXPLICIT_OPENAI, serper_api_key=EXPLICIT_SERPER),
        env={"OPENAI_API_KEY": ENV_OPENAI, "SERPER_API_KEY": ENV_SERPER},
    )
    assert resolved.openai_api_key == EXPLICIT_OPENAI
    assert resolved.serper_api_key == EXPLICIT_SERPER
    assert resolved.openai_source == resolved.serper_source == "explicit"


def test_env_used_when_nothing_explicit() -> None:
    resolved = resolve(
        Credentials(), env={"OPENAI_API_KEY": ENV_OPENAI, "SERPER_API_KEY": ENV_SERPER}
    )
    assert resolved.openai_api_key == ENV_OPENAI
    assert resolved.serper_api_key == ENV_SERPER
    assert resolved.openai_source == resolved.serper_source == "env"


def test_unset_when_neither_source_has_a_key() -> None:
    resolved = resolve(None, env={})
    assert resolved.openai_api_key is None
    assert resolved.serper_api_key is None
    assert resolved.openai_source == resolved.serper_source == "unset"
    assert resolved.has_openai is False
    assert resolved.has_serper is False


def test_providers_resolve_independently() -> None:
    """One provider explicit, the other from env — a mixed-source run is legal."""
    resolved = resolve(
        Credentials(openai_api_key=EXPLICIT_OPENAI), env={"SERPER_API_KEY": ENV_SERPER}
    )
    assert (resolved.openai_api_key, resolved.openai_source) == (
        EXPLICIT_OPENAI, "explicit",
    )
    assert (resolved.serper_api_key, resolved.serper_source) == (ENV_SERPER, "env")


@pytest.mark.parametrize("empty", ["", None])
def test_empty_or_absent_explicit_field_falls_back_to_env(empty) -> None:
    resolved = resolve(
        Credentials(serper_api_key=empty), env={"SERPER_API_KEY": ENV_SERPER}
    )
    assert resolved.serper_api_key == ENV_SERPER
    assert resolved.serper_source == "env"


def test_empty_env_var_counts_as_unset() -> None:
    """``SERPER_API_KEY=`` is how a shell spells "unset"; pre-spec code agreed."""
    resolved = resolve(None, env={"SERPER_API_KEY": ""})
    assert resolved.serper_api_key is None
    assert resolved.serper_source == "unset"


def test_resolution_reads_the_environment_at_call_time(monkeypatch) -> None:
    """The defect §3 removes: resolution must not be frozen at import time."""
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    assert resolve().serper_api_key is None
    monkeypatch.setenv("SERPER_API_KEY", ENV_SERPER)
    assert resolve().serper_api_key == ENV_SERPER


# ---------------------------------------------------------------------------
# §3.3 — the telemetry block, and nothing else
# ---------------------------------------------------------------------------


def test_telemetry_block_carries_source_fingerprint_label_only() -> None:
    """Shape is the published fixture's (tests/fixtures/run_contract/manifest.json).

    Asserted literally rather than against the fixture file: the fixture lives on
    the Day-1 fixtures branch, and PR A must not depend on a file it does not
    ship. PR C, which writes the manifest, is where the two meet.
    """
    resolved = resolve(
        Credentials(openai_api_key=EXPLICIT_OPENAI, label="key-B-grant"),
        env={"SERPER_API_KEY": ENV_SERPER},
    )
    block = resolved.telemetry()
    assert set(block) == {"openai", "serper"}
    for provider in block.values():
        assert set(provider) == {"source", "fingerprint", "label"}
    assert block["openai"] == {
        "source": "explicit",
        "fingerprint": fingerprint(EXPLICIT_OPENAI),
        "label": "key-B-grant",
    }
    assert block["serper"]["source"] == "env"
    assert block["serper"]["fingerprint"] == fingerprint(ENV_SERPER)
    # No key material anywhere in the serialized block.
    serialized = json.dumps(block)
    assert EXPLICIT_OPENAI not in serialized
    assert ENV_SERPER not in serialized


def test_telemetry_label_is_null_for_a_provider_with_no_key() -> None:
    """A tag naming a key is meaningless against a provider that has none."""
    block = resolve(
        Credentials(openai_api_key=EXPLICIT_OPENAI, label="key-B-grant"), env={}
    ).telemetry()
    assert block["openai"]["label"] == "key-B-grant"
    assert block["serper"] == {"source": "unset", "fingerprint": None, "label": None}


@pytest.mark.parametrize("render", [repr, str])
def test_reprs_never_render_key_material(render) -> None:
    """A stock dataclass repr would leak the key into every traceback (§3.3)."""
    supplied = Credentials(
        openai_api_key=EXPLICIT_OPENAI, serper_api_key=EXPLICIT_SERPER, label="key-B"
    )
    resolved = resolve(supplied, env={})
    for text in (render(supplied), render(resolved)):
        assert EXPLICIT_OPENAI not in text
        assert EXPLICIT_SERPER not in text
        assert fingerprint(EXPLICIT_OPENAI) in text
    # And inside a container, which is how objects usually reach a log line.
    assert EXPLICIT_OPENAI not in repr({"credentials": resolved})
    assert EXPLICIT_OPENAI not in repr([supplied])


def test_resolved_credentials_are_frozen() -> None:
    resolved = resolve(Credentials(openai_api_key=EXPLICIT_OPENAI), env={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.openai_api_key = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# §3.2 — the deprecation shim has no consumers left in-repo
# ---------------------------------------------------------------------------


def test_no_module_in_the_package_reads_the_config_key_constants() -> None:
    """The gate that keeps import-time key resolution from creeping back.

    ``config.SERPER_API_KEY`` / ``config.OPENAI_API_KEY`` are resolved once, at
    import. Any consumer of them re-freezes the process's keys and silently
    defeats per-call credentials — and would do so without failing any behavioural
    test, since the env-sourced value is usually the right one. So the rule is
    structural: only ``config.py`` may name them.
    """
    root = Path(__file__).resolve().parent.parent / "g3o"
    names = {"SERPER_API_KEY", "OPENAI_API_KEY"}
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "config.py" and path.parent.name == "common":
            continue  # the shim's own definition site
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # Structural, not textual: naming the env var in a docstring, a comment,
        # or an operator-facing error message is fine and common. Only a real
        # attribute read or import of the constant is a consumer.
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in names:
                offenders.append(f"{path}:{node.lineno}: reads .{node.attr}")
            elif isinstance(node, ast.ImportFrom) and node.module == "g3o.common.config":
                for alias in node.names:
                    if alias.name in names:
                        offenders.append(
                            f"{path}:{node.lineno}: imports {alias.name}"
                        )
    assert offenders == [], (
        "config key constants are a deprecation shim with no in-repo consumers "
        "(spec §3.2); resolve through g3o.common.credentials instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_shim_itself_still_resolves_for_out_of_repo_callers() -> None:
    """Kept for one release (§3.2), so its absence is also a regression."""
    assert hasattr(g3o_config, "SERPER_API_KEY")
    assert hasattr(g3o_config, "OPENAI_API_KEY")


# ---------------------------------------------------------------------------
# §3.2 — the threaded key is the key that reaches the wire
# ---------------------------------------------------------------------------


def _capture_serper_key(monkeypatch) -> dict[str, str]:
    """Stub ``_execute`` and record the key it was handed."""
    seen: dict[str, str] = {}

    def _fake_execute(payload, *, api_key):
        seen["api_key"] = api_key
        return {"organic": [], "searchParameters": {}}

    monkeypatch.setattr(serper_client, "_execute", _fake_execute)
    monkeypatch.setattr(serper_client, "_cached", lambda payload, engine="serper": None)
    monkeypatch.setattr(serper_client, "_save_cache", lambda *a, **k: None)
    return seen


def test_serper_uses_the_threaded_credentials_over_the_environment(monkeypatch) -> None:
    seen = _capture_serper_key(monkeypatch)
    monkeypatch.setenv("SERPER_API_KEY", ENV_SERPER)
    serper_client.search_google(
        "q", credentials=resolve(Credentials(serper_api_key=EXPLICIT_SERPER))
    )
    assert seen["api_key"] == EXPLICIT_SERPER


def test_serper_falls_back_to_the_environment_when_nothing_is_threaded(
    monkeypatch,
) -> None:
    """And reads it at call time — the env var is set *after* import."""
    seen = _capture_serper_key(monkeypatch)
    monkeypatch.setenv("SERPER_API_KEY", ENV_SERPER)
    serper_client.search_google("q")
    assert seen["api_key"] == ENV_SERPER


def test_two_calls_in_one_process_can_use_two_different_keys(monkeypatch) -> None:
    """The concurrency contract's premise (§1.7): no per-process key state."""
    seen: list[str] = []

    def _fake_execute(payload, *, api_key):
        seen.append(api_key)
        return {"organic": [], "searchParameters": {}}

    monkeypatch.setattr(serper_client, "_execute", _fake_execute)
    monkeypatch.setattr(serper_client, "_cached", lambda payload, engine="serper": None)
    monkeypatch.setattr(serper_client, "_save_cache", lambda *a, **k: None)
    for key in (EXPLICIT_SERPER, ENV_SERPER):
        serper_client.search_google(
            "q", force_refresh=True, credentials=resolve(Credentials(serper_api_key=key))
        )
    assert seen == [EXPLICIT_SERPER, ENV_SERPER]


def test_openai_client_is_built_from_the_threaded_credentials(monkeypatch) -> None:
    built: dict[str, str] = {}

    class _FakeOpenAI:
        def __init__(self, *, api_key, max_retries):
            built["api_key"] = api_key
            built["max_retries"] = max_retries

    monkeypatch.setattr(batch_client, "OpenAI", _FakeOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", ENV_OPENAI)
    client = batch_client.client_from_credentials(
        resolve(Credentials(openai_api_key=EXPLICIT_OPENAI))
    )
    assert isinstance(client, _FakeOpenAI)
    assert built == {"api_key": EXPLICIT_OPENAI, "max_retries": 0}


def test_openai_client_is_none_when_no_key_resolves(monkeypatch) -> None:
    """Lazy by design: a stage that never calls out must not die on a missing key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert batch_client.client_from_credentials() is None


def test_default_client_still_raises_the_documented_error(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        batch_client._default_client()


# ---------------------------------------------------------------------------
# §3.5 — key attribution on batch submits
# ---------------------------------------------------------------------------


def test_submit_metadata_adds_the_fingerprint_to_chunk_identity() -> None:
    identity = _chunk_metadata("r20260811T120000Z-aaaa", "extract", 1)
    md = _submit_metadata(identity, fingerprint(EXPLICIT_OPENAI))
    assert md == {**identity, "g3o_key_fingerprint": fingerprint(EXPLICIT_OPENAI)}
    # Identity itself is untouched: it is the reconciliation key.
    assert set(identity) == {"g3o_run_id", "g3o_stage", "g3o_chunk"}


def test_submit_metadata_omits_the_field_when_no_fingerprint_is_known() -> None:
    identity = _chunk_metadata("r20260811T120000Z-aaaa", "extract", 1)
    assert _submit_metadata(identity, None) == identity
    assert _submit_metadata(identity, "") == identity


def test_submit_metadata_carries_no_key_material() -> None:
    md = _submit_metadata(
        _chunk_metadata("r1", "extract", 1), fingerprint(EXPLICIT_OPENAI)
    )
    assert EXPLICIT_OPENAI not in json.dumps(md)


# ---------------------------------------------------------------------------
# §3.3 — the hard one: grep a whole dry-run tree for the key
# ---------------------------------------------------------------------------


def _dry_run_config(tmp_path: Path, master: Path) -> PresweepConfig:
    return PresweepConfig(
        run_id="secrecy-1",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
        dry_run=True,
    )


def _write_master(path: Path) -> Path:
    header = (
        "master_row_id,institution_name,country,branch,government_level,"
        "institution_type,website,official_site_url,official_site_confidence\n"
    )
    rows = "".join(
        f"{i},Ministry {i},Atlantis,executive,national,ministry,,,\n" for i in range(3)
    )
    path.write_text(header + rows, encoding="utf-8")
    return path


def test_no_key_material_anywhere_in_a_dry_run_tree(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    """§3.3, stated as a test: grep the full run tree for the key strings.

    Both sources are loaded — explicit credentials *and* the environment — so the
    grep would catch a leak from either precedence branch. The summary the caller
    receives and everything the run logged are searched too: the spec forbids key
    material in artifacts, logs, receipts, and exceptions alike, and a receipt is
    just as public as a manifest.
    """
    master = _write_master(tmp_path / "master.csv")
    monkeypatch.setenv("OPENAI_API_KEY", ENV_OPENAI)
    monkeypatch.setenv("SERPER_API_KEY", ENV_SERPER)
    caplog.set_level(logging.DEBUG)

    summary = run_presweep(
        _dry_run_config(tmp_path, master),
        credentials=Credentials(
            openai_api_key=EXPLICIT_OPENAI,
            serper_api_key=EXPLICIT_SERPER,
            label="key-B-grant",
        ),
    )

    secrets = (EXPLICIT_OPENAI, EXPLICIT_SERPER, ENV_OPENAI, ENV_SERPER)
    run_dir = Path(summary["run_dir"])
    files = [p for p in run_dir.rglob("*") if p.is_file()]
    assert files, "dry run wrote nothing — the grep would be vacuous"
    for path in files:
        blob = path.read_bytes()
        for secret in secrets:
            assert secret.encode("utf-8") not in blob, f"{secret!r} leaked into {path}"

    serialized_summary = json.dumps(summary, default=str)
    log_text = caplog.text
    for secret in secrets:
        assert secret not in serialized_summary
        assert secret not in log_text


def test_a_leaked_key_would_actually_fail_that_grep(tmp_path: Path) -> None:
    """Guard against the grep passing because it looks in the wrong place.

    Plants the key in the run tree and asserts the same walk finds it. Without
    this, a refactor that moved the run directory would turn the secrecy test
    into a test of an empty directory.
    """
    run_dir = tmp_path / "runs" / "planted"
    (run_dir / "institutions" / "ab").mkdir(parents=True)
    (run_dir / "institutions" / "ab" / "x.json").write_text(
        json.dumps({"leak": EXPLICIT_OPENAI}), encoding="utf-8"
    )
    found = [
        p
        for p in run_dir.rglob("*")
        if p.is_file() and EXPLICIT_OPENAI.encode("utf-8") in p.read_bytes()
    ]
    assert len(found) == 1


def test_live_key_gate_message_names_the_variable_not_the_value(
    tmp_path: Path, monkeypatch
) -> None:
    """A pre-spend failure is where a naive implementation echoes the key."""
    master = _write_master(tmp_path / "master.csv")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    config = PresweepConfig(
        run_id="gate-1",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
        dry_run=False,
        stop_after="discovery_general",
    )
    with pytest.raises(RuntimeError) as exc:
        run_presweep(config, credentials=Credentials(openai_api_key=EXPLICIT_OPENAI))
    assert "SERPER_API_KEY" in str(exc.value)
    assert EXPLICIT_OPENAI not in str(exc.value)


def test_explicit_credentials_satisfy_the_live_key_gate(
    tmp_path: Path, monkeypatch
) -> None:
    """The gate reads resolved credentials, so an explicit key clears it (§3.1).

    Stops after Stage 1a with a stubbed Serper call, so nothing is spent and no
    OpenAI key is required.
    """
    master = _write_master(tmp_path / "master.csv")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    seen: list[str] = []

    def _fake_detailed(query, num_results=10, force_refresh=False, options=None,
                       credentials=None):
        seen.append(credentials.serper_api_key if credentials else "<none>")
        return serper_client.SerperResult(
            results=[], search_parameters={}, from_cache=False, payload={"q": query}
        )

    monkeypatch.setattr(
        "g3o.run.presweep.stage_discovery.search_google_detailed", _fake_detailed
    )
    config = PresweepConfig(
        run_id="gate-2",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
        dry_run=False,
        stop_after="discovery_general",
    )
    summary = run_presweep(
        config, credentials=Credentials(serper_api_key=EXPLICIT_SERPER)
    )
    assert summary["dry_run"] is False
    assert seen and set(seen) == {EXPLICIT_SERPER}, (
        "the resolved key must reach the stage runner, not just the gate"
    )


def test_preflight_key_check_reads_the_passed_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    """``keys_ok`` must answer "could *this* run authenticate" (§3.1).

    With an empty environment and both keys passed explicitly, the readiness gate
    has to clear — otherwise the droplet orchestrator (Item 3), which holds keys
    in memory rather than in the environment, could never pass its own preflight.
    """
    from g3o.run.preflight import run_preflight

    master = _write_master(tmp_path / "master.csv")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = PresweepConfig(
        run_id="preflight-1",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=3,
        seed=22294,
    )

    without = run_preflight(config)
    assert without["keys_ok"] is False

    with_keys = run_preflight(
        config,
        credentials=Credentials(
            openai_api_key=EXPLICIT_OPENAI, serper_api_key=EXPLICIT_SERPER
        ),
    )
    assert with_keys["keys_ok"] is True
    assert EXPLICIT_OPENAI not in json.dumps(with_keys, default=str)


def test_verify_model_spends_on_the_passed_key_not_the_ambient_one(
    tmp_path: Path, monkeypatch
) -> None:
    """The preflight's one spend-bearing branch must use the reported key (§3.2).

    ``--verify-model`` submits a real 1-job batch. Before 2026-08-11 it took
    neither a client nor credentials, so it always used the environment — a
    preflight could report key B as ready and then spend key A. The env here holds
    a *different* key precisely so a regression shows up as the wrong fingerprint
    rather than as no assertion at all.
    """
    from g3o.run import verify_model as vm
    from g3o.run.preflight import run_preflight

    master = _write_master(tmp_path / "master.csv")
    monkeypatch.setenv("OPENAI_API_KEY", ENV_OPENAI)
    monkeypatch.setenv("SERPER_API_KEY", ENV_SERPER)
    built: list[str] = []
    seen_clients: list[object] = []

    class _FakeOpenAI:
        def __init__(self, *, api_key, max_retries):
            built.append(api_key)

    class _Status:
        status = "completed"
        is_terminal = True
        is_completed = True

    def _submit(jobs, *, model, client=None):
        seen_clients.append(client)
        return batch_client.BatchHandle(
            batch_id="batch-verify-1",
            input_file_id="file-1",
            submitted_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
            n_jobs=1,
        )

    monkeypatch.setattr(batch_client, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(vm, "submit_batch", _submit)
    monkeypatch.setattr(vm, "poll_batch", lambda batch_id, *, client=None: _Status())
    monkeypatch.setattr(
        vm, "fetch_results", lambda batch_id, *, client=None, status=None: iter(())
    )

    summary = run_preflight(
        PresweepConfig(
            run_id="verify-1",
            runs_dir=tmp_path / "runs",
            master_csv=master,
            sample_size=3,
            seed=22294,
        ),
        verify_model_live=True,
        credentials=Credentials(
            openai_api_key=EXPLICIT_OPENAI, serper_api_key=EXPLICIT_SERPER
        ),
    )

    assert summary["verify_model"]["batch_id"] == "batch-verify-1"
    assert built == [EXPLICIT_OPENAI], f"verify_model built its client from {built}"
    assert ENV_OPENAI not in built
    assert seen_clients and all(c is not None for c in seen_clients), (
        "the credentialed client never reached submit_batch"
    )


def test_resolved_credentials_type_is_what_stages_receive() -> None:
    """Cheap guard that the threading type never silently becomes ``Credentials``."""
    assert isinstance(resolve(Credentials()), ResolvedCredentials)
