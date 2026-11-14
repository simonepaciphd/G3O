"""``core.source_on_official_domain`` from the official sites this run found (PI ruling 70 b, 2026-11-13).

Ruling 70 b: "``source_on_official_domain`` uses the official site Stage 1 found
for each institution in this run". The run's official-site step is the
``classify_official_site`` stage (numbered Stage 2 in the code; it picks the
site from the Stage 1 search results), which writes one
``2_official_site.json`` per institution folder, ``{"url": ..., ...}``. Its
``url`` is read here, per institution, from the run folder (never the master
column or the overlay CSV), so a resumed run reads the same sites again.

Per institution (:func:`load_run_official_sites`):

- ``2_official_site.json`` with a ``url`` that has a host: the institution's
  official site. This includes a bypass envelope (``"bypassed": true``: the
  site came from the master column): PI ruling 84 a (2026-11-13), the master
  site used for the bypass counts as this run's official site.
- ``2_official_site.json`` with no ``url`` (the step found none), or no file
  while the step is done (``.done/classify_official_site.json``) and the
  attrition ledger records no failure of the step for the institution (the
  step had no candidate to choose from): no official site. The signed rule
  (``items/core.source_on_official_domain/rules/0``) is silent on this case;
  RC-D-025 P13 (PI 2026-11-10) gives ``unknown`` "when the institution is not
  in the official-site list", which is applied here.
- Unresolved, refused for that institution's pages: the step failed for it
  (an attrition record of the step with a known failure reason,
  :data:`FAILURE_REASONS`, and no file); the step is not done and there is no
  file; the ``url`` has no host; or the file cannot be read.

The comparison (:func:`g3o.common.source_fields.official_from_hosts`) is the
signed one, P13 and RC-D-026 9 a: the page's host equal to its own
institution's site host is ``own_official``; equal to another institution's
(in this run) ``other_official``; an institution with no site ``unknown``
unless another's matches; otherwise ``not_official``. PI ruling 85 a
(2026-11-13): "another institution's official site" means the other
institutions of this run only (their sites in this run folder), never the
master or another run.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from g3o.common import attrition
from g3o.common import source_fields as sf
from g3o.common.paths import iter_institution_dirs
from g3o.common.run_state import is_done
from g3o.common.urlnorm import site_host

#: The run's official-site step and its per-institution artifact (``stage_classify``).
OFFICIAL_SITE_STAGE = "classify_official_site"
OFFICIAL_SITE_FALLBACK_STAGE = "classify_official_site_fallback"
OFFICIAL_SITE_FILE = "2_official_site.json"
RULING = "PI ruling 70 b"
#: The attrition reasons the official-site step (and its fallback) records when it fails for an institution:
#: ``stage_classify`` (batch ``parse_failed``, jev ``jev_parse_failed``) and ``jev_stage_runner``
#: (``jev_request_failed``, ``jev_result_processing_failed``). Review L1: any other record of the step is
#: not a failure.
FAILURE_REASONS = frozenset({"parse_failed", "jev_parse_failed", "jev_request_failed",
                             "jev_result_processing_failed"})


@dataclass(frozen=True)
class RunOfficialSites:
    """The official sites this run found, per institution id (the run folder's institution key)."""

    label: str  # names the map in each value's basis
    hosts: Mapping[str, str]  # institution id -> site host of the found official site (bypass included, 84 a)
    no_site: frozenset[str]  # the step found no official site
    unresolved: Mapping[str, str] = field(default_factory=dict)  # institution id -> why it is refused

    def official(self, url: str, institution_id: str) -> sf.FieldValue:
        """``core.source_on_official_domain`` of one page of ``institution_id`` (see the module docstring)."""
        if institution_id in self.unresolved:
            raise sf.MissingUpstreamError(f"{RULING}: official site of {institution_id} "
                                          f"({self.unresolved[institution_id]})", [sf.OFFICIAL])
        if institution_id not in self.hosts and institution_id not in self.no_site:
            raise sf.MissingUpstreamError(f"{RULING}: {OFFICIAL_SITE_FILE} of {institution_id} (not in this run)",
                                          [sf.OFFICIAL])
        return sf.official_from_hosts(url, institution_id, self.hosts, self.label)


def _failed(run_dir: Path) -> set[str]:
    stages = {OFFICIAL_SITE_STAGE, OFFICIAL_SITE_FALLBACK_STAGE}
    return {str(r.get("institution_id")) for r in attrition.read_records(run_dir)
            if r.get("stage") in stages and r.get("reason") in FAILURE_REASONS}


def load_run_official_sites(run_dir: Path) -> RunOfficialSites:
    """Read every institution's ``2_official_site.json`` of the run (resume-safe: from disk, every pass)."""
    run_dir = Path(run_dir)
    done = is_done(run_dir, OFFICIAL_SITE_STAGE)
    failed = _failed(run_dir)
    hosts: dict[str, str] = {}
    no_site: set[str] = set()
    unresolved: dict[str, str] = {}
    for inst_dir in iter_institution_dirs(run_dir):
        inst_id = inst_dir.name
        path = inst_dir / OFFICIAL_SITE_FILE
        if not path.exists():
            if inst_id in failed:
                unresolved[inst_id] = f"the {OFFICIAL_SITE_STAGE} step failed for it (attrition ledger)"
            elif done:
                no_site.add(inst_id)
            else:
                unresolved[inst_id] = f"the {OFFICIAL_SITE_STAGE} step is not done and wrote no {OFFICIAL_SITE_FILE}"
            continue
        try:
            doc = json.loads(path.read_bytes().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            unresolved[inst_id] = f"{OFFICIAL_SITE_FILE} unreadable: {type(exc).__name__}: {exc}"
            continue
        if not isinstance(doc, dict):
            unresolved[inst_id] = f"{OFFICIAL_SITE_FILE} is not a JSON object"
            continue
        url = doc.get("url")
        # PI ruling 84 a: a bypass envelope's master site counts as this run's official site, read like any
        # other url (a bypass names a url; an empty one would be no site, a hostless one is unresolved).
        if url is None or (isinstance(url, str) and not url.strip()):
            no_site.add(inst_id)
            continue
        host = site_host(url) if isinstance(url, str) else None
        if host is None:
            unresolved[inst_id] = f"{OFFICIAL_SITE_FILE} url {url!r} has no host"
            continue
        hosts[inst_id] = host
    return RunOfficialSites(f"{RULING}: {OFFICIAL_SITE_FILE} of run {run_dir.name}", hosts, frozenset(no_site),
                            unresolved)


__all__ = ["FAILURE_REASONS", "OFFICIAL_SITE_FALLBACK_STAGE", "OFFICIAL_SITE_FILE", "OFFICIAL_SITE_STAGE", "RunOfficialSites",
           "load_run_official_sites"]
