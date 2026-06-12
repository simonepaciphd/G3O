"""Tests for ``g3o.run.presweep`` (Phase 3, Session B 2026-05-09)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from g3o.run.presweep import (
    PresweepConfig,
    build_manifest,
    institution_record,
    plan_run,
    run_presweep,
    stratified_sample,
    synth_institution_id,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row(
    *,
    master_row_id: int,
    country: str,
    government_level: str,
    institution_type: str,
    branch: str = "executive",
    institution_name: str | None = None,
) -> dict[str, Any]:
    return {
        "master_row_id": str(master_row_id),
        "country": country,
        "government_level": government_level,
        "branch": branch,
        "institution_type": institution_type,
        "institution_name": institution_name or f"{country}-{master_row_id}",
        "website": "",
        "source_dataset_id": "synth",
        "source_url": "",
        "source_file": "synth.csv",
        "retrieval_date": "",
        "notes": "synth",
    }


def _build_master(n_strata: int, rows_per_stratum: int) -> list[dict[str, Any]]:
    """Build ``n_strata × rows_per_stratum`` master rows across distinct strata."""
    rows: list[dict[str, Any]] = []
    rid = 0
    for s in range(n_strata):
        country = f"COUNTRY-{s:03d}"
        gov_level = ["national", "regional", "municipal"][s % 3]
        inst_type = ["ministry", "agency", "council"][s % 3]
        for _ in range(rows_per_stratum):
            rid += 1
            rows.append(
                _row(
                    master_row_id=rid,
                    country=country,
                    government_level=gov_level,
                    institution_type=inst_type,
                )
            )
    return rows


def _write_master_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    fieldnames = [
        "master_row_id",
        "country",
        "government_level",
        "branch",
        "institution_type",
        "institution_name",
        "website",
        "source_dataset_id",
        "source_url",
        "source_file",
        "retrieval_date",
        "notes",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return path


# ---------------------------------------------------------------------------
# synth_institution_id
# ---------------------------------------------------------------------------


def test_synth_institution_id_zero_padded():
    assert synth_institution_id({"master_row_id": "42"}) == "INST-0000042"
    assert synth_institution_id({"master_row_id": "1234567"}) == "INST-1234567"


def test_synth_institution_id_non_numeric_falls_back():
    assert synth_institution_id({"master_row_id": "abc"}) == "INST-abc"


def test_institution_record_projection():
    row = _row(
        master_row_id=42,
        country="TESTLAND",
        government_level="national",
        institution_type="ministry",
        branch="executive",
        institution_name="Ministry of Public Affairs",
    )
    rec = institution_record(row)
    assert rec["institution_id"] == "INST-0000042"
    assert rec["institution_name"] == "Ministry of Public Affairs"
    assert rec["country"] == "TESTLAND"
    assert rec["branch_of_government"] == "executive"
    assert rec["level_of_government"] == "national"
    assert rec["institution_type"] == "ministry"
    assert rec["website"] is None  # empty string mapped to None
    # Stage 2 bypass column (WS3 round-2) — pre-rollout the column is missing.
    assert rec["official_site_url"] is None
    assert rec["official_site_confidence"] is None


def test_institution_record_carries_official_site_url():
    """When the master row has the WS3 round-2 bypass column filled, project it."""
    row = _row(
        master_row_id=7,
        country="TESTLAND",
        government_level="national",
        institution_type="ministry",
    )
    row["official_site_url"] = "https://ministry.test.gov/"
    row["official_site_confidence"] = "high"
    rec = institution_record(row)
    assert rec["official_site_url"] == "https://ministry.test.gov/"
    assert rec["official_site_confidence"] == "high"


def test_institution_record_blank_official_site_url_maps_to_none():
    row = _row(
        master_row_id=8,
        country="TESTLAND",
        government_level="national",
        institution_type="ministry",
    )
    row["official_site_url"] = ""  # blank cell, not absent
    rec = institution_record(row)
    assert rec["official_site_url"] is None


# ---------------------------------------------------------------------------
# stratified_sample
# ---------------------------------------------------------------------------


def test_stratified_sample_deterministic_seed():
    rows = _build_master(n_strata=20, rows_per_stratum=10)
    a = stratified_sample(rows, sample_size=15, seed=22294)
    b = stratified_sample(rows, sample_size=15, seed=22294)
    assert [r["master_row_id"] for r in a] == [r["master_row_id"] for r in b]


def test_stratified_sample_different_seeds_diverge():
    rows = _build_master(n_strata=50, rows_per_stratum=5)
    a = stratified_sample(rows, sample_size=20, seed=1)
    b = stratified_sample(rows, sample_size=20, seed=2)
    assert {r["master_row_id"] for r in a} != {r["master_row_id"] for r in b}


def test_stratified_sample_n_strata_ge_sample_size_one_per_stratum():
    """When strata are abundant relative to N, each picked stratum contributes one row."""
    rows = _build_master(n_strata=50, rows_per_stratum=10)
    sample = stratified_sample(rows, sample_size=20, seed=22294)
    assert len(sample) == 20
    keys = {(r["country"], r["government_level"], r["institution_type"]) for r in sample}
    assert len(keys) == 20  # exactly one row per drawn stratum


def test_stratified_sample_n_strata_lt_sample_size_equal_quota():
    """Equal-per-stratum allocation: each stratum contributes ``base`` or ``base+1`` rows."""
    rows = _build_master(n_strata=10, rows_per_stratum=20)
    sample = stratified_sample(rows, sample_size=50, seed=22294)
    assert len(sample) == 50
    # 50 across 10 strata = 5 per stratum baseline, no remainder.
    counts: dict[tuple[str, str, str], int] = {}
    for r in sample:
        key = (r["country"], r["government_level"], r["institution_type"])
        counts[key] = counts.get(key, 0) + 1
    assert sorted(counts.values()) == [5] * 10


def test_stratified_sample_with_remainder():
    """53 across 10 strata = base 5, +1 for 3 randomly-chosen strata."""
    rows = _build_master(n_strata=10, rows_per_stratum=20)
    sample = stratified_sample(rows, sample_size=53, seed=22294)
    assert len(sample) == 53
    counts: dict[tuple[str, str, str], int] = {}
    for r in sample:
        key = (r["country"], r["government_level"], r["institution_type"])
        counts[key] = counts.get(key, 0) + 1
    vals = sorted(counts.values())
    # Either [5,5,5,5,5,5,5,6,6,6] or, in the deficit-redistribution branch, similar.
    assert vals == [5, 5, 5, 5, 5, 5, 5, 6, 6, 6]


def test_stratified_sample_deficit_redistribution():
    """Strata too small to hit quota cede their slots to strata that still have rows."""
    # 5 strata × 2 rows each = 10 rows. Want 8 → base=1, but quotas would be base=1+(extras=3)
    # Actually 8 // 5 = 1 base, 8 - 5 = 3 extras → 3 strata get 2, 2 strata get 1.
    # Each stratum has only 2 rows. So quotas are achievable: 2+2+2+1+1 = 8. No deficit.
    # Force deficit: small strata.
    rows = (
        _build_master(n_strata=2, rows_per_stratum=20)
        + [_row(master_row_id=1000 + i, country=f"S{i}", government_level="national",
                institution_type="ministry") for i in range(3)]
    )
    # 5 strata: 2 large (20 rows each), 3 tiny (1 row each). Want 15.
    # base = 3, remainder = 0. Quota = 3 each → 5 × 3 = 15.
    # Tiny strata only have 1 → contribute 1 each = 3. Large contribute 3 each = 6. Total 9.
    # Deficit = 15 - 9 = 6, redistributed to large strata (still have rows).
    sample = stratified_sample(rows, sample_size=15, seed=22294)
    assert len(sample) == 15


def test_stratified_sample_zero_size():
    rows = _build_master(n_strata=10, rows_per_stratum=5)
    assert stratified_sample(rows, sample_size=0, seed=1) == []


def test_stratified_sample_empty_rows():
    assert stratified_sample([], sample_size=10, seed=1) == []


# ---------------------------------------------------------------------------
# build_manifest + plan_run
# ---------------------------------------------------------------------------


def _make_config(*, tmp_path: Path, master_csv: Path, sample_size: int = 5) -> PresweepConfig:
    return PresweepConfig(
        run_id="20260509-test",
        runs_dir=tmp_path / "runs",
        master_csv=master_csv,
        sample_size=sample_size,
        seed=22294,
        dry_run=True,
    )


def test_build_manifest_shape(tmp_path: Path):
    rows = _build_master(n_strata=8, rows_per_stratum=3)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=4)
    sample = stratified_sample(rows, sample_size=4, seed=22294)
    manifest = build_manifest(config, sample, n_strata_observed=8)
    assert manifest["run_id"] == "20260509-test"
    assert manifest["run_kind"] == "pre-sweep"
    assert manifest["n_institutions_drawn"] == 4
    assert manifest["n_strata_observed"] == 8
    # Spec revision 2026-05-09 (D1–D2): discovery is two-phase; Stage 1a runs
    # general queries, Stage 1b runs site-restricted queries after Stage 2.
    assert "discovery_general" in manifest["stages_planned"]
    assert "discovery_site_restricted" in manifest["stages_planned"]
    assert manifest["stages_planned"].index("discovery_general") < manifest[
        "stages_planned"
    ].index("classify_official_site")
    assert manifest["stages_planned"].index("classify_official_site") < manifest[
        "stages_planned"
    ].index("discovery_site_restricted")
    assert manifest["stages_planned"][-1] == "extract"
    assert manifest["config"]["sample_size"] == 4
    assert manifest["config"]["seed"] == 22294


def test_plan_run_writes_layout(tmp_path: Path):
    rows = _build_master(n_strata=12, rows_per_stratum=4)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=7)
    plan = plan_run(config)
    run_dir = plan.run_dir
    assert run_dir.is_dir()
    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["n_institutions_drawn"] == 7
    assert len(manifest["institutions"]) == 7
    for inst_id in manifest["institutions"]:
        inst_dir = run_dir / inst_id
        assert inst_dir.is_dir()
        inst_json = inst_dir / "institution.json"
        assert inst_json.exists()
        loaded = json.loads(inst_json.read_text(encoding="utf-8"))
        assert loaded["institution_id"] == inst_id
    # Dry-run marker
    assert (run_dir / "_DRY_RUN.txt").exists()


def test_run_presweep_dry_run_returns_summary(tmp_path: Path):
    rows = _build_master(n_strata=6, rows_per_stratum=4)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=3)
    summary = run_presweep(config)
    assert summary["dry_run"] is True
    assert summary["n_institutions"] == 3
    assert "next_step" in summary
    assert "g3o presweep --execute" in summary["next_step"]


def test_plan_run_idempotent(tmp_path: Path):
    rows = _build_master(n_strata=6, rows_per_stratum=4)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=3)
    plan_a = plan_run(config)
    plan_b = plan_run(config)
    # Same seed → same sample, same manifest payload.
    assert plan_a.manifest["institutions"] == plan_b.manifest["institutions"]


def test_plan_run_empty_master_raises(tmp_path: Path):
    master = _write_master_csv(tmp_path / "master.csv", [])
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=3)
    with pytest.raises(RuntimeError, match="empty"):
        plan_run(config)


# ---------------------------------------------------------------------------
# Real master CSV — schema sanity check (skipped if absent)
# ---------------------------------------------------------------------------


def test_real_master_csv_columns_match_schema():
    """The runner reads the production master_institutions.csv via stratify keys
    that must exist as columns. If the file is absent (e.g. in CI), skip."""
    import os

    candidates = [
        Path(__file__).resolve().parents[3]
        / "inputs/G3O_Institution_Master_v2/data_final/master_institutions.csv",
    ]
    for p in candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                header = next(csv.reader(f))
            for required in (
                "master_row_id",
                "country",
                "government_level",
                "institution_type",
                "institution_name",
                "branch",
            ):
                assert required in header, f"missing column {required!r} in {p}"
            return
    if os.environ.get("G3O_REQUIRE_MASTER", "").lower() in {"1", "true"}:
        raise AssertionError("master_institutions.csv not found; set G3O_REQUIRE_MASTER=0 to skip")


# ---------------------------------------------------------------------------
# URL dedup helper (Q3=c, 2026-05-09)
# ---------------------------------------------------------------------------


def test_dedupe_key_normalizes_scheme_and_www():
    from g3o.run.presweep import _dedupe_key

    assert _dedupe_key("HTTPS://Example.GOV/x") == _dedupe_key("https://example.gov/x")
    assert _dedupe_key("https://www.example.gov/x") == _dedupe_key("https://example.gov/x")


def test_dedupe_key_strips_trailing_slash_on_non_root():
    from g3o.run.presweep import _dedupe_key

    assert _dedupe_key("https://example.gov/news/ai/") == _dedupe_key(
        "https://example.gov/news/ai"
    )


def test_dedupe_key_preserves_root_slash():
    from g3o.run.presweep import _dedupe_key

    a = _dedupe_key("https://example.gov/")
    b = _dedupe_key("https://example.gov")
    # Either consistent representation is fine; the contract is consistency.
    assert a == b


def test_dedupe_key_drops_fragment():
    from g3o.run.presweep import _dedupe_key

    assert _dedupe_key("https://example.gov/x#section") == _dedupe_key(
        "https://example.gov/x"
    )


def test_dedupe_key_keeps_query_string_intact():
    """Q3=c rejected aggressive query-param normalization."""
    from g3o.run.presweep import _dedupe_key

    a = _dedupe_key("https://example.gov/x?utm_source=foo")
    b = _dedupe_key("https://example.gov/x")
    assert a != b


def test_dedupe_key_falls_back_on_unparseable():
    from g3o.run.presweep import _dedupe_key

    # No scheme/netloc → raw URL returned unchanged.
    assert _dedupe_key("not-a-url") == "not-a-url"


def test_candidate_urls_union_dedupes_path_aware():
    from g3o.run.presweep import _candidate_urls_union

    general = {
        "INST-A": [
            {"link": "https://example.gov/news/ai-policy"},
            {"link": "https://example.gov/about"},
        ]
    }
    site = {
        "INST-A": [
            {"link": "https://www.example.gov/news/ai-policy/"},  # dup of #1
            {"link": "https://example.gov/budget"},  # new
        ]
    }
    out = _candidate_urls_union(general, site, "INST-A")
    # Exactly 3 unique keys; first-seen URL preserved (1a wins on collision).
    assert len(out) == 3
    assert out[0] == "https://example.gov/news/ai-policy"


# ---------------------------------------------------------------------------
# Stage 2 bypass guard (D1+D4, 2026-05-09)
# ---------------------------------------------------------------------------


def _write_master_csv_with_bypass_col(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Like ``_write_master_csv`` but adds the WS3 round-2 ``official_site_url`` column."""
    fieldnames = [
        "master_row_id", "country", "government_level", "branch", "institution_type",
        "institution_name", "website", "source_dataset_id", "source_url",
        "source_file", "retrieval_date", "notes", "official_site_url",
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})
    return path


