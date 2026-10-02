"""What code is deployed here, and which paid services it will actually use.

Added 2026-10-02 after the production host ran a checkout two weeks and nine
merges behind ``main`` without anyone noticing: the Bright Data Web Unlocker
had been merged, documented and switched on by default, and the host had
neither the code nor the token, so every blocked page silently fell back to the
baseline scraper. Two silences stacked, and nothing printed either one.

This module turns both into output:

* :func:`deployment_status` — the commit this package runs from, whether the
  tree is dirty, and how it compares with ``origin/main`` (read with
  ``git ls-remote``; nothing is fetched or changed). Also echoes the deploy
  record written by ``scripts/deploy.sh`` (``~/DEPLOYED.json``), if any.
* :func:`services_status` — for each paid API, whether this run would call it
  and whether its credential is present, so "the unlocker is off" is a line in
  the preflight and in ``g3o doctor`` rather than an absence in the results.

Both are read-only and never raise; an unanswerable question is reported as
``None`` with a note. See ``docs/deployment.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from g3o.common import config
from g3o.common.credentials import ResolvedCredentials, resolve

#: The repository root this package was imported from (``<root>/g3o/common``).
REPO_DIR = Path(__file__).resolve().parents[2]
#: Written by ``scripts/deploy.sh`` on every deploy.
DEPLOY_RECORD = Path.home() / "DEPLOYED.json"


def _git(*args: str, timeout: float = 10.0) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_DIR), *args],
            capture_output=True, text=True, timeout=timeout, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def deployment_status(*, check_remote: bool = True) -> dict[str, Any]:
    """The deployed commit and its distance from ``origin/main``.

    ``stale`` is True when ``origin/main`` is not contained in the deployed
    commit, False when it is, and None when that could not be determined (not
    a git checkout, or the remote unreachable). ``behind`` counts the missing
    commits only when they are already present locally; otherwise it is None
    and ``stale`` still answers.
    """
    status: dict[str, Any] = {
        "repo_dir": str(REPO_DIR),
        "commit": None,
        "dirty": None,
        "origin_main": None,
        "behind": None,
        "stale": None,
        "deploy_record": None,
        "note": None,
    }
    if DEPLOY_RECORD.is_file():
        try:
            status["deploy_record"] = json.loads(DEPLOY_RECORD.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status["deploy_record"] = {"unreadable": str(DEPLOY_RECORD)}
    head = _git("rev-parse", "HEAD")
    if head is None:
        status["note"] = "not a git checkout (installed package); staleness unknown"
        return status
    status["commit"] = head
    porcelain = _git("status", "--porcelain", "--untracked-files=no")
    status["dirty"] = bool(porcelain) if porcelain is not None else None
    if not check_remote:
        status["note"] = "remote check skipped"
        return status
    remote = _git("ls-remote", "origin", "refs/heads/main", timeout=15.0)
    if not remote:
        status["note"] = "origin unreachable; staleness unknown"
        return status
    origin_main = remote.split()[0]
    status["origin_main"] = origin_main
    if origin_main == head:
        status["behind"] = 0
        status["stale"] = False
        return status
    if _git("cat-file", "-e", f"{origin_main}^{{commit}}") is not None:
        contained = _git("merge-base", "--is-ancestor", origin_main, head)
        status["stale"] = contained is None
        count = _git("rev-list", "--count", f"{head}..{origin_main}")
        status["behind"] = int(count) if count and count.isdigit() else None
    else:
        # origin/main has commits this checkout has never fetched.
        status["stale"] = True
        status["note"] = "origin/main has commits not fetched here; run scripts/deploy.sh"
    return status


def services_status(
    config_obj: Any | None = None,
    credentials: ResolvedCredentials | None = None,
) -> dict[str, Any]:
    """For each paid API: will this run call it, and is its credential present.

    ``config_obj`` is a :class:`~g3o.run.presweep.PresweepConfig`; without one the
    defaults are assumed. Credential *values* are never included.
    """
    from g3o.common.pricing import SERPER_PRICING
    from g3o.run.presweep import PresweepConfig

    cfg = (
        config_obj
        if config_obj is not None
        # Placeholder paths: only the model and unlocker defaults are read.
        else PresweepConfig(run_id="doctor", runs_dir=Path("."), master_csv=Path("."))
    )
    creds = credentials if credentials is not None else resolve()
    llm_stages = ("classify_official_site", "classify_triage", "extract", "validate")
    models = {stage: cfg.model_for_stage(stage) for stage in llm_stages}
    jev_stages = [s for s, m in models.items() if m.startswith("jev-")]
    openai_stages = [s for s, m in models.items() if not m.startswith("jev-")]
    unlocker_flags = bool(cfg.scrape_unlocker_on_block or cfg.scrape_unlocker_on_empty)
    unlocker_token = bool(config.UNLOCKER_API_TOKEN)
    return {
        "serper": {
            "used": True,
            "credential_present": creds.has_serper,
            "usd_per_credit": (
                config.SERPER_USD_PER_CREDIT
                if config.SERPER_USD_PER_CREDIT is not None
                else SERPER_PRICING["usd_per_unit"]
            ),
            "rate_source": (
                "G3O_SERPER_USD_PER_CREDIT"
                if config.SERPER_USD_PER_CREDIT is not None
                else "pricing.SERPER_PRICING default"
            ),
        },
        "openai": {
            "used": bool(openai_stages),
            "stages": openai_stages,
            "credential_present": creds.has_openai,
        },
        "typesafe": {
            "used": bool(jev_stages),
            "stages": jev_stages,
            "credential_present": creds.has_typesafe,
        },
        "brightdata_unlocker": {
            "enabled_by_config": unlocker_flags,
            "credential_present": unlocker_token,
            "active": unlocker_flags and unlocker_token,
            "zone": config.UNLOCKER_ZONE if unlocker_token else None,
        },
        "residential_proxy": {
            "active": bool(config.SCRAPE_PROXY_URL),
            "note": "billed per GB outside the spend ceiling" if config.SCRAPE_PROXY_URL else None,
        },
        "database_url_present": bool(os.environ.get("DATABASE_URL")),
    }


def warnings_for(services: dict[str, Any], deployment: dict[str, Any] | None) -> list[str]:
    """Operator-facing one-liners for every silent degradation found."""
    out: list[str] = []
    for name in ("serper", "openai", "typesafe"):
        svc = services[name]
        if svc.get("used", True) and not svc["credential_present"]:
            out.append(f"{name}: used by this run but its API key is not set; a live run will refuse to start")
    unl = services["brightdata_unlocker"]
    if unl["enabled_by_config"] and not unl["credential_present"]:
        out.append(
            "brightdata_unlocker: OFF — G3O_UNLOCKER_API_TOKEN is not set, so blocked "
            "and empty pages fall back to the baseline scraper"
        )
    if services["residential_proxy"]["active"]:
        out.append("residential_proxy: G3O_SCRAPE_PROXY is set; its per-GB spend is not counted in the ceiling")
    if deployment is not None:
        if deployment.get("stale"):
            behind = deployment.get("behind")
            gap = f"{behind} commit(s)" if behind is not None else "unfetched commits"
            out.append(
                f"deployment: this checkout is behind origin/main by {gap}; "
                f"deploy with scripts/deploy.sh (docs/deployment.md)"
            )
        if deployment.get("dirty"):
            out.append("deployment: the checkout has uncommitted changes to tracked files")
    return out


__all__ = ["DEPLOY_RECORD", "REPO_DIR", "deployment_status", "services_status", "warnings_for"]
