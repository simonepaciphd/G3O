"""Approved D-007 normalized storage boundary (local producer fixtures allowed).

The storage envelope is an explicit deterministic input alongside Stage 6, not
an addition to an LLM response schema. T-026/T-028 own runtime production; this
module refuses incomplete 2.7 envelopes and never upgrades historical rows.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from g3o.common.instrument import canonical_json, load_instrument, sha256_text, validate_instrument
from g3o.common.storage_fields import FIELDS

CHANNELS = ("web_extract", "procurement", "ai_text")
COMMON_COLUMNS = ["codebook_release", "setup_pointer", "evidence_channel", "item_support_json",
                  "coder_records_json", "field_availability_json"]
EXTRA_COLUMNS = {
    "activities": ["observation_ids_json", "activity_relations_json"],
    "sources": ["observation_ids_json", "page_artifact_path", "page_content_sha256",
                "contact_email_domain_counts_json"],
    "summary": [],
}
AVAILABILITY_REASONS = {"legacy_not_collected", "historical_provenance_unavailable", "coder_not_applicable"}
SUPPORT_STATES = {"supported", "downgraded_no_quote", "downgraded_low_confidence",
                  "downgraded_quote_not_stating_value", "set_by_rule", "not_required"}
METADATA_ITEMS = {"core.codebook_release", "core.setup_pointer", "core.evidence_channel"}
VERDICTS = tuple(FIELDS["core.page_verdict"]["codes"])


def table_fields(table: str) -> dict[str, dict[str, Any]]:
    return {key: field for key, field in FIELDS.items() if table in field["storage_targets"]}


def expanded_columns(table: str, legacy: list[str]) -> list[str]:
    return list(dict.fromkeys([*legacy, *COMMON_COLUMNS,
                              *(f["column_or_member"] for f in table_fields(table).values()),
                              *EXTRA_COLUMNS[table]]))


def legacy_row(table: str, base: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Preserve old values/encoding; explicitly mark unavailable additions.

    Metadata is evidence supplied by the caller, never inferred from a filename.
    A missing historical release remains NULL, not an invented v2.5 label.
    """
    from g3o.common.schema import ACTIVITY_COLUMNS, ACTIVITY_SOURCE_COLUMNS, SUMMARY_COLUMNS
    columns = {"activities": ACTIVITY_COLUMNS, "sources": ACTIVITY_SOURCE_COLUMNS,
               "summary": SUMMARY_COLUMNS}[table]
    metadata = metadata or {}
    release = metadata.get("codebook_release")
    if release not in (None, "v2.5"):
        raise ValueError("new-format rows require an explicit validated 2.7 storage envelope")
    channel = metadata.get("evidence_channel")
    if channel is not None and channel not in CHANNELS:
        raise ValueError("invalid historical evidence_channel")
    result = {column: base.get(column) for column in columns}
    reasons = {key: "legacy_not_collected" for key, f in table_fields(table).items()
               if base.get(f["column_or_member"]) is None}
    for name in ("codebook_release", "setup_pointer", "evidence_channel"):
        result[name] = metadata.get(name)
        if result[name] is None:
            reasons[f"core.{name}"] = "historical_provenance_unavailable"
        else:
            reasons.pop(f"core.{name}", None)
    for key in ("core.supporting_text", "core.support_status", "core.support_rule_name",
                "core.support_status_second_reason", "core.coder_record"):
        reasons[key] = "historical_provenance_unavailable"
    result["field_availability_json"] = canonical_json(reasons)
    return result


def _require_keys(value: Any, keys: set[str], label: str, *, exact: bool = True) -> None:
    if not isinstance(value, dict) or not keys <= value.keys() or (exact and set(value) != keys):
        raise ValueError(f"invalid {label} fields; required {sorted(keys)}")


def _string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")


def _strings(value: Any, label: str) -> None:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value) or len(set(value)) != len(value):
        raise ValueError(f"{label} must be an explicit list of unique identifiers")


