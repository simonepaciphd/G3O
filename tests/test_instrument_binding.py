"""Binding checks use real signed builders and no provider client."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from g3o.common.instrument import load_instrument, sha256_text
from g3o.extract import pass2_support, request_v27
from g3o.run.presweep import instrument_binding as binding
from tests.test_pass2_support import base_page, two_activity_page


def settings():
    return binding.RuntimeSettings(
        jev_model="explicit-test-jev", extractor_model="explicit-test-extractor",
        extractor_effort="medium", extractor_max_tokens=1234, reserved_tokens=25,
        reference_year=2026, approval_reference="Offline test of the signed builders; no live approval",
        x35_model="explicit-test-x35",
    )


def test_real_jobs_and_coders_use_same_instrument_settings(tmp_path):
    bound = binding.bind_runtime(tmp_path, settings())
    record = load_instrument(tmp_path / "final" / "instruments", bound.instrument_id)
    payload = record["payload"]
    assert bound.page_config.setup_pointer == bound.activity_config.setup_pointer == bound.instrument_id
    assert bound.page_config.configured_model == bound.activity_config.configured_model == payload["configured_jev_model"]
    assert bound.page_config.reserved_tokens == 25
    assert bound.activity_config.reference_year == 2026
    assert payload["producer_code_revision"].startswith("package-sha256:")
    page = base_page()
    p2 = two_activity_page()
    jobs = (bound.pass1_job(page, request_v27.select_requests(page)),
            bound.pass2_job(p2, pass2_support.select_requests(p2)))
    for job, key in zip(jobs, ("pass1", "pass2"), strict=True):
        assert job.params["model"] == payload["extractor_model_id"] == settings().extractor_model
        assert job.params["max_tokens"] == payload["extractor_configuration"]["max_tokens"] == 1234
        assert job.params["output_config"]["effort"] == "medium"
        assert sha256_text(job.params["system"]) == payload["prompt_hashes"][key]
        assert job.metadata["setup_pointer"] == bound.instrument_id
    assert binding.bind_runtime(tmp_path, settings()).instrument_id == bound.instrument_id
    assert len(list((tmp_path / "final" / "instruments").glob("*.json"))) == 1


@pytest.mark.parametrize("change", [
    {"jev_model": "other"}, {"extractor_model": "other"}, {"extractor_effort": "high"},
    {"extractor_max_tokens": 2345}, {"reserved_tokens": 30}, {"reference_year": 2027},
    {"approval_reference": "Different approval"}, {"x35_model": "other"},
])
def test_resume_refuses_changed_configuration_before_publishing(tmp_path, change):
    binding.bind_runtime(tmp_path, settings())
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}
    with pytest.raises(ValueError, match="resume instrument differs"):
        binding.bind_runtime(tmp_path, replace(settings(), **change))
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.json")} == before


def test_interruption_after_instrument_creation_resumes_without_new_identity(tmp_path, monkeypatch):
    real_write = binding.write_instrument
    created = []

    def interrupted(*args):
        created.append(real_write(*args))
        raise KeyboardInterrupt

    monkeypatch.setattr(binding, "write_instrument", interrupted)
    with pytest.raises(KeyboardInterrupt):
        binding.bind_runtime(tmp_path, settings())
    assert not (tmp_path / "instrument-binding.json").exists()
    monkeypatch.setattr(binding, "write_instrument", real_write)
    resumed = binding.bind_runtime(tmp_path, settings())
    assert resumed.instrument_id == created[0]["instrument_id"]
    assert len(list((tmp_path / "final" / "instruments").glob("*.json"))) == 1


def test_tampered_immutable_instrument_refuses(tmp_path):
    bound = binding.bind_runtime(tmp_path, settings())
    path = tmp_path / "final" / "instruments" / f"{bound.instrument_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["payload"]["configured_jev_model"] = "not-the-executed-model"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="immutable instrument"):
        binding.bind_runtime(tmp_path, settings())


def test_unapproved_installed_matcher_refuses_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(binding, "version", lambda _: "0.0")
    with pytest.raises(ValueError, match="RapidFuzz"):
        binding.bind_runtime(tmp_path, settings())
    assert not list(tmp_path.iterdir())

def test_codebook_mismatch_names_the_signed_r15_release(tmp_path, monkeypatch):
    monkeypatch.setattr(binding, "CODEBOOK_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="signed r15"):
        binding.bind_runtime(tmp_path, settings())
    assert not list(tmp_path.iterdir())


def test_x35_model_is_pinned_in_the_instrument_and_a_different_one_is_refused(tmp_path):
    """RC-D-033 C1 a: the X35 model is in the payload (bound by the setup pointer); a runtime
    X35 model other than the pinned one is refused, and an absent one cannot be bound."""
    from tests.test_stage6_quote import FakeEntail, FakeExtractor

    bound = binding.bind_runtime(tmp_path, settings())
    payload = load_instrument(tmp_path / "final" / "instruments", bound.instrument_id)["payload"]
    assert payload["extractor_configuration"]["x35_model"] == "explicit-test-x35"
    step = bound.stage6_quote_fn(FakeExtractor(), FakeEntail(), x35_model="explicit-test-x35")
    assert step.x35_model == "explicit-test-x35" and step.bound_instrument_id == bound.instrument_id
    with pytest.raises(ValueError, match="pinned in the instrument"):
        bound.stage6_quote_fn(FakeExtractor(), FakeEntail(), x35_model="another-x35")
    for absent in ("", "  "):
        with pytest.raises(ValueError, match="x35_model must be explicitly supplied"):
            replace(settings(), x35_model=absent)
    with pytest.raises(TypeError):
        binding.RuntimeSettings(jev_model="j", extractor_model="e", extractor_effort="low", extractor_max_tokens=1,
                                reserved_tokens=0, reference_year=2026, approval_reference="a")


def test_archive_host_list_version_is_recorded_in_the_instrument(tmp_path):
    """PI ruling A2.1 a (2026-11-11): the archive-host list version is recorded in the setup."""
    from g3o.common import archive_hosts

    bound = binding.bind_runtime(tmp_path, settings())
    payload = load_instrument(tmp_path / "final" / "instruments", bound.instrument_id)["payload"]
    recorded = payload["extractor_configuration"]["archive_host_list"]
    assert recorded == archive_hosts.setup_record()
    assert recorded["version"] == "g3o.archive_hosts.v2" and recorded["strip_www"] is True
    assert recorded["path_prefixes"] == {"archive.org": ["/details/"]} and "archive.fo" in recorded["hosts"]