def test_classify_official_site_bypass_writes_envelope_and_skips_submit(
    tmp_path: Path, monkeypatch,
):
    """Master row with non-null official_site_url → write bypass envelope, skip LLM."""
    from g3o.common import batch_client
    from g3o.run import presweep as ps

    row_a = _row(master_row_id=1, country="A", government_level="national",
                 institution_type="ministry")
    row_a["official_site_url"] = "https://ministry.a.gov/"
    row_b = _row(master_row_id=2, country="A", government_level="regional",
                 institution_type="agency")

    master = _write_master_csv_with_bypass_col(tmp_path / "master.csv", [row_a, row_b])
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    # Empty discovery for both rows. row_a is bypassed (envelope written, no
    # job); row_b has no candidate URLs and no bypass → no envelope, no job.
    discovery: dict[str, list[dict[str, Any]]] = {}

    def _fail_submit(*a: Any, **kw: Any) -> None:
        raise AssertionError("submit_batch must not be called for fully-bypassed sample")

    monkeypatch.setattr(batch_client, "submit_batch", _fail_submit)
    result = ps._run_classify_official_site(
        plan.run_dir, plan.sample, discovery,
        run_id=config.run_id, model="gpt-5-nano", poll_interval=1, max_wait=1,
    )

    assert result.get("INST-0000001") == "https://ministry.a.gov/"
    envelope_path = plan.run_dir / "INST-0000001" / "2_official_site.json"
    assert envelope_path.exists()
    payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert payload == {
        "bypassed": True,
        "source": "master_csv",
        "url": "https://ministry.a.gov/",
    }
    # The non-bypassed row got nothing (empty discovery → no envelope).
    assert not (plan.run_dir / "INST-0000002" / "2_official_site.json").exists()


# ---------------------------------------------------------------------------
# Stage 1a/1b artifact filenames + Stage 1b skip-when-null (D1–D3, 2026-05-09)
# ---------------------------------------------------------------------------


def test_run_discovery_general_writes_1a_artifact_filename(tmp_path: Path):
    """Stage 1a writes ``1a_discovery_general.json``, not the legacy ``1_discovery.json``."""
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=2, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    monkey = ps.stage_discovery.search_google
    ps.stage_discovery.search_google = lambda *a, **kw: []  # type: ignore[assignment]
    try:
        ps._run_discovery_general(
            plan.run_dir, plan.sample, languages=("en",), num_results=5,
        )
    finally:
        ps.stage_discovery.search_google = monkey  # type: ignore[assignment]

    for inst_id in plan.manifest["institutions"]:
        assert (plan.run_dir / inst_id / "1a_discovery_general.json").exists()
        assert not (plan.run_dir / inst_id / "1_discovery.json").exists()


def test_run_discovery_site_restricted_skips_when_no_site(tmp_path: Path):
    """Q2=a (2026-05-09): when official_sites[inst_id] is None, Stage 1b is skipped."""
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=2, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    inst_a, inst_b = plan.manifest["institutions"]
    official_sites: dict[str, str | None] = {inst_a: "https://a.gov/", inst_b: None}

    seen_queries: list[str] = []

    def _capture(query: str, num_results: int = 10, force_refresh: bool = False) -> list[dict]:
        seen_queries.append(query)
        return []

    monkey = ps.stage_discovery.search_google
    ps.stage_discovery.search_google = _capture  # type: ignore[assignment]
    try:
        out = ps._run_discovery_site_restricted(
            plan.run_dir, plan.sample, official_sites,
            languages=("en",), num_results=5,
        )
    finally:
        ps.stage_discovery.search_google = monkey  # type: ignore[assignment]

    # Inst A: queries fired, 1b file written. Inst B: skipped — no queries, no file.
    assert (plan.run_dir / inst_a / "1b_discovery_site_restricted.json").exists()
    assert not (plan.run_dir / inst_b / "1b_discovery_site_restricted.json").exists()
    assert all(q.startswith("site:a.gov ") for q in seen_queries)
    # Q1=a: same per-language query count as Stage 1a (4 English GenAI terms).
    assert len(seen_queries) == 4
    assert inst_a in out and inst_b not in out


