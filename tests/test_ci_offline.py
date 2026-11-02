"""The CI runner refuses real network I/O even before test collection."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / ".github/scripts/offline.py"


@pytest.mark.parametrize("operation", [
    "socket.getaddrinfo('example.invalid', 443)",
    "socket.socket().connect(('127.0.0.1', 9))",
    "socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', 9))",
])
def test_network_attempt_fails_before_io(tmp_path, operation):
    script = tmp_path / "probe.py"
    script.write_text("import socket\n" + operation, encoding="utf-8")
    result = subprocess.run([sys.executable, str(RUNNER), str(script)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "offline check blocked socket." in result.stderr
    assert "NetworkForbidden" in result.stderr


def test_module_import_is_guarded(tmp_path):
    (tmp_path / "probe_module.py").write_text(
        "import socket\nsocket.getaddrinfo('example.invalid', 443)", encoding="utf-8")
    result = subprocess.run([sys.executable, str(RUNNER), "-m", "probe_module"],
                            cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "offline check blocked socket.getaddrinfo" in result.stderr


def test_offline_module_keeps_arguments_and_file_io(tmp_path):
    (tmp_path / "probe_module.py").write_text(
        "import json,sys\nprint(json.dumps(sys.argv[1:]))", encoding="utf-8")
    result = subprocess.run([sys.executable, str(RUNNER), "-m", "probe_module", "a b", "c"],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == ["a b", "c"]


def test_ordinary_workflows_have_no_live_job_or_credentials():
    paths = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    assert len(paths) == 1  # New/reusable workflows require a fresh trigger audit.
    text = paths[0].read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on", workflow.get(True))  # PyYAML YAML1.1 `on`.
    assert set(triggers) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"test", "codebook", "coverage", "wheel-install"}
    assert "secrets." not in text
    assert "search_google" not in text
    assert "continue-on-error" not in text
    for job in workflow["jobs"].values():
        assert "uses" not in job  # No unaudited reusable workflow.
        for step in job["steps"]:
            if "uses" in step:
                assert step["uses"] in {"actions/checkout@v4", "actions/setup-python@v5"}
            command = step.get("run", "")
            if any(token in command for token in ("-m pytest", "-m ruff", "-m g3o.codebook", "-m build", "check_wheel.py")):
                assert "unshare --net" in command
                assert "offline.py" in command
    assert '--cov-fail-under=80' in text
    assert '"not network"' in text
