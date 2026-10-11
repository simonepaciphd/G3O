"""Core unit + end-to-end staging-path tests, offline.

Standing lab rule: prove the whole five-stage path on a handful of records
before touching a live source. These run entirely on the synthetic fixtures in
tests/fixtures/_ocds_sample/ — no network, no real procurement data.

Run:  .venv/bin/pytest -q
"""

from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

import pytest

from pipeline.core import contract
from pipeline.core.base import Pipeline, SourceAdapter
from pipeline.core.classify import (
    CANNOT_TYPE_FLAG, LOW_SCORE_FLAG, NLPClassifier, contract_uncertainty_flags,
    is_valid_activity_type)
from pipeline.core.coding import (
    CANNOT_TYPE, activity_type_for, adoption_stage_for, stage_dating_field, vendor_for)
from pipeline.core.models import (
    GenAIQuerySet, Hit, InstitutionLink, InstitutionReview, RawRecord)
from pipeline.core.search import (
    find_regex, find_terms, load_queries, local_filter, normalize)
from pipeline.core.standardize import build_extension, extract_ocds, standardize
from pipeline.core.store import StagingStore, ValidationError
from pipeline.cli import cmd_run

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "_ocds_sample"
SCHEMA_DIR = ROOT / "config" / "schema"
CONTRACT_SNAPSHOT = ROOT / "docs" / "reference" / "output_contract_v2.0.SNAPSHOT.md"

# The approved set (PI ruling D4, 2026-08-04) — the same file the CLI loads.
QUERIES = load_queries(str(ROOT / "config" / "genai_queries.yaml"))


def _extract_one(name: str) -> dict:
    """First staged record from a fixture. Most fixtures stage exactly one."""
    records = extract_ocds(_raw(name))
    assert records, f"{name} staged nothing"
    return records[0]


def _raw(name: str) -> RawRecord:
    with open(FIXTURES / f"{name}.json", "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return RawRecord(
        source_id="fixture_ocds",
        native_id=name,
        payload=payload,
        fetched_at="2026-08-03T12:00:00Z",
        raw_payload_ref=f"tests/fixtures/_ocds_sample/{name}.json",
    )


class FixtureAdapter(SourceAdapter):
    """Offline adapter over the synthetic fixtures. The shape a real OCDS
    adapter takes, minus the transport."""

    def __init__(self, names=("award_relevant", "tender_ambiguous", "award_irrelevant")):
        super().__init__({
            "source_id": "fixture_ocds",
            "access_mode": "api",
            "is_ocds": True,
            "country_iso3": "ZZZ",
            "country_name": "Fixtureland",
            "repo_name": "Synthetic OCDS fixtures",
            "coverage_type": "both",
        })
        self.names = names

    def search(self, queries):
        return [Hit(self.source_id, n) for n in self.names]

    def fetch(self, hits):
        return [_raw(h.native_id) for h in hits]


