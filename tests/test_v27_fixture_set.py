"""T-040 self-check on the v2.7 fixture set (tests/fixtures/v27/).

Offline structure test only: it checks coverage (DP-031 / RC-D-014 P3 b), that expected
values are codebook codes, that every expected value cites a rule, that real-page fixtures
carry no page text and a hash-pinned reference, and that judgement calls are registered.
It does not run the pipeline (that is T-041, paid).
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "v27"
CODEBOOK = ROOT / "codebook" / "codebook.yaml"
SIGNED_SHA = "07610cc92c5c49f6fb80d22bfa128a1b4db7f6fb429a62f0ea8789943569c527"
A_IDS = ["A-003", "A-004", "A-010", "A-011", "A-012", "A-020", "A-021", "A-022"]
VERDICTS = [
    "confirms_activity",
    "ambiguous_genai",
    "ambiguous_attribution",
    "other_body",
    "event_only",
    "background_only",
    "confirms_absence",
    "no_genai",
    "not_assessable",
]
MISSING = {"not_asked", "not_documented", "unknown", "_NA_"}


def _fixtures():
    out = []
    for name in ("synthetic.json", "real.json", "transfers.json"):
        p = FIX / name
        if p.exists():
            out += json.loads(p.read_text(encoding="utf-8"))["fixtures"]
    return out


@pytest.fixture(scope="module")
def fixtures():
    return _fixtures()


@pytest.fixture(scope="module")
def items():
    return yaml.safe_load(CODEBOOK.read_text(encoding="utf-8"))["items"]


def test_codebook_is_signed_release():
    assert hashlib.sha256(CODEBOOK.read_bytes()).hexdigest() == SIGNED_SHA


def test_fixture_ids_unique(fixtures):
    ids = [f["fixture_id"] for f in fixtures]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("a_id", A_IDS)
def test_at_least_three_fixtures_per_a_id(fixtures, a_id):
    assert sum(a_id in f["a_ids"] for f in fixtures) >= 3


@pytest.mark.parametrize("verdict", VERDICTS)
def test_every_page_verdict_value_has_a_fixture(fixtures, verdict):
    hits = [
        f
        for f in fixtures
        if "A-011" in f["a_ids"]
        and any(e["item"] == "core.page_verdict" and e["value"] == verdict for e in f["expected"])
    ]
    assert hits, verdict


def test_expected_values_are_codebook_codes(fixtures, items):
    for f in fixtures:
        for e in f["expected"]:
            it = items.get(e["item"])
            if it is None or e.get("value_kind"):
                continue  # mechanics keys (followed_urls, provenance, ...) and counts
            vals = it.get("values")
            if not isinstance(vals, list) or not all(
                isinstance(v, dict) and v.get("code") for v in vals
            ):
                continue  # free-text, list, date and year items
            codes = {v["code"] for v in vals} | MISSING
            assert e["value"] in codes, (f["fixture_id"], e["item"], e["value"])


def test_every_expected_value_cites_a_rule(fixtures):
    for f in fixtures:
        assert f["expected"], f["fixture_id"]
        for e in f["expected"]:
            assert e.get("rule"), (f["fixture_id"], e["item"])


def test_kinds_and_real_fixtures_carry_no_text(fixtures):
    for f in fixtures:
        assert f["kind"] in {"synthetic", "real", "real_transfer"}
        if f["kind"] == "real":
            refs = [f["page_ref"]] if "page_ref" in f else f["page_refs"]
            for ref in refs:
                assert len(ref["text_sha256"]) == 64 and ref["store"]
                assert ref.get("line_1based", 0) >= 1 or len(ref.get("member_sha256", "")) == 64
            assert "text" not in f and "pages" not in f
            for e in f["expected"]:
                assert e.get("labeller") == "agent" and "jev_score" in e


def test_judgement_calls_are_registered(fixtures):
    reg = {r["jc_id"] for r in csv.DictReader((FIX / "judgement-calls.csv").open(encoding="utf-8"))}
    used = {e["judgement_call"] for f in fixtures for e in f["expected"] if e.get("judgement_call")}
    assert used <= reg, used - reg


def test_label_sheet_matches_fixtures(fixtures):
    rows = list(csv.DictReader((FIX / "label-sheet.csv").open(encoding="utf-8")))
    n = sum(len(f["expected"]) for f in fixtures)
    assert len(rows) == n
    assert {r["fixture_id"] for r in rows} == {f["fixture_id"] for f in fixtures}


def test_synthetic_long_pages_exceed_chunk_threshold():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fixture_text", FIX / "fixture_text.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    syn = json.loads((FIX / "synthetic.json").read_text(encoding="utf-8"))["fixtures"]
    long_pages = [p for f in syn for p in f["pages"] if "text_parts" in p]
    assert long_pages
    for p in long_pages:
        assert len(mod.page_text(p)) > 2 * 32000 * mod.CHARS_PER_TOKEN


def test_no_pilot_v1_input():
    for p in FIX.rglob("*"):
        if p.is_file() and p.suffix in {".json", ".csv", ".py"}:
            t = p.read_text(encoding="utf-8")
            assert "pilot_v1" not in t and "g3o_full_database_v1" not in t, p


def test_jev_label_scores_join_and_readings():
    scores = list(csv.DictReader((FIX / "jev-label-scores.csv").open(encoding="utf-8")))
    sheet = list(csv.DictReader((FIX / "label-sheet.csv").open(encoding="utf-8")))
    keys = {s["key"] for s in scores}
    assert len(keys) == len(scores)
    # current real label keys that have a score are filled; superseded keys (relabels) stay in the scores file
    sheet_keys = {r["jev_key"] for r in sheet if r["jev_key"]}
    assert {r["jev_key"] for r in sheet if r["jev_argmax_1_5"]} == keys & sheet_keys
    for r in sheet:
        if r["label_version"] not in ("", "1"):
            assert r["jev_key"].endswith("@v" + r["label_version"])
    for s in scores:
        probs = {int(k): v for k, v in json.loads(s["probabilities_1_5"]).items()}
        top = max(probs, key=lambda k: (probs[k], -k))
        assert int(s["jev_argmax_1_5"]) == top
        assert abs(float(s["jev_expected_1_5"]) - (float(s["level_raw"]) + 1)) < 1e-6


def test_real_pages_resolve_and_quotes_occur():
    """Drive-backed: skipped when G3O_DRIVE_ROOT is unset (CI); hash-checks every real page and quote."""
    import importlib.util
    import os
    import re

    if not os.environ.get("G3O_DRIVE_ROOT"):
        pytest.skip("G3O_DRIVE_ROOT not set: real-page stores are not available")
    spec = importlib.util.spec_from_file_location("fixture_text", FIX / "fixture_text.py")
    ft = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ft)
    drive = ft.drive_root()

    def norm(s):
        return re.sub(r"\s+", " ", s).strip()

    real = json.loads((FIX / "real.json").read_text(encoding="utf-8"))["fixtures"]
    cache = {}
    for f in real:
        refs = [f["page_ref"]] if "page_ref" in f else f["page_refs"]
        texts = []
        for r in refs:
            k = r["text_sha256"]
            if k not in cache:
                cache[k] = norm(ft.load_real_text(r, drive))
            texts.append(cache[k])
        for e in f["expected"]:
            q = e.get("evidence_quote")
            assert not q or any(norm(q) in t for t in texts), (f["fixture_id"], q)