def validate_value(item_id: str, value: Any, *, part: str | None = None) -> None:
    """Validate storage shape/codes, without choosing answers or applying coding rules."""
    canonical_json(value)
    field = FIELDS[item_id]
    missing = field["missing_tokens"] if isinstance(field["missing_tokens"], list) else []
    if value is None:
        raise ValueError(f"2.7 item {item_id} is unavailable; no generic default is permitted")
    if part is not None:
        if part not in field.get("parts", {}):
            raise ValueError(f"unknown part of {item_id}: {part}")
        if value not in field["parts"][part] + missing:
            raise ValueError(f"invalid part value for {item_id}")
        return
    if "parts" in field:
        _require_keys(value, set(field["parts"]), item_id)
        for name, val in value.items():
            validate_value(item_id, val, part=name)
        return
    if item_id in ("core.review_depth", "core.cx_display_rollup"):
        if not isinstance(value, dict):
            raise ValueError(f"{item_id} requires the named D-007 object shape")
        return
    if field["answer_type"] in ("list", "multi"):
        if isinstance(value, str) and value in missing:
            return
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            raise ValueError(f"{item_id} requires an array or signed missing token")
        if field["codes"] and any(v not in field["codes"] for v in value):
            raise ValueError(f"invalid list member for {item_id}")
        return
    if item_id == "core.n_sources":
        if type(value) is not int or value < 0:
            raise ValueError("n_sources must be an actual nonnegative claim count")
        return
    if not isinstance(value, str) or not value:
        raise ValueError(f"{item_id} requires its lexical text value")
    if field["codes"] and value not in field["codes"] + missing:
        raise ValueError(f"invalid code for {item_id}: {value!r}")
    if item_id in ("core.year_announced", "core.year_pilot_start", "core.year_production_start") and value not in missing and not re.fullmatch(r"\d{4}", value):
        raise ValueError(f"invalid year text for {item_id}")


def email_domain_counts(emails: list[str] | str) -> list[dict[str, Any]] | str:
    if isinstance(emails, str):
        validate_value("core.content_contact_emails", emails)
        return emails
    validate_value("core.content_contact_emails", emails)
    distinct: set[tuple[str, str]] = set()
    for email in emails:
        local, separator, domain = email.rpartition("@")
        if not separator or not local or not domain or any(c.isspace() for c in email):
            raise ValueError("email count input must contain extracted addresses")
        distinct.add((local, domain.lower()))  # local case and aliases deliberately retained
    counts = Counter(domain for _, domain in distinct)
    return [{"domain": domain, "count": counts[domain]} for domain in sorted(counts)]


def support_id(run_id: str, institution_uid: str, record: dict[str, Any]) -> str:
    keys = ("item_id", "item_part", "value_json", "observation_id", "source_id", "chunk_id",
            "support_text_sha256", "passage")
    return sha256_text(canonical_json([run_id, institution_uid, *[record[k] for k in keys]]))