# --------------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,title", [
    ("procurement_record.schema.json", "G3O Standardized Procurement Record"),
    ("procurement_extension.schema.json", "G3O Procurement Extension Record"),
    ("institution_link.schema.json", "G3O Procurement Institution Link"),
])
def test_schema_files_parse(name, title):
    with open(SCHEMA_DIR / name, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["title"] == title


def test_record_schema_carries_the_spec_7_additions():
    with open(SCHEMA_DIR / "procurement_record.schema.json", "r", encoding="utf-8") as fh:
        props = json.load(fh)["properties"]
    assert "buyer_url" in props and "buyer_national_id" in props


def test_genai_category_enum_matches_the_contract_snapshot():
    """genai_category takes the contract's activity_type (D12). The members must
    match the pinned contract verbatim — this is the guard against anyone
    re-typing, extending, or "tidying" an enum the contract owns."""
    with open(SCHEMA_DIR / "procurement_record.schema.json", "r", encoding="utf-8") as fh:
        members = json.load(fh)["properties"]["genai_category"]["enum"]
    assert [m for m in members if m is not None] == list(contract.ACTIVITY_TYPE)


@pytest.mark.parametrize("constant,column", [
    (contract.ACTIVITY_TYPE, "activity_type"),
    (contract.ADOPTION_STAGE, "adoption_stage"),
    (contract.GENAI_EVIDENCE, "genai_evidence"),
    (contract.HAS_GENAI_ACTIVITY, "has_genai_activity"),
])
def test_contract_constants_are_transcribed_from_the_pinned_snapshot(constant, column):
    """core/contract.py claims to be a verbatim copy. Prove it against the file:
    every member must appear in the snapshot's own JSON-schema enum for that
    column, and the counts must agree so nothing was added or dropped."""
    snapshot = CONTRACT_SNAPSHOT.read_text(encoding="utf-8")
    declared = re.search(rf'"{column}": {{"enum":\[(.*?)\]}}', snapshot)
    assert declared, f"{column} enum not found in the contract snapshot"
    from_file = [m.strip('"') for m in declared.group(1).split(",")]
    assert list(constant) == from_file


def test_uncertainty_flag_vocabulary_is_closed():
    """The contract says 'use these exact strings'. Our operational triggers are
    prefixed and must be filtered out before they reach contract output."""
    kept = contract_uncertainty_flags(
        ["genai_vs_traditional_ai", LOW_SCORE_FLAG, "made_up_flag"])
    assert kept == ["genai_vs_traditional_ai"]
    assert LOW_SCORE_FLAG.startswith("internal_")


# --------------------------------------------------------------------------- #
# search / normalization
# --------------------------------------------------------------------------- #

def test_normalize_folds_diacritics_and_case():
    assert normalize("IA Générative") == "ia generative"


def test_normalize_preserves_non_latin_script():
    """Matching happens in the source's language; nothing is transliterated."""
    assert "بانک" in normalize("د افغانستان بانک")


def test_find_terms_returns_original_spelling():
    hits = find_terms("Contrato de IA generativa municipal", QUERIES.all_terms())
    assert "IA generativa" in hits


def test_find_terms_respects_word_boundaries():
    assert find_terms("the plaintiff said nothing", ["AI"]) == []


def test_find_terms_deduplicates_across_language_blocks():
    """The draft repeats product names in en/es/fr/pt. Counting one match four
    times would inflate any score that counts distinct signals."""
    hits = find_terms("Licences for Microsoft Copilot", QUERIES.all_terms())
    assert hits == ["Microsoft Copilot"]


def test_local_filter_is_high_recall_and_passes_quarantined_products():
    assert local_filter("Licences for Microsoft Copilot", QUERIES) is True
    assert local_filter("Repair of municipal water pipes", QUERIES) is False


def test_query_loader_rejects_invalid_regex_before_collection(tmp_path):
    query_file = tmp_path / "bad_queries.yaml"
    query_file.write_text('version: "test"\nregex: ["["]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid regex"):
        load_queries(str(query_file))


# --------------------------------------------------------------------------- #
# OCDS extraction
# --------------------------------------------------------------------------- #

def test_extract_ocds_award_unwraps_the_package_and_reads_the_award_branch():
    f = _extract_one("award_relevant")
    assert f["notice_type"] == "award"
    assert f["ocds_ocid"] == "ocds-synthetic-0001"
    assert f["buyer_name"].startswith("Ministerio")
    assert f["supplier_name"].startswith("Distribuidora")
    # awarded sum wins over the tender estimate, and says so
    assert f["value_amount"] == 452300.5
    assert f["value_is_estimated"] is False
    assert f["award_date"] == "2026-03-10"
    assert f["contract_start_date"] == "2026-04-01"
    assert f["procedure_type"] == "open"
    assert f["bidder_count"] == 4


def test_extract_ocds_pulls_the_matching_signals_for_institution_matching():
    f = _extract_one("award_relevant")
    assert f["buyer_url"] == "https://ministerio.example.org/contrataciones"
    assert f["buyer_national_id"] == "NAT-4471-SYN"
    assert f["buyer_email_domain"] == "ministerio.example.org"


def test_extract_ocds_tender_uses_the_estimate_and_flags_the_framework():
    f = _extract_one("tender_ambiguous")
    assert f["notice_type"] == "tender"
    assert f["value_is_estimated"] is True
    assert f["procedure_type"] == "framework_establishment"
    assert f["value_covers"] == "unknown"  # ceiling cannot be inferred from framework status
    assert "award_date" not in f


def test_extract_ocds_uses_release_id_so_tender_and_award_do_not_collapse():
    """Keying on the ocid would collapse the tender and award releases of one
    contracting process onto a single record_id, and the award would overwrite
    the tender. Award records are additionally suffixed with their award id so a
    release carrying several awards stages several records (ruling D6)."""
    award = _extract_one("award_relevant")
    tender = _extract_one("tender_ambiguous")
    assert award["native_id"].startswith("synthetic-0001-award-01")
    assert award["native_id"] != award["ocds_ocid"]
    assert tender["native_id"] == "synthetic-0002-tender-01"   # no award, no suffix


def test_extract_ocds_does_not_infer_negotiated_from_limited_method():
    f = _extract_one("award_irrelevant")
    assert f["procedure_type"] == "unknown"


def test_extract_ocds_never_invents_a_url():
    f = _extract_one("award_irrelevant")
    assert f["url"] == "https://municipio.example.org/contratos/synthetic-0003"


# --------------------------------------------------------------------------- #
# classification (codebook §5.1 mapping)
# --------------------------------------------------------------------------- #

def _classify(name):
    return NLPClassifier(QUERIES).classify(_extract_one(name))


def test_explicit_generative_term_is_yes():
    c = _classify("award_relevant")
    assert (c.relevance, c.genai_evidence_type, c.genai_relevant) == \
        ("yes", "confirms_activity", True)
    assert "IA generativa" in c.genai_evidence


def test_context_required_product_alone_is_unclear_not_yes():
    c = _classify("tender_ambiguous")
    assert (c.relevance, c.genai_evidence_type, c.genai_relevant) == \
        ("unclear", "ambiguous", False)
    assert "genai_vs_traditional_ai" in c.review_flags


def test_context_required_quarantine_is_normalization_safe():
    queries = GenAIQuerySet(
        version="test",
        terms={"en": ["microsoft copilot"]},
        context_required_terms=["Microsoft Copilot"],
    )
    c = NLPClassifier(queries).classify({"title": "MICROSOFT COPILOT licences"})
    assert c.relevance == "unclear"


def test_no_signal_is_per_source_absence_not_an_institution_verdict():
    """Contract Edge Case A codes a supplied page with no GenAI mention as
    confirms_absence on THAT row (column 36). What one record cannot settle is
    has_genai_activity (column 8), which is institution-level."""
    c = _classify("award_irrelevant")
    assert (c.relevance, c.genai_evidence_type) == ("no", "confirms_absence")
    assert c.genai_evidence_type in contract.GENAI_EVIDENCE


def test_classifier_evidence_never_exceeds_contract_snippet_cap():
    c = NLPClassifier(QUERIES).classify({
        "title": "Generative AI " + ("long evidence " * 100),
    })
    assert len(c.genai_evidence) <= 300


def test_exclude_term_kills_the_acronym_collision():
    c = NLPClassifier(QUERIES).classify(
        {"title": "Server storage maintenance",
         "description": "Includes GPT partition table repair on file servers."})
    assert c.relevance == "no"


def test_exclude_term_does_not_override_an_explicit_term():
    c = NLPClassifier(QUERIES).classify(
        {"title": "Generative AI licences",
         "description": "Also covers GPT partition table maintenance."})
    assert c.relevance == "yes"


def test_classifier_leaves_the_category_valid_and_unset():
    """The enum is known now, but which member procurement evidence supports is
    a coding rule nobody has written. Unset, not guessed."""
    c = _classify("award_relevant")
    assert c.genai_category is None
    assert is_valid_activity_type(c.genai_category)


def test_classifier_never_assigns_a_category():
    """genai_category takes the contract's activity_type values, which are not
    available here. Guessing one is the taxonomy invention the ruling forbids."""
    assert _classify("award_relevant").genai_category is None


def test_classifier_version_is_recorded_for_the_transparency_trail():
    assert _classify("award_relevant").classifier_version.endswith(QUERIES.version)


# --------------------------------------------------------------------------- #
# PI rulings of 2026-08-04
# --------------------------------------------------------------------------- #

def test_query_set_is_the_approved_one_not_a_draft():
    """Ruling D4: the draft was approved as-is and promoted. The pipeline must
    load the approved file, and its version must no longer say draft."""
    assert QUERIES.version == "1.0"
    assert "draft" not in QUERIES.version.lower()
    assert not (ROOT / "config" / "genai_queries.DRAFT-v0.1.yaml").exists()


def test_gpt_regex_behaviour_is_pinned_exactly_as_shipped():
    """Ruling D4 ships the GPT pattern as-is with a recorded recall gap. The
    measured behaviour is narrower than "does not match GPT-5":

      GPT-4   -> matches in full
      GPT-5   -> matches, but only the bare token `GPT` (the version branch
                 covers 2/3/4, then the word boundary before `-` lets bare GPT
                 match). So a GPT-5 notice IS retrieved — but on a regex-only
                 signal, which the classifier routes to `unclear` + review
                 rather than confirming.
      GPT5    -> no match at all. This unhyphenated form is the true blind spot.

    Pinned, not fixed: widening the pattern is a term-set change and needs a PI
    decision. If this test fails, someone edited the approved query set.
    """
    assert find_regex("procurement of GPT-4 services", QUERIES.regex)
    assert find_regex("procurement of GPT-5 services", QUERIES.regex)
    assert not find_regex("procurement of GPT5 services", QUERIES.regex)

    # A GPT-5 notice with no other signal reaches review, never a confirmed yes.
    clf = NLPClassifier(QUERIES).classify(
        {"title": "Supply of GPT-5 based assistant", "description": ""})
    assert clf.relevance == "unclear"
    assert "genai_vs_traditional_ai" in clf.review_flags

    header = (ROOT / "config" / "genai_queries.yaml").read_text(encoding="utf-8")
    assert "KNOWN DEFECT" in header and "GPT5" in header


def test_tender_is_proposed_and_award_is_announced():
    """Ruling D2/D3 overrides the recommended default in spec §6.2: a tender-only
    record DOES create an activity row, staged as `proposed` — but only when the
    evidence confirms activity (bug fix 2026-08-08; see adoption_stage_for's
    docstring — the ruling's own text ties `proposed` to `confirms_activity`)."""
    assert adoption_stage_for("tender", "confirms_activity") == "proposed"
    assert adoption_stage_for("award", "confirms_activity") == "announced"
    assert adoption_stage_for("unknown", "confirms_activity") is None  # no ruled stage, so none invented
    assert stage_dating_field("award") == "award_date"
    assert stage_dating_field("tender") == "publication_date"


def test_no_stage_for_a_record_whose_evidence_does_not_confirm_activity():
    """Bug fix 2026-08-08: caught reviewing the first live sample, where all 5
    confirms_absence records were incorrectly staged `proposed`. A tender or
    award with confirms_absence / ambiguous / background_only evidence gets no
    staged adoption_stage — the eventual contract mapper emits `_NA_` for these,
    not this function."""
    for notice_type in ("tender", "award", "unknown"):
        for evidence_type in ("confirms_absence", "ambiguous", "background_only"):
            assert adoption_stage_for(notice_type, evidence_type) is None, (
                notice_type, evidence_type)


def test_production_is_unreachable_from_procurement_evidence():
    """Spec §6.1: a purchase is not a deployment."""
    assert "production" not in set(
        adoption_stage_for(n, "confirms_activity") for n in ("tender", "award", "unknown"))


def test_activity_type_is_applied_directly_when_the_notice_says_so():
    """Ruling Q1a: the contract's §4.2 'typical evidence' column already names
    procurement records for these three members."""
    assert activity_type_for(
        {"title": "Licences for internal staff drafting assistant"})[0] == "internal_operational"
    assert activity_type_for(
        {"title": "Chatbot for citizen enquiries"})[0] == "public_facing_service"
    assert activity_type_for(
        {"title": "Pilot of a generative AI assistant"})[0] == "pilot_experiment"


def test_a_trial_wins_over_its_setting():
    """A pilot run for internal staff is still a pilot; precedence is explicit."""
    assert activity_type_for(
        {"title": "Pilot for internal staff", "description": "trial"})[0] == "pilot_experiment"


def test_untypeable_record_is_reported_not_coded():
    """Ruling D1: `unknown` is the ruled answer but is not legal until contract
    v2.2 lands, so the record must carry a flag rather than a guessed value."""
    typed, signals = activity_type_for({"title": "Suministro de soluciones", "description": ""})
    assert typed == CANNOT_TYPE and signals == []
    clf = NLPClassifier(QUERIES).classify(
        {"title": "Adquisición de IA generativa", "description": "Contrato marco."})
    assert clf.relevance == "yes"
    assert clf.genai_category is None
    assert CANNOT_TYPE_FLAG in clf.review_flags


def test_activity_typing_is_english_only_and_that_is_visible():
    """MEASURED GAP, surfaced not patched. The §4.2 signals are English, so a
    Spanish notice that an English one would type lands in CANNOT_TYPE and is
    reported instead. Many OCDS sources are Spanish-language, so on a real run
    this is the common case, not the edge case.

    Not fixed here on purpose: per-language rosters belong to
    subprojects/multilingual-pipeline/ (PI ruling D4), so adding Spanish signals
    would be deciding something that is not ours. Delete this test when the
    rosters arrive.
    """
    english = {"title": "Generative AI licences for internal staff drafting"}
    spanish = {"title": "Licencias de IA generativa para redacción de documentos internos"}
    assert activity_type_for(english)[0] == "internal_operational"
    assert activity_type_for(spanish)[0] == CANNOT_TYPE


def test_cannot_type_flag_never_reaches_contract_output():
    assert contract_uncertainty_flags([CANNOT_TYPE_FLAG]) == []


def test_activity_type_only_typed_for_relevant_records():
    """Typing an irrelevant record would be meaningless."""
    assert _classify("award_irrelevant").genai_category is None


def test_multi_lot_release_stages_one_record_per_award():
    """Ruling D6: never silently the first. Two awards, two staged records, each
    with its own supplier, value and lot."""
    records = extract_ocds(_raw("award_multi_lot"))
    assert len(records) == 2
    assert {r["lot_identifier"] for r in records} == {"lote-1", "lote-2"}
    assert {r["value_amount"] for r in records} == {210000, 64000}
    assert {r["supplier_name"] for r in records} == {
        "Alfa Integraciones SA (SYNTHETIC)", "Beta Servicios Digitales SL (SYNTHETIC)"}
    assert len({r["native_id"] for r in records}) == 2   # distinct record_ids downstream


def test_multi_lot_records_carry_every_supplier_for_the_downstream_collapse():
    """Ruling D6 interim rule: the collapse writes vendor=`multiple` and keeps
    the list, so staging has to carry the list."""
    records = extract_ocds(_raw("award_multi_lot"))
    names = records[0]["release_supplier_names"]
    assert len(names) == 2
    assert vendor_for(names) == "multiple"
    assert vendor_for(["Alfa Integraciones SA (SYNTHETIC)"]) == "Alfa Integraciones SA (SYNTHETIC)"
    assert vendor_for([]) is None


def test_review_queue_holds_the_unresolved_and_the_link_table_does_not(tmp_path):
    """Ruling Q5c: institution_link is for resolved uids only."""
    store = StagingStore(str(tmp_path / "staging"))
    store.upsert_review(InstitutionReview(
        record_id="r1", country_iso3="ESP",
        buyer_name_raw="Ayuntamiento de Ejemplo", status="open",
        opened_at="2026-08-04T10:00:00Z", reason="multiple_candidates",
        candidates=[{"institution_uid": "G3O-I-00012345", "match_score": 0.91}],
        master_build_id="mb-2026-07-30"))
    assert store.count("review") == 1
    with pytest.raises(ValidationError):
        store.upsert_link(InstitutionLink(
            record_id="r1", role="contracting_authority",
            match_method="unresolved", confidence="review_queue",
            institution_uid=None))
    store.close()


def test_link_rejects_a_uid_that_is_not_ledger_shaped(tmp_path):
    """The ledger mints G3O-I-00000000 form. A bare integer is master_row_id."""
    store = StagingStore(str(tmp_path / "staging"))
    for bad in ("719588", "G3O-I-123"):
        with pytest.raises(ValidationError):
            store.upsert_link(InstitutionLink(
                record_id="r1", role="contracting_authority",
                match_method="tier3_exact_name", confidence="auto_accepted",
                institution_uid=bad))
    store.close()


def test_link_can_record_a_followed_merge_chain(tmp_path):
    """Merges chain in the ledger; the audit trail keeps the uid we started from."""
    store = StagingStore(str(tmp_path / "staging"))
    store.upsert_link(InstitutionLink(
        record_id="r2", role="contracting_authority",
        match_method="tier1_domain", confidence="auto_accepted",
        institution_uid="G3O-I-00000002", resolved_from_uid="G3O-I-00000001",
        ledger_status="active", master_build_id="mb-2026-07-30", key_level=1))
    assert store.count("links") == 1
    store.close()


# --------------------------------------------------------------------------- #
# standardize + extension
# --------------------------------------------------------------------------- #

def test_standardize_fills_provenance_and_source_metadata():
    adapter = FixtureAdapter()
    raw = _raw("award_relevant")
    fields = extract_ocds(raw)[0]
    rec = standardize(adapter, raw, fields, NLPClassifier(QUERIES).classify(fields))
    assert rec.country_iso3 == "ZZZ"
    assert rec.record_id and rec.pipeline_version and rec.fetched_at
    assert rec.raw_payload_ref == raw.raw_payload_ref
    assert rec.review_status == ("pending" if rec.review_flags else "not_required")


def test_extension_holds_only_what_the_contract_cannot_and_never_the_verdict():
    adapter = FixtureAdapter()
    raw = _raw("award_relevant")
    fields = extract_ocds(raw)[0]
    ext = build_extension(adapter, raw, fields, NLPClassifier(QUERIES).classify(fields))
    assert ext.value_amount == 452300.5 and ext.value_currency == "EUR"
    assert ext.procedure_type == "open"
    assert not hasattr(ext, "genai_relevant")
    assert not hasattr(ext, "institution_uid")


def test_ungrounded_extension_fields_default_to_not_documented_never_null():
    adapter = FixtureAdapter()
    raw = _raw("award_relevant")
    fields = extract_ocds(raw)[0]
    ext = build_extension(adapter, raw, fields, NLPClassifier(QUERIES).classify(fields))
    # OCDS carries no contract text, so the §4.3 governance terms are unevidenced
    assert ext.ip_ownership == "not_documented"
    assert ext.human_oversight_requirement == "not_documented"
    assert ext.exit_lockin_provision is None
    assert ext.supplier_role == "unknown"


def test_record_id_is_stable_across_runs():
    adapter = FixtureAdapter()
    raw = _raw("award_relevant")
    fields = extract_ocds(raw)[0]
    clf = NLPClassifier(QUERIES).classify(fields)
    a = standardize(adapter, raw, fields, clf).record_id
    b = standardize(adapter, raw, fields, clf).record_id
    assert a == b
    assert build_extension(adapter, raw, fields, clf).record_id == a


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def test_store_rejects_a_positional_institution_id(tmp_path):
    """master_row_id is positional and moved 706247 -> 719588 across a rebuild.
    A link keyed on it would silently repoint at the wrong institution."""
    store = StagingStore(str(tmp_path / "staging"))
    link = InstitutionLink(record_id="abc", institution_uid="719588",
                           role="contracting_authority",
                           match_method="tier3_exact_name", confidence="review_queue",
                           )
    with pytest.raises(ValidationError, match="positional"):
        store.upsert_link(link)
    store.close()


def test_store_rejects_a_row_that_violates_its_schema(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    with pytest.raises(ValidationError):
        store._upsert("records", {"record_id": "x"})   # missing required fields
    store.close()


def test_store_enforces_json_schema_formats(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    raw = _raw("award_relevant")
    fields = extract_ocds(raw)[0]
    record = standardize(FixtureAdapter(), raw, fields, NLPClassifier(QUERIES).classify(fields))
    row = record.to_dict()
    row["fetched_at"] = "not-a-date"
    with pytest.raises(ValidationError, match="not a 'date-time'"):
        store._upsert("records", row)
    store.close()


def test_unverified_source_cannot_run_unbounded(tmp_path):
    config = tmp_path / "sources.yaml"
    config.write_text(
        "sources:\n"
        "  - source_id: fixture_unverified\n"
        "    access_mode: api\n"
        "    verification_status: unverified_snapshot\n",
        encoding="utf-8",
    )
    args = Namespace(
        limit=None,
        config=str(config),
        source_id="fixture_unverified",
        allow_unverified=True,
    )
    with pytest.raises(SystemExit, match="bounded smoke run"):
        cmd_run(args)


# --------------------------------------------------------------------------- #
# end-to-end staging-path small-sample smoke run
# --------------------------------------------------------------------------- #

def test_smoke_run_end_to_end(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    report = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store).run(strict=True)

    assert report.errors == []
    assert report.fetched == 3 and report.written == 3
    # every provisional candidate disposition is present
    assert (report.candidate_yes, report.candidate_unclear, report.candidate_no) == (1, 1, 1)

    assert store.count("records") == 3
    assert store.count("extensions") == 3

    csv_path = store.export_csv("records")
    per_source = store.export_per_source("fixture_ocds")
    assert csv_path.exists() and per_source.exists()
    assert len(per_source.read_text(encoding="utf-8").strip().splitlines()) == 4  # header + 3
    store.close()


def test_smoke_run_is_idempotent(tmp_path):
    """Re-running a source upserts on record_id; a re-run never duplicates."""
    store = StagingStore(str(tmp_path / "staging"))
    pipe = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store)
    pipe.run(strict=True)
    pipe.run(strict=True)
    assert store.count("records") == 3
    assert store.count("extensions") == 3
    store.close()


def test_limit_caps_the_run_for_the_small_sample_rule(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    report = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store).run(limit=2)
    assert report.fetched == 2 and store.count("records") == 2
    store.close()


def test_limit_does_not_pull_an_extra_payload_from_a_lazy_fetch(tmp_path):
    pulled = []

    class LazyAdapter(FixtureAdapter):
        def fetch(self, hits):
            for h in hits:
                pulled.append(h.native_id)
                yield _raw(h.native_id)

    store = StagingStore(str(tmp_path / "staging"))
    report = Pipeline(LazyAdapter(), QUERIES, NLPClassifier(QUERIES), store).run(limit=2)
    assert report.fetched == 2 and len(pulled) == 2
    store.close()


def test_stored_rows_round_trip_with_types_intact(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store).run(strict=True)
    # native_id is the source's own id — for OCDS, the ocid — not the file name.
    rows = {r["ocds_ocid"]: r for r in store.iter_rows("records")}
    assert rows["ocds-synthetic-0001"]["genai_relevant"] is True
    assert rows["ocds-synthetic-0003"]["genai_relevant"] is False
    exts = {r["ocds_ocid"]: r for r in store.iter_rows("extensions")}
    assert exts["ocds-synthetic-0001"]["value_amount"] == 452300.5
    store.close()


def _synthetic_index(rows=()):
    from pipeline.core.matcher import InstitutionIndex, LedgerEntry, MasterRow, normalize_name, registrable_domain
    master = [MasterRow(institution_uid=uid, country_iso3="ZZZ", government_level="national",
                        branch="bureaucratic", institution_type="ministry", institution_name=name,
                        website_domain=registrable_domain(""), normalized_name=normalize_name(name),
                        duplicate="", disambiguation="") for uid, name in rows]
    ledger = {uid: LedgerEntry(status="active", merged_into_uid="") for uid, _ in rows}
    return InstitutionIndex(master, ledger, "mb-test")


def test_matching_runs_on_every_record_and_keeps_unresolved_in_review(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    report = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store,
                      institution_index=_synthetic_index()).run(strict=True)
    assert report.sent_to_review == report.written == store.count("review")
    assert report.linked == store.count("links") == 0
    reviews = list(store.iter_rows("review"))
    assert {r["reason"] for r in reviews} == {"no_candidate"}
    assert all(r["master_build_id"] == "mb-test" and r["matcher_version"] for r in reviews)
    store.close()


def test_exact_name_match_is_linked_with_master_version(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    index = _synthetic_index([("G3O-I-00000001", "Ministerio de Administración Pública (SYNTHETIC)")])
    report = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store,
                      institution_index=index).run(strict=True)
    assert report.linked + report.sent_to_review == report.written
    links = list(store.iter_rows("links"))
    assert report.linked == len(links) >= 1
    assert all(l["institution_uid"] == "G3O-I-00000001" and l["master_build_id"] == "mb-test"
               for l in links)
    store.close()


def test_run_without_an_index_skips_matching(tmp_path):
    store = StagingStore(str(tmp_path / "staging"))
    report = Pipeline(FixtureAdapter(), QUERIES, NLPClassifier(QUERIES), store).run(strict=True)
    assert (report.linked, report.sent_to_review, store.count("links"), store.count("review")) == (0, 0, 0, 0)
    store.close()