def test_run_discovery_site_restricted_records_carry_site_domain(tmp_path: Path):
    """Stage 1b records each include the ``site_domain`` they were scoped to."""
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)

    inst_id = plan.manifest["institutions"][0]
    canned = [
        {"link": "https://example.gov/policy", "title": "Policy", "snippet": "x",
         "domain": "example.gov", "position": 1, "date": None, "sitelinks": []},
    ]

    monkey = ps.stage_discovery.search_google
    ps.stage_discovery.search_google = lambda *a, **kw: canned  # type: ignore[assignment]
    try:
        out = ps._run_discovery_site_restricted(
            plan.run_dir, plan.sample, {inst_id: "https://example.gov/"},
            languages=("en",), num_results=5,
        )
    finally:
        ps.stage_discovery.search_google = monkey  # type: ignore[assignment]

    payload = json.loads(
        (plan.run_dir / inst_id / "1b_discovery_site_restricted.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["site_domain"] == "example.gov"
    assert all(r.get("site_domain") == "example.gov" for r in payload["records"])
    # Returned dict mirrors the records keyed by institution_id.
    assert inst_id in out


# ---------------------------------------------------------------------------
# Session E (2026-05-09) — state files, resume, scrape idempotency, Stage 6 fold
# ---------------------------------------------------------------------------


def _batch_status(state: str, batch_id: str = "batch-test"):
    from g3o.common.batch_client import BatchStatus

    return BatchStatus(
        batch_id=batch_id, status=state, request_counts={},
        output_file_id=None, error_file_id=None,
    )


def _batch_handle(batch_id: str = "batch-test", n_jobs: int = 1):
    from datetime import datetime, timezone

    from g3o.common.batch_client import BatchHandle

    return BatchHandle(
        batch_id=batch_id, input_file_id="file-test",
        submitted_at=datetime.now(timezone.utc), n_jobs=n_jobs,
    )


def test_stages_includes_validate(tmp_path: Path):
    """Q8=ii (Session E): Stage 6 (validate) is folded into STAGES."""
    from g3o.run.presweep import STAGES

    assert STAGES == (
        "discovery_general",
        "classify_official_site",
        "discovery_site_restricted",
        "classify_triage",
        "scrape",
        "extract",
        "validate",
    )


def test_stage2_all_bypassed_writes_done_marker_no_state(tmp_path: Path, monkeypatch):
    """Q1=a, Q4(a): all rows bypassed → no batch, no _state/{stage}.json,
    .done/{stage}.json marker recorded with no_batch=True."""
    from g3o.common import batch_client
    from g3o.common.run_state import done_path, state_path
    from g3o.run import presweep as ps

    row_a = _row(master_row_id=1, country="A", government_level="national",
                 institution_type="ministry")
    row_a["official_site_url"] = "https://a.gov/"
    row_b = _row(master_row_id=2, country="B", government_level="national",
                 institution_type="ministry")
    row_b["official_site_url"] = "https://b.gov/"
    master = _write_master_csv_with_bypass_col(tmp_path / "master.csv", [row_a, row_b])
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    monkeypatch.setattr(
        batch_client, "submit_batch",
        lambda *a, **kw: pytest.fail(
            "submit_batch must not be called when all rows are bypassed"
        ),
    )
    out = ps._run_classify_official_site(
        plan.run_dir, plan.sample, {},
        run_id=config.run_id, model="gpt-5-nano", poll_interval=1, max_wait=1,
    )

    # Both bypass envelopes written.
    assert out["INST-0000001"] == "https://a.gov/"
    assert out["INST-0000002"] == "https://b.gov/"
    # No active state file; .done marker present with no_batch=True.
    assert not state_path(plan.run_dir, "classify_official_site").exists()
    done = done_path(plan.run_dir, "classify_official_site")
    assert done.exists()
    payload = json.loads(done.read_text(encoding="utf-8"))
    assert payload["no_batch"] is True


def test_stage2_mixed_bypass_writes_state_file_with_bypass_count(
    tmp_path: Path, monkeypatch,
):
    """Q4(b): mixed bypass + LLM → state file covers LLM subset only;
    bypass_count recorded; submit_batch called once with the LLM jobs."""
    from g3o.common import batch_client
    from g3o.common.run_state import load_state
    from g3o.run import presweep as ps

    row_bypass = _row(master_row_id=1, country="A", government_level="national",
                      institution_type="ministry")
    row_bypass["official_site_url"] = "https://a.gov/"
    row_llm = _row(master_row_id=2, country="B", government_level="national",
                   institution_type="agency")
    master = _write_master_csv_with_bypass_col(
        tmp_path / "master.csv", [row_bypass, row_llm]
    )
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    discovery: dict[str, list[dict[str, Any]]] = {
        "INST-0000002": [{"link": "https://b.example/news"}, {"link": "https://b.example/about"}]
    }

    submit_calls: list[Any] = []

    def _capture_submit(jobs, **kw):
        submit_calls.append(jobs)
        return _batch_handle(batch_id="batch-stage2", n_jobs=len(jobs))

    monkeypatch.setattr(batch_client, "submit_batch", _capture_submit)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])
    monkeypatch.setattr(
        batch_client, "poll_batch",
        lambda batch_id, client=None: _batch_status("completed", batch_id=batch_id),
    )
    monkeypatch.setattr(
        batch_client, "fetch_results",
        lambda batch_id, client=None, status=None: iter([]),
    )
    ps._run_classify_official_site(
        plan.run_dir, plan.sample, discovery,
        run_id=config.run_id, model="gpt-5-nano", poll_interval=0, max_wait=1,
    )

    assert len(submit_calls) == 1
    assert len(submit_calls[0]) == 1  # only the non-bypassed institution
    assert submit_calls[0][0].custom_id == "INST-0000002"

    # State file moved to .done after fetch; bypass_count was recorded.
    from g3o.common.run_state import done_path

    done_payload = json.loads(
        done_path(plan.run_dir, "classify_official_site").read_text(encoding="utf-8")
    )
    assert done_payload["bypass_count"] == 1
    assert done_payload["n_chunks"] == 1
    assert done_payload["chunks"]["1"]["custom_ids"] == ["INST-0000002"]
    assert done_payload["chunks"]["1"]["batch_id"] == "batch-stage2"
    assert "fetched_at" in done_payload
    # Active file gone.
    assert load_state(plan.run_dir, "classify_official_site") is None


def test_stage2_resume_after_crash_does_not_resubmit(tmp_path: Path, monkeypatch):
    """Q6=a gate test: mid-poll crash → state file persists batch_id; on
    resume, submit_batch is NOT called, polling rejoins, fetch runs once."""
    from g3o.common import batch_client
    from g3o.common.run_state import is_done, load_state, state_path
    from g3o.run import presweep as ps

    row_llm = _row(master_row_id=2, country="B", government_level="national",
                   institution_type="agency")
    master = _write_master_csv_with_bypass_col(tmp_path / "master.csv", [row_llm])
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    discovery = {"INST-0000002": [{"link": "https://b.example/x"}]}

    # --- Phase 1: submit OK, first poll returns in_progress, second poll raises.
    submit_calls: list[Any] = []

    def _ok_submit(jobs, **kw):
        submit_calls.append(jobs)
        return _batch_handle(batch_id="batch-resume-1", n_jobs=len(jobs))

    poll_calls: list[str] = []

    def _crash_on_second_poll(batch_id, client=None):
        poll_calls.append(batch_id)
        if len(poll_calls) == 1:
            return _batch_status("in_progress", batch_id=batch_id)
        raise KeyboardInterrupt("simulated mid-poll crash")

    monkeypatch.setattr(batch_client, "submit_batch", _ok_submit)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", lambda md, **kw: [])
    monkeypatch.setattr(batch_client, "poll_batch", _crash_on_second_poll)
    with pytest.raises(KeyboardInterrupt):
        ps._run_classify_official_site(
            plan.run_dir, plan.sample, discovery,
            run_id=config.run_id, model="gpt-5-nano", poll_interval=0, max_wait=10,
        )

    # State file persisted; .done not present yet.
    state = load_state(plan.run_dir, "classify_official_site")
    assert state is not None
    assert state["chunks"]["1"]["batch_id"] == "batch-resume-1"
    assert state["chunks"]["1"]["last_status"] == "in_progress"
    assert not is_done(plan.run_dir, "classify_official_site")
    assert len(submit_calls) == 1

    # --- Phase 2: resume. submit_batch must NOT be called; poll returns
    # completed; fetch yields one parsed result.
    def _fail_submit(*a, **kw):
        raise AssertionError("submit_batch must not be called on resume")

    def _fail_reconcile(*a, **kw):
        raise AssertionError(
            "reconciliation must not run for a chunk that already has a batch_id"
        )

    fetch_calls: list[str] = []

    def _yield_one_result(batch_id, client=None, status=None):
        fetch_calls.append(batch_id)
        from g3o.common.batch_client import BatchResult

        yield BatchResult(
            custom_id="INST-0000002",
            success=True,
            response={
                "body": {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "url": "https://b.example/official",
                                        "confidence": "high",
                                        "rationale": "test",
                                    }
                                )
                            }
                        }
                    ]
                }
            },
            error=None,
        )

    monkeypatch.setattr(batch_client, "submit_batch", _fail_submit)
    monkeypatch.setattr(batch_client, "find_batches_by_metadata", _fail_reconcile)
    monkeypatch.setattr(
        batch_client, "poll_batch",
        lambda batch_id, client=None: _batch_status("completed", batch_id=batch_id),
    )
    monkeypatch.setattr(batch_client, "fetch_results", _yield_one_result)
    out = ps._run_classify_official_site(
        plan.run_dir, plan.sample, discovery,
        run_id=config.run_id, model="gpt-5-nano", poll_interval=0, max_wait=10,
    )

    # Resume completed: state file moved to .done; only one fetch happened.
    assert is_done(plan.run_dir, "classify_official_site")
    assert not state_path(plan.run_dir, "classify_official_site").exists()
    assert out["INST-0000002"] == "https://b.example/official"
    assert fetch_calls == ["batch-resume-1"]


def test_stage2_done_marker_short_circuits(tmp_path: Path, monkeypatch):
    """Q3=e2: when .done/classify_official_site.json is present, the runner
    skips the stage and reconstructs ``out`` from disk envelopes."""
    from g3o.common import batch_client
    from g3o.common.run_state import mark_done
    from g3o.run import presweep as ps

    row = _row(master_row_id=1, country="A", government_level="national",
               institution_type="ministry")
    row["official_site_url"] = "https://a.gov/"
    master = _write_master_csv_with_bypass_col(tmp_path / "master.csv", [row])
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    # Pre-write a bypass envelope as if a prior run had completed Stage 2.
    inst_dir = plan.run_dir / "INST-0000001"
    (inst_dir / "2_official_site.json").write_text(
        json.dumps({"bypassed": True, "source": "master_csv", "url": "https://a.gov/"}),
        encoding="utf-8",
    )
    mark_done(plan.run_dir, "classify_official_site", no_batch=True)

    # submit_batch must not fire on a done-marker short-circuit.
    monkeypatch.setattr(
        batch_client, "submit_batch",
        lambda *a, **kw: pytest.fail(
            "submit_batch must not be called when .done marker is present"
        ),
    )
    out = ps._run_classify_official_site(
        plan.run_dir, plan.sample, {},
        run_id=config.run_id, model="gpt-5-nano", poll_interval=1, max_wait=1,
    )

    assert out["INST-0000001"] == "https://a.gov/"