class StorageEnvelope:
    """Fully validated local handoff; no automatic research or provenance repair."""

    def __init__(self, data: dict[str, Any], instrument: dict[str, Any], *, artifact_root: Path):
        self._data = deepcopy(data)
        _require_keys(self._data, {"format", "run_id", "institution_uid", "institution_id",
                                "codebook_release", "setup_pointer", "evidence_channel",
                                "activities", "sources", "summary"}, "storage envelope")
        if self._data["format"] != "g3o-storage-v1" or self._data["codebook_release"] != "2.7":
            raise ValueError("unsupported storage envelope/release")
        if self._data["evidence_channel"] not in CHANNELS:
            raise ValueError("invalid canonical evidence channel")
        for key in ("run_id", "institution_uid", "institution_id"):
            _string(self._data[key], key)
        self._instrument = validate_instrument(instrument, expected_id=self._data["setup_pointer"])["payload"]
        self.artifact_root = artifact_root
        self.supports: dict[str, dict[str, Any]] = {}
        self.pages: dict[str, tuple[Any, ...]] = {}
        self.observation_sources: dict[str, set[str]] = defaultdict(set)
        for table in ("activities", "sources"):
            if not isinstance(self._data[table], dict):
                raise ValueError(f"{table} must be keyed by existing row identifiers")
            for key, row in self._data[table].items():
                _string(key, "row key")
                self._validate_row(table, row, key)
        self._validate_row("summary", self._data["summary"])
        self._validate_links()

    @property
    def data(self) -> dict[str, Any]:
        """A detached view: a caller cannot mutate already validated storage."""
        return deepcopy(self._data)

    @classmethod
    def load(cls, path: Path, instrument_directory: Path, *, artifact_root: Path) -> StorageEnvelope:
        data = json.loads(path.read_text(encoding="utf-8"))
        record = load_instrument(instrument_directory, data.get("setup_pointer"))
        return cls(data, record, artifact_root=artifact_root)

    def _validate_row(self, table: str, row: dict[str, Any], row_key: str | None = None) -> None:
        keys = {"values", "item_support", "coder_records"}
        if table != "summary":
            keys.add("observation_ids")
        if table == "activities":
            keys.add("activity_relations")
        if table == "sources":
            keys |= {"activity_id", "page_artifact_path", "page_content_sha256"}
        _require_keys(row, keys, f"{table} row")
        expected = set(table_fields(table)) - METADATA_ITEMS
        _require_keys(row["values"], expected, f"{table} questionnaire values")
        for item_id, value in row["values"].items():
            validate_value(item_id, value)
        if table != "summary":
            _strings(row["observation_ids"], "observation_ids")
            if not row["observation_ids"]:
                raise ValueError("2.7 source/activity rows must retain original observations")
        if table == "sources":
            path = Path(row["page_artifact_path"])
            if not path.is_absolute():
                path = self.artifact_root / path
            raw_text = path.read_bytes().decode("utf-8")
            if sha256_text(raw_text) != row["page_content_sha256"]:
                raise ValueError("actual page artifact hash mismatch")
            row["_page_text"] = raw_text
            row["_page_path"] = str(path.resolve())
        if not isinstance(row["item_support"], list) or not isinstance(row["coder_records"], list):
            raise ValueError("item_support and coder_records must be explicit arrays")
        if len({s["support_id"] for s in row["item_support"]}) != len(row["item_support"]):
            raise ValueError("duplicate support identity in one row")
        for record in row["item_support"]:
            self._validate_support(record)
            if table == "sources" and record["source_id"] is not None and record["source_id"] != row_key:
                raise ValueError("source claim borrowed another claim's support")
            if table == "activities" and record["observation_id"] is not None and record["observation_id"] not in row["observation_ids"]:
                raise ValueError("activity borrowed another observation's support")
        for record in row["coder_records"]:
            self._validate_coder(record)
        # Per-value/part records cannot be replaced by an unkeyed last-page quote.
        for item, value in row["values"].items():
            field = FIELDS[item]
            if field["coder"] not in {"classifier", "quote_step"}:
                continue
            pairs = list(value.items()) if "parts" in field else [(None, v) for v in value] if isinstance(value, list) else [(None, value)]
            for part, selected in pairs:
                if not any(s["item_id"] == item and s["item_part"] == part and s["value_json"] == selected for s in row["item_support"]):
                    raise ValueError(f"missing keyed support record for {item}/{part}")

    def _validate_support(self, record: dict[str, Any]) -> None:
        keys = {"support_id", "item_id", "item_part", "value_json", "observation_id",
                "source_id", "chunk_id", "supporting_text", "support_status", "support_rule_name",
                "support_status_second_reason", "uncertainty_flags", "input_support_ids",
                "support_text_sha256", "page_content_sha256", "passage"}
        _require_keys(record, keys, "support record", exact=False)
        if set(record) - keys - {"date_target"}:
            raise ValueError("unknown support fields")
        item = record["item_id"]
        if item not in FIELDS or FIELDS[item]["state"] in {"excluded", "external_owner_pending"}:
            raise ValueError("support references a non-runtime item")
        value = record["value_json"]
        if FIELDS[item]["answer_type"] in ("list", "multi") and isinstance(value, str) and value not in FIELDS[item]["missing_tokens"]:
            validate_value(item, [value])
        else:
            validate_value(item, value, part=record["item_part"])
        if record["support_status"] not in SUPPORT_STATES:
            raise ValueError("unknown signed support status")
        if not isinstance(record["supporting_text"], str) or sha256_text(record["supporting_text"]) != record["support_text_sha256"]:
            raise ValueError("support quote hash mismatch")
        if value in ("not_asked", "_NA_") and record["support_status"] != "set_by_rule":
            raise ValueError("rule-skipped values must retain set_by_rule support provenance")
        if record["support_status"] == "supported" and not record["supporting_text"]:
            raise ValueError("supported value has no quote")
        if record["support_status"] == "set_by_rule":
            _string(record["support_rule_name"], "actual support rule")
        if item == "core.date_upper_bound":
            _string(record.get("date_target"), "date target")
        validate_value("core.support_status_second_reason", record["support_status_second_reason"])
        validate_value("core.uncertainty_flags", record["uncertainty_flags"])
        _strings(record["input_support_ids"], "input_support_ids")
        if not isinstance(record["passage"], dict) or not record["passage"]:
            raise ValueError("an explicit passage/span discriminator is required")
        expected = support_id(self._data["run_id"], self._data["institution_uid"], record)
        if record["support_id"] != expected:
            raise ValueError("support identity does not match complete support key")
        if expected in self.supports and self.supports[expected] != record:
            raise ValueError("conflicting records reuse a support identity")
        self.supports[expected] = record

    def _validate_coder(self, record: dict[str, Any]) -> None:
        keys = {"support_id", "observation_id", "item_id", "item_part", "coder_type", "coder_version",
                "configured_model", "actual_response_model", "request_id", "question_set_version",
                "chunk_id", "chosen_value", "chosen_answer_probability", "probability_distribution"}
        _require_keys(record, keys, "coder record", exact=False)
        if set(record) - keys - {"field_availability", "support_entailment"}:
            raise ValueError("unknown coder fields")
        if record["item_id"] not in FIELDS:
            raise ValueError("unknown coder item")
        _string(record["coder_version"], "coder_version")
        _string(record["question_set_version"], "question_set_version")
        allowed_coder = FIELDS[record["item_id"]]["coder"]
        if record["coder_type"] not in {allowed_coder, "mechanical"}:
            raise ValueError("coder_type does not match the signed item coder")
        if record["coder_type"] in {"mechanical", "derived"}:
            unavailable = record.get("field_availability", {})
            for key in ("configured_model", "actual_response_model", "request_id", "chosen_answer_probability", "probability_distribution"):
                if record[key] is not None or unavailable.get(key) != "coder_not_applicable":
                    raise ValueError("mechanical coder must use typed null with coder_not_applicable")
        else:
            for key in ("configured_model", "actual_response_model", "request_id"):
                _string(record[key], key)
            expected_model = self._instrument["configured_jev_model"] if record["coder_type"] == "classifier" else self._instrument["extractor_model_id"]
            if record["configured_model"] != expected_model or record["question_set_version"] != self._instrument["question_set_version"]:
                raise ValueError("coder configuration does not match the actual instrument")
            p = record["chosen_answer_probability"]
            if p is not None and (type(p) not in (int, float) or not 0 <= p <= 1):
                raise ValueError("invalid chosen-answer probability")
            dist = record["probability_distribution"]
            if dist is not None and (not isinstance(dist, dict) or any(type(p) not in (int, float) or not 0 <= p <= 1 for p in dist.values())):
                raise ValueError("invalid probability distribution")
        canonical_json(record)  # preserves missing probabilities; never fills them

    def _validate_links(self) -> None:
        activities, sources = self._data["activities"], self._data["sources"]
        observation_activities: dict[str, set[str]] = defaultdict(set)
        relation_pairs: dict[tuple[str, str, str], str] = {}
        relation_identity: dict[str, dict[str, Any]] = {}
        for aid, row in activities.items():
            for oid in row["observation_ids"]:
                observation_activities[oid].add(aid)
        for sid, row in sources.items():
            if row["activity_id"] != "_NA_" and row["activity_id"] not in activities:
                raise ValueError("source activity endpoint does not resolve")
            for oid in row["observation_ids"]:
                self.observation_sources[oid].add(sid)
                if row["activity_id"] != "_NA_" and row["activity_id"] not in observation_activities.get(oid, set()):
                    raise ValueError("source observation is absent from its final activity")
            self.pages[sid] = (row["_page_path"], row["values"]["core.source_url"],
                               row["values"]["core.source_access_date"], row["page_content_sha256"])
        for aid, row in activities.items():
            actual = sum(source["activity_id"] == aid for source in sources.values())
            if row["values"]["core.n_sources"] != actual:
                raise ValueError("n_sources must count evidence claims, not URLs")
            for oid in row["observation_ids"]:
                if oid not in self.observation_sources:
                    raise ValueError("activity observation has no source claim")
            if not isinstance(row["activity_relations"], list):
                raise ValueError("activity_relations must be an explicit array")
            relation_ids: set[str] = set()
            for rel in row["activity_relations"]:
                _require_keys(rel, {"relation_id", "lhs_observation_id", "rhs_observation_id", "relation",
                                    "source_refs", "support_ids", "lhs_final_activity_id", "rhs_final_activity_id",
                                    "relation_scope"}, "relation")
                if rel["relation_id"] in relation_ids:
                    raise ValueError("duplicate relation identity")
                relation_ids.add(rel["relation_id"])
                prior = relation_identity.get(rel["relation_id"])
                if prior is not None and prior != rel:
                    raise ValueError("relation identity reused for different endpoints/evidence")
                relation_identity[rel["relation_id"]] = rel
                if rel["relation_scope"] not in {"within_page", "cross_page"}:
                    raise ValueError("invalid relation scope")
                item = "core.activity_segment" if rel["relation_scope"] == "within_page" else "core.activity_relation_cross_page"
                validate_value(item, rel["relation"])
                pair = (rel["relation_scope"], rel["lhs_observation_id"], rel["rhs_observation_id"])
                if pair in relation_pairs and relation_pairs[pair] != rel["relation"]:
                    raise ValueError("multiple conflicting relations for the same pair")
                relation_pairs[pair] = rel["relation"]
                for side in ("lhs", "rhs"):
                    oid = rel[f"{side}_observation_id"]
                    final = rel[f"{side}_final_activity_id"]
                    if final not in observation_activities.get(oid, set()):
                        raise ValueError("original relation endpoint/final mapping does not resolve")
                if rel["relation"] in {"distinct_action", "unresolved"} and rel["lhs_final_activity_id"] == rel["rhs_final_activity_id"]:
                    raise ValueError("distinct/unresolved observations must not be merged")
                if any(s not in sources for s in rel["source_refs"]) or any(s not in self.supports for s in rel["support_ids"]):
                    raise ValueError("relation evidence endpoint does not resolve")
                if rel["relation_scope"] == "within_page":
                    left = {self.pages[s] for s in self.observation_sources[rel["lhs_observation_id"]]}
                    right = {self.pages[s] for s in self.observation_sources[rel["rhs_observation_id"]]}
                    if not left & right:
                        raise ValueError("within-page endpoints have no actual page in common")
            rollup = row["values"]["core.cx_display_rollup"]
            for item, result in rollup.items():
                if item not in FIELDS:
                    raise ValueError("unknown display rollup item")
                _require_keys(result, {"value", "input_support_ids", "source_ids", "observation_ids", "combining_rule_ref"}, "display rollup")
                validate_value(item, result["value"])
                _string(result["combining_rule_ref"], "combining rule")
                if any(s not in self.supports for s in result["input_support_ids"]) or any(s not in sources for s in result["source_ids"]) or any(o not in self.observation_sources for o in result["observation_ids"]):
                    raise ValueError("display rollup input does not resolve")
        inverse = {"component_of_program": "has_component", "has_component": "component_of_program",
                   "governs": "governed_by", "governed_by": "governs"}
        for (scope, lhs, rhs), value in relation_pairs.items():
            other = relation_pairs.get((scope, rhs, lhs))
            if other is not None and other != inverse.get(value, value):
                raise ValueError("supplied inverse relations disagree")
        for record in self.supports.values():
            if any(key not in self.supports for key in record["input_support_ids"]):
                raise ValueError("combined support input does not resolve")
            sid, oid = record["source_id"], record["observation_id"]
            if sid is not None:
                if sid not in sources or oid not in sources[sid]["observation_ids"]:
                    raise ValueError("support source/observation endpoint does not resolve")
                source = sources[sid]
                if record["page_content_sha256"] != source["page_content_sha256"]:
                    raise ValueError("support is bound to a different page artifact")
                if record["supporting_text"] and record["supporting_text"] not in source["_page_text"]:
                    raise ValueError("support text is not verbatim in its actual page")
                passage = record["passage"]
                if "start" in passage or "end" in passage:
                    if set(passage) != {"start", "end"} or type(passage["start"]) is not int or type(passage["end"]) is not int or not 0 <= passage["start"] <= passage["end"] <= len(source["_page_text"]):
                        raise ValueError("invalid support passage span")
                    if source["_page_text"][passage["start"]:passage["end"]] != record["supporting_text"]:
                        raise ValueError("support passage span does not identify its quote")
            elif oid is not None and oid not in self.observation_sources:
                raise ValueError("pooled support observation does not resolve")
        for table in ("activities", "sources", "summary"):
            rows = [self._data[table]] if table == "summary" else self._data[table].values()
            for row in rows:
                for coder in row["coder_records"]:
                    if coder["support_id"] not in self.supports or (coder["observation_id"] is not None and coder["observation_id"] not in self.observation_sources):
                        raise ValueError("coder provenance endpoint does not resolve")
                    support = self.supports[coder["support_id"]]
                    if (coder["item_id"], coder["item_part"], coder["chosen_value"], coder["observation_id"], coder["chunk_id"]) != (support["item_id"], support["item_part"], support["value_json"], support["observation_id"], support["chunk_id"]):
                        raise ValueError("coder provenance does not match its support key")
                    expected = "mechanical" if support["support_status"] == "set_by_rule" else FIELDS[support["item_id"]]["coder"]
                    if coder["coder_type"] != expected:
                        raise ValueError("coder type does not match the actual rule/provider context")
                for support in row["item_support"]:
                    if FIELDS[support["item_id"]]["coder"] in {"classifier", "quote_step"} and not any(c["support_id"] == support["support_id"] for c in row["coder_records"]):
                        raise ValueError("missing per-code coder provenance")
        def origins(sid: str, trail: frozenset[str] = frozenset()) -> set[tuple[str | None, str | None]]:
            if sid in trail:
                raise ValueError("cyclic pooled support provenance")
            support = self.supports[sid]
            result = set()
            if support["observation_id"] is not None or support["source_id"] is not None:
                result.add((support["observation_id"], support["source_id"]))
            for prior in support["input_support_ids"]:
                result.update(origins(prior, trail | {sid}))
            return result
        # Traverse every record, including summary-only pooled provenance.
        for sid, support in self.supports.items():
            evidence = origins(sid)
            if support["source_id"] is None and support["supporting_text"]:
                if not any(source_id in sources and support["supporting_text"] in sources[source_id]["_page_text"] for _, source_id in evidence):
                    raise ValueError("pooled support quote is not verbatim in an input page")
        for table in ("activities", "sources"):
            for key, row in self._data[table].items():
                for support in row["item_support"]:
                    evidence = origins(support["support_id"])
                    if not evidence:
                        raise ValueError("row support has no contextual observation or explicit pooled inputs")
                    if table == "sources" and any(sid != key for _, sid in evidence):
                        raise ValueError("source claim borrowed another claim's pooled support")
                    if table == "activities" and any(oid not in row["observation_ids"] for oid, _ in evidence):
                        raise ValueError("activity borrowed another observation's pooled support")
        self._validate_review_depth()

    def _validate_review_depth(self) -> None:
        depth = self._data["summary"]["values"]["core.review_depth"]
        if set(depth) - set(CHANNELS) or self._data["evidence_channel"] not in depth:
            raise ValueError("review_depth must include the active evidence channel")
        for channel, counts in depth.items():
            _require_keys(counts, {"n_pages_reviewed", "n_pages_by_verdict", "n_pages_failed", "n_followed_links"}, "review depth")
            if set(counts["n_pages_by_verdict"]) != set(VERDICTS):
                raise ValueError("review_depth must contain all nine verdict counts")
            numeric = [counts[k] for k in ("n_pages_reviewed", "n_pages_failed", "n_followed_links")]
            numeric += list(counts["n_pages_by_verdict"].values())
            if any(type(v) is not int or v < 0 for v in numeric):
                raise ValueError("page counts must be actual nonnegative integers")
            if sum(counts["n_pages_by_verdict"].values()) != counts["n_pages_reviewed"]:
                raise ValueError("page verdict counts do not sum to reviewed pages")
            if channel == self._data["evidence_channel"]:
                unique: dict[tuple[Any, ...], str] = {}
                for sid, page in self.pages.items():
                    verdict = self._data["sources"][sid]["values"]["core.page_verdict"]
                    if page in unique and unique[page] != verdict:
                        raise ValueError("same actual page has conflicting page verdicts")
                    unique[page] = verdict
                observed = Counter(unique.values())
                if any(observed[v] != counts["n_pages_by_verdict"][v] for v in VERDICTS) or len(unique) != counts["n_pages_reviewed"]:
                    raise ValueError("review_depth must exactly count actual reviewed page artifacts")
            elif counts["n_pages_reviewed"] or counts["n_pages_failed"] or counts["n_followed_links"]:
                raise ValueError("review_depth has counts for a channel without evidenced inputs")

    def row(self, table: str, key: str | None, base: dict[str, Any], *, run_id: str, institution_uid: str) -> dict[str, Any]:
        if run_id != self._data["run_id"] or institution_uid != self._data["institution_uid"] or base["institution_id"] != self._data["institution_id"]:
            raise ValueError("storage envelope institution/run binding mismatch")
        source = self._data[table] if table == "summary" else self._data[table][key]
        result = legacy_row(table, base)
        for item, value in source["values"].items():
            field = FIELDS[item]
            result[field["column_or_member"]] = canonical_json(value) if isinstance(value, (dict, list)) or field["answer_type"] in ("list", "multi") else value
        for name in ("codebook_release", "setup_pointer", "evidence_channel"):
            result[name] = self._data[name]
        result["item_support_json"] = canonical_json(source["item_support"])
        result["coder_records_json"] = canonical_json(source["coder_records"])
        result["field_availability_json"] = "{}"
        if table != "summary":
            result["observation_ids_json"] = canonical_json(source["observation_ids"])
        if table == "activities":
            result["activity_relations_json"] = canonical_json(source["activity_relations"])
        if table == "sources":
            if base["source_url"] != source["values"]["core.source_url"]:
                raise ValueError("source URL identity differs between storage and consolidated claim")
            if base["activity_id"] != source["activity_id"]:
                raise ValueError("source claim activity binding mismatch")
            result["page_artifact_path"] = source["page_artifact_path"]
            result["page_content_sha256"] = source["page_content_sha256"]
            result["genai_evidence"] = source["values"]["core.page_verdict"]
            result["contact_email_domain_counts_json"] = canonical_json(email_domain_counts(source["values"]["core.content_contact_emails"]))
        return result


def public_projection(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Privacy projection only; PI-release/public-activity gates remain downstream."""
    result = dict(row)
    for column in ("coder_records_json", "page_artifact_path", "content_contact_emails_json"):
        result.pop(column, None)
    for field in table_fields(table).values():
        if field["visibility"] == "internal":
            result.pop(field["column_or_member"], None)
    if result.get("cx_display_rollup"):
        rollup = json.loads(result["cx_display_rollup"])
        result["cx_display_rollup"] = canonical_json({item: value for item, value in rollup.items()
                                                       if FIELDS[item]["visibility"] == "public"})
    if result.get("field_availability_json"):
        reasons = json.loads(result["field_availability_json"])
        result["field_availability_json"] = canonical_json({item: reason for item, reason in reasons.items()
                                                            if FIELDS[item]["visibility"] != "internal"})
    if result.get("item_support_json"):
        supports = json.loads(result["item_support_json"])
        result["item_support_json"] = canonical_json([s for s in supports if FIELDS[s["item_id"]]["visibility"] == "public"])
    return result