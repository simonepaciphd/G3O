"""PI ruling 70 b: ``source_on_official_domain`` from the official sites this run found.

Offline: a run folder with declared ``2_official_site.json`` files, the step's
done marker and the attrition ledger; no provider call.
"""
from __future__ import annotations

import json

import pytest

from g3o.common import attrition
from g3o.common import source_fields as sf
from g3o.common.paths import institution_dir
from g3o.common.run_state import mark_done
from g3o.run.presweep import official_site_v27 as osv
from g3o.run.presweep import stage_classify


def _site(run_dir, inst, doc):
    d = institution_dir(run_dir, inst)
    d.mkdir(parents=True, exist_ok=True)
    if doc is not None:
        (d / osv.OFFICIAL_SITE_FILE).write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def run(tmp_path):
    run_dir = tmp_path / "r1"
    _site(run_dir, "A", {"url": "https://www.council-a.gov.au/about", "confidence": "high"})
    _site(run_dir, "B", {"url": "https://council-b.gov.au/"})
    _site(run_dir, "C", {"url": None, "confidence": "low"})  # the step found no site
    _site(run_dir, "D", None)  # no candidate: no file
    mark_done(run_dir, osv.OFFICIAL_SITE_STAGE, no_batch=True)
    return run_dir


def test_constants_are_the_official_site_step():
    assert osv.OFFICIAL_SITE_STAGE == "classify_official_site"
    assert osv.OFFICIAL_SITE_FALLBACK_STAGE == stage_classify.STAGE_2_FALLBACK


def test_own_other_not_official_and_no_site(run):
    sites = osv.load_run_official_sites(run)
    assert sites.official("https://council-a.gov.au/news/x", "A").value == "own_official"  # www. dropped
    assert sites.official("https://council-b.gov.au/x", "A").value == "other_official"
    assert sites.official("https://news.example.com/x", "A").value == "not_official"
    # No official site (url null, or no file once the step is done): unknown (RC-D-025 P13),
    # unless another institution's site matches (RC-D-026 9 a).
    for inst in ("C", "D"):
        assert sites.official("https://news.example.com/x", inst).value == "unknown"
        assert sites.official("https://council-a.gov.au/x", inst).value == "other_official"
    assert "70 b" in sites.official("https://council-a.gov.au/x", "A").basis
    with pytest.raises(sf.MissingUpstreamError, match="not in this run"):
        sites.official("https://council-a.gov.au/x", "Z")


def test_unresolved_institutions_are_refused(tmp_path):
    run_dir = tmp_path / "r2"
    _site(run_dir, "A", {"url": "https://council-a.gov.au/"})
    _site(run_dir, "FAIL", None)
    _site(run_dir, "NOHOST", {"url": "not a url"})
    _site(run_dir, "PEND", None)
    attrition.record(run_dir, institution_id="FAIL", stage=osv.OFFICIAL_SITE_STAGE, reason="jev_parse_failed")
    sites = osv.load_run_official_sites(run_dir)  # the step is not done
    for inst, why in (("FAIL", "failed"), ("NOHOST", "no host"), ("PEND", "not done")):
        with pytest.raises(sf.MissingUpstreamError, match=why):
            sites.official("https://council-a.gov.au/x", inst)
    assert sites.official("https://council-a.gov.au/x", "A").value == "own_official"


def test_bypassed_master_site_counts_as_this_runs_site(tmp_path):
    """PI ruling 84 a: a bypassed institution's master-column site is this run's official site."""
    run_dir = tmp_path / "r3"
    _site(run_dir, "A", {"url": "https://council-a.gov.au/"})
    _site(run_dir, "BYP", {"bypassed": True, "source": "master_csv", "url": "https://www.bypassed.gov.au/"})
    sites = osv.load_run_official_sites(run_dir)
    assert sites.official("https://bypassed.gov.au/x", "BYP").value == "own_official"
    assert sites.official("https://bypassed.gov.au/x", "A").value == "other_official"
    assert sites.official("https://council-a.gov.au/x", "BYP").value == "other_official"
    assert sites.official("https://news.example.com/x", "BYP").value == "not_official"


def test_other_official_is_this_run_only(tmp_path):
    """PI ruling 85 a: "another institution's official site" is another institution of this run only."""
    other_run = tmp_path / "r_other"
    _site(other_run, "B", {"url": "https://council-b.gov.au/"})
    mark_done(other_run, osv.OFFICIAL_SITE_STAGE, no_batch=True)
    run_dir = tmp_path / "r4"
    _site(run_dir, "A", {"url": "https://council-a.gov.au/"})
    mark_done(run_dir, osv.OFFICIAL_SITE_STAGE, no_batch=True)
    sites = osv.load_run_official_sites(run_dir)
    # B's site is only in another run folder: not other_official here.
    assert sites.official("https://council-b.gov.au/x", "A").value == "not_official"
    with pytest.raises(sf.MissingUpstreamError, match="not in this run"):
        sites.official("https://council-b.gov.au/x", "B")


def test_only_known_failure_reasons_mark_the_step_failed(tmp_path):
    """Review L1: an attrition record of the step with another reason is not a failure."""
    run_dir = tmp_path / "r5"
    _site(run_dir, "N", None)
    _site(run_dir, "F", None)
    attrition.record(run_dir, institution_id="N", stage=osv.OFFICIAL_SITE_STAGE, reason="low_confidence_note")
    attrition.record(run_dir, institution_id="F", stage=osv.OFFICIAL_SITE_FALLBACK_STAGE,
                     reason="jev_request_failed")
    mark_done(run_dir, osv.OFFICIAL_SITE_STAGE, no_batch=True)
    sites = osv.load_run_official_sites(run_dir)
    assert sites.official("https://news.example.com/x", "N").value == "unknown"
    with pytest.raises(sf.MissingUpstreamError, match="failed"):
        sites.official("https://news.example.com/x", "F")
    assert osv.FAILURE_REASONS >= {"parse_failed", "jev_parse_failed", "jev_request_failed",
                                   "jev_result_processing_failed"}


def test_read_from_disk_on_every_load(run):
    """Resume-safe: nothing is cached; a second load reads the files again."""
    assert osv.load_run_official_sites(run).official("https://x.example.org/", "D").value == "unknown"
    _site(run, "D", {"url": "https://x.example.org/"})
    assert osv.load_run_official_sites(run).official("https://x.example.org/", "D").value == "own_official"