def test_stage4_skips_refetch_when_url_hash_file_exists(tmp_path: Path):
    """Q5=a: ``runs/<run_id>/<inst_id>/scrape/<url_hash>.json`` already on
    disk → no scrape_url call for that URL."""
    from g3o.run import presweep as ps
    from g3o.scrape.render import FetchMetadata, RenderedPage

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    inst_id = plan.manifest["institutions"][0]
    triaged = {inst_id: ["https://x.example/a", "https://x.example/b"]}

    # Pre-seed one URL's per-run output file.
    from g3o.extract.batch import url_hash

    scrape_dir = plan.run_dir / inst_id / "scrape"
    scrape_dir.mkdir(parents=True, exist_ok=True)
    cached = RenderedPage(
        url="https://x.example/a", text="cached", title="A",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-05-09", http_status=200, final_url="https://x.example/a",
            fetch_method="html", elapsed_ms=10, wait_for=None,
        ),
    )
    (scrape_dir / f"{url_hash('https://x.example/a')}.json").write_text(
        cached.model_dump_json(), encoding="utf-8"
    )

    fetched: list[str] = []

    def _capture_scrape(url, **kwargs):
        fetched.append(url)
        return RenderedPage(
            url=url, text=f"fresh-{url}", title="",
            content_type="html",
            fetch_metadata=FetchMetadata(
                access_date="2026-05-09", http_status=200, final_url=url,
                fetch_method="html", elapsed_ms=10, wait_for=None,
            ),
        )

    monkey = ps.stage_scrape.scrape_url
    ps.stage_scrape.scrape_url = _capture_scrape  # type: ignore[assignment]
    try:
        # respect_robots=False + zero delay keep this idempotency test offline
        # and fast (the F14 politeness path is covered in test_politeness.py).
        out = ps._run_scrape(
            plan.run_dir, plan.sample, triaged,
            respect_robots=False, host_delay_seconds=0,
        )
    finally:
        ps.stage_scrape.scrape_url = monkey  # type: ignore[assignment]

    # Only the second URL was fetched; the first was loaded from disk.
    assert fetched == ["https://x.example/b"]
    pages = out[inst_id]
    assert len(pages) == 2
    by_url = {p.url: p.text for p in pages}
    assert by_url["https://x.example/a"] == "cached"
    assert by_url["https://x.example/b"] == "fresh-https://x.example/b"


def test_stage4_done_marker_short_circuits_no_scrape_calls(tmp_path: Path):
    """Q3=e2: ``.done/scrape.json`` present → no scrape_url calls; pages
    reconstructed from per-URL files on disk."""
    from g3o.common.run_state import mark_done
    from g3o.run import presweep as ps
    from g3o.scrape.render import FetchMetadata, RenderedPage

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    inst_id = plan.manifest["institutions"][0]
    triaged = {inst_id: ["https://x.example/a"]}

    from g3o.extract.batch import url_hash

    scrape_dir = plan.run_dir / inst_id / "scrape"
    scrape_dir.mkdir(parents=True, exist_ok=True)
    cached = RenderedPage(
        url="https://x.example/a", text="cached", title="A",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-05-09", http_status=200, final_url="https://x.example/a",
            fetch_method="html", elapsed_ms=10, wait_for=None,
        ),
    )
    (scrape_dir / f"{url_hash('https://x.example/a')}.json").write_text(
        cached.model_dump_json(), encoding="utf-8"
    )
    mark_done(plan.run_dir, "scrape", no_batch=True)

    monkey = ps.stage_scrape.scrape_url
    ps.stage_scrape.scrape_url = lambda url, **kw: pytest.fail(  # type: ignore[assignment]
        "scrape_url must not be called when .done/scrape.json is present"
    )
    try:
        out = ps._run_scrape(plan.run_dir, plan.sample, triaged)
    finally:
        ps.stage_scrape.scrape_url = monkey  # type: ignore[assignment]

    pages = out[inst_id]
    assert len(pages) == 1
    assert pages[0].text == "cached"


def test_stage4_robots_disallow_skips_url_and_records_attrition(tmp_path: Path):
    """Review F14 / D4: a robots.txt Disallow skips the URL and writes a
    ``robots_disallowed`` attrition record; allowed URLs still scrape."""
    from g3o.common import attrition
    from g3o.run import presweep as ps
    from g3o.scrape.render import FetchMetadata, RenderedPage

    attrition._reset_cache()
    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    inst_id = plan.manifest["institutions"][0]
    triaged = {inst_id: ["https://x.example/ok", "https://x.example/private"]}

    class _Robots:
        def allowed(self, url: str) -> bool:
            return "private" not in url

        def crawl_delay(self, url: str):
            return None

    scraped_urls: list[str] = []

    def _scrape(url, **kwargs):
        scraped_urls.append(url)
        return RenderedPage(
            url=url, text="body text long enough to be kept", title="",
            content_type="html",
            fetch_metadata=FetchMetadata(
                access_date="2026-05-09", http_status=200, final_url=url,
                fetch_method="html", elapsed_ms=1, wait_for=None,
            ),
        )

    monkey = ps.stage_scrape.scrape_url
    ps.stage_scrape.scrape_url = _scrape  # type: ignore[assignment]
    try:
        out = ps._run_scrape(
            plan.run_dir, plan.sample, triaged,
            respect_robots=True, robots=_Robots(), host_delay_seconds=0,
        )
    finally:
        ps.stage_scrape.scrape_url = monkey  # type: ignore[assignment]

    assert scraped_urls == ["https://x.example/ok"]
    assert [p.url for p in out[inst_id]] == ["https://x.example/ok"]
    reasons = [(r["reason"], r.get("url")) for r in attrition.read_records(plan.run_dir)]
    assert ("robots_disallowed", "https://x.example/private") in reasons


def test_stage5_extract_threads_run_model_into_jobs(tmp_path: Path, monkeypatch):
    """Review F18a: presweep threads the run's model into build_extract_jobs so
    ``batch_metadata.model_label`` reflects it, not the literal ``gpt-5-nano``."""
    from g3o.run import presweep as ps
    from g3o.scrape.render import FetchMetadata, RenderedPage

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=1)
    plan = ps.plan_run(config)
    inst_id = plan.manifest["institutions"][0]
    page = RenderedPage(
        url="https://x.example/a",
        text="This page has well over fifty non-whitespace characters of body text.",
        title="A", content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-05-09", http_status=200, final_url="https://x.example/a",
            fetch_method="html", elapsed_ms=1, wait_for=None,
        ),
    )

    captured: dict[str, Any] = {}

    def _capture_build(pairs, *, batch_id, institution_search_languages,
                       model_label=None, chat_type="web"):
        captured["model_label"] = model_label
        return []

    monkeypatch.setattr(ps.stage_extract, "build_extract_jobs", _capture_build)
    monkeypatch.setattr(ps.stage_extract, "run_chunked_stage", lambda *a, **k: None)

    ps._run_extract(
        plan.run_dir, plan.sample, {inst_id: [page]},
        institution_search_languages="en", model="gpt-5-mini-xyz",
        poll_interval=1, max_wait=1, run_id=config.run_id,
    )
    assert captured["model_label"] == "gpt-5-mini-xyz"


def test_stage1a_writes_done_marker_at_end(tmp_path: Path):
    """Stage 1a's ``mark_done(no_batch=True)`` marker enables resume case (e)."""
    from g3o.common.run_state import is_done
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=2, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    config = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=2)
    plan = ps.plan_run(config)

    monkey = ps.stage_discovery.search_google
    ps.stage_discovery.search_google = lambda *a, **kw: []  # type: ignore[assignment]
    try:
        ps._run_discovery_general(
            plan.run_dir, plan.sample, languages=("en",), num_results=5,
        )
    finally:
        ps.stage_discovery.search_google = monkey  # type: ignore[assignment]

    assert is_done(plan.run_dir, "discovery_general")
