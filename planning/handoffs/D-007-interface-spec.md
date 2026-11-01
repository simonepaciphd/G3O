# D-007 storage and publication interface — approved contract v1.0

Status: PI-APPROVED for local implementation (S1 a, S2 a, P1 a, P2 approve); not sent, not accepted by Colin. Approval: 2026-11-01T15:38:55.942Z; exact page SHA256 d9ca34714331b5a565a3f30ca56a34dccc2ceb8a74ebf39ac37889d2d4a29977; reply in ../archive/records/g3o-storage-continuation-20261101.reply.json. Reviewed preimage retained in ../archive/2026-11-01-before-d007-approval/.
Integrator: 20261101-codex-v2-c10efbad5812817d, researcher, 2026-11-01.
Sources: SPEC v001.11 plus approved RC-D-007/009; r11 SHA256 f948fe0b2a36448db57b70b195567ffc39fb024efb986f9b0025581cee181e0d; ENUM 87ac525; LABELS 34f6407.
Mapping: D-007-field-map.json beside this file. Its 120 entries account for every codebook item: 108 runtime-mapped, one signed release-2.7 language slot deferred to its external owner, and 11 outside-release placeholders explicitly excluded. It is the approved storage mapping, not a new coding rule.

## 1. Existing grains and compatibility

Keep the existing filenames and key columns:
- g3o_activities_v{N}.csv: institution_uid, run_id, activity_id; current 37 columns.
- g3o_activity_sources_v{N}.csv: institution_uid, run_id, source_id; current 20 columns. A source is an evidence claim (page × activity), not a unique physical page. One page about two activities has two S-ids with distinct A-ids. An absence source retains its existing _NA_ activity marker.
- g3o_institution_summary_v{N}.csv: institution_uid, run_id; current 22 columns.

Keep existing column order and append the additions in the field map; do not remove legacy columns. Preserve source_id uniqueness under the existing loader key. Do not change n_sources into a count of URLs. Same URL fetched at different times does not prove same page content. Add internal-only page_artifact_path and public page_content_sha256 from the actual consumed text artifact; no inferred fetch dates or invented original-run stamps. Cross-run identity continues to include run_id. Public projections never expose local artifact paths; use source URL/public identity and content hash. Define page identity by the actual consumed artifact plus source identity/fetch provenance, not content hash alone (two distinct pages may have identical text).

All three tables append codebook_release, setup_pointer, evidence_channel, item_support_json, coder_records_json and field_availability_json. core.date_upper_bound is retained at both signed source and activity contexts, with its date target identified in support/provenance records; no activity context is dropped. The externally owned core.language_coverage slot is explicitly deferred to its owner, not invented as an executable column. Item-specific columns follow the exact order of the signed codebook map (existing columns reused rather than duplicated). Sources also append observation_ids_json, page_artifact_path, page_content_sha256. Activities append observation_ids_json and activity_relations_json. These names and encodings are approved by P2.

There is no silent promotion of old data. v2.5 remains v2.5 only when actual run metadata proves that label. New 2.7 rows require valid instrument provenance. Unknown historical metadata must not be guessed from filenames, run dates or current software.

## 2. Field mapping and serialization

Each map entry lists item ID, codebook name, signed level(s), answer type, visibility, target table/column or nested record and permitted values derived from the codebook. The data dictionary owns definitions. The map does not redefine questionnaire values.

Page/source items go to evidence-claim rows; page-level values may repeat on claims from the same actual page. The seven evaluation fields (evaluation_documented and its six type flags) belong to each finding × page claim. They are not scalar activity fields. An activity-level display rollup remains a distinct derived item under its signed combining rule, retaining its input claim identities.

Activity items go to activity rows only after the applicable signed consolidation. Per-page observations and the supporting evidence remain retrievable. Institution items go to summary rows. The mapping's row-level items live in each table's metadata or per-item records. Multipart attribution is one JSON object column observed_actor_relationship, with relationship and searched_institution_role; observed_actor_role remains internal. It is not two independent public columns.

Wire rules:
- CSV is UTF-8, RFC4180 quoting; SQL strings are text, structured values jsonb.
- Questionnaire codes and dates are text, preserving signed missing tokens and lexical values. Multi/list fields use a JSON value union: array for collected values, a JSON string for a signed missing token, null only for explicitly unavailable storage data under S1. Structured records use JSON objects/arrays. Legacy v2.5 cells retain their existing wire encoding; the release label selects the decoder, so no old delimiter-encoded column is silently reinterpreted. No delimiter splitting on semicolons inside quotes or list values.
- JSON objects use deterministic sorted keys, no NaN/Infinity; arrays preserve meaningful signed order. Serialization is lossless, without normalization of quote text.
- A genuine measured count may be a nonnegative integer. A scale number copied by the quote step retains its original string, not an inferred numeric value.
- Blank CSV cells mean SQL NULL only for an explicitly allowed unavailable/not-applicable storage field. They never stand for empty arrays, zero, not_asked, not_documented or unknown.
- field_availability_json is an object keyed by item ID. Approved reason strings are legacy_not_collected, historical_provenance_unavailable and coder_not_applicable. These describe storage/provenance only and are not questionnaire response codes. S1a permits explicitly incomplete historical provenance in legacy exports, retaining only version facts supported by actual metadata. Incomplete new-release rows are rejected.
- New 2.7 rows reject absent required fields, invalid codes or incomplete provenance. A rule-skipped question uses its signed token and records the rule; it is never repaired by a generic default.

Full extracted email addresses stay internal. S2a publishes contact_email_domain_counts_json as an array of {domain,count} objects counting distinct extracted address strings per actual page after lowercasing only the domain. Preserve local-part case; make no alias or plus-address assumptions. Repeat appearances do not increase the count. No zero is emitted merely because extraction did not run. Published verbatim quotes retain the separate R-058 rule.

### Named rollup records

review_depth is a JSON object with one entry per evidence channel. Each channel has n_pages_reviewed, n_pages_by_verdict (all nine signed verdict keys), n_pages_failed and n_followed_links. Counts refer to actual reviewed page artifacts, not repeated page/activity claims. Deduplicate repeated claims by actual page identity before counting; do not collapse separately fetched distinct pages just because the text hashes match. Count a page once in its actual channel. Failed/unassessable distinctions follow signed rules; no new page-verdict assignment is inferred. The old 8-count annotation is superseded by SPEC's approved nine-value count requirement.

cx_display_rollup is an object keyed by item_id. Each member is {value, input_support_ids, source_ids, observation_ids, combining_rule_ref}; value preserves the item's signed scalar/list/missing form, and references identify all inputs actually used. The signed combining rule decides the value; storage does not invent a new aggregation rule.

## 3. Per-item support and coder provenance

item_support_json is an array of records:
- support_id: deterministic opaque identifier scoped to run/institution and its complete support key, including passage text hash and span/occurrence discriminator;
- item_id, item_part (null for single-part), value_json (the exact supported scalar or selected list member);
- observation_id, source_id, chunk_id; null permitted only where the actual coding context has no such dimension;
- supporting_text: full verbatim text;
- support_status, support_rule_name, support_status_second_reason: exact signed values/text;
- uncertainty_flags: exact signed list/missing-value union, scoped to this observation/code;
- input_support_ids: ordered links for a combined/mapped value, not a replacement fabricated quote;
- support_text_sha256 and page_content_sha256 computed from actual text artifacts.

The logical key includes item, part, value, observation, source, chunk and passage/span discriminator; multiple supporting passages get separate records. Do not overwrite one activity's supports with the last page. Rule-set values retain their rule reference and signed set-by-rule status; no fake quote. For institution/pooled results, provenance can name multiple input support records. Public projections exclude supports for internal-only items. Unmasked published quotes are retained under R-058, including when they incidentally contain email text; the separate extracted-email fields remain restricted.

coder_records_json is internal. Records reference support/observation/item/part and carry coder_type, coder_version, configured_model, actual_response_model, request_id, question_set_version, chunk_id, chosen_value, chosen_answer_probability and probability_distribution. Preserve the full distribution internally; the public API does not serve it. Setup configuration is not proof of a response model or request ID.
- Classifier probabilities missing from a provider response remain missing. No 0, 1, inferred distribution or generic confidence is substituted.
- Mechanical coders have no provider model/request by construction: typed null plus coder_not_applicable, with actual rule/version instead of fabricated IDs.
- T-027 must bring any missing-probability policy to the PI before implementation. This document does not decide its downstream confidence or publication treatment.
- Code values, support states and confidence are separate facts. The 0.8 chosen-answer bar and signed page-downgrade rule are unchanged.

## 4. Pairwise relations and observations

activity_relations_json contains relation_id, lhs_observation_id, rhs_observation_id, relation, source_refs, support_ids, lhs_final_activity_id and rhs_final_activity_id. Endpoints are the original pre-consolidation observations, not only final A-ids: same_activity/shared_participation can merge two endpoints into one final activity. All endpoint references must resolve within the institution/run unless a separately authorized transfer explicitly supplies cross-run provenance. relation_scope is within_page or cross_page; core.activity_segment (name activity_relation_within_page) uses the within_page form. Preserve direction and the signed priority when more than one link fits. Never merge distinct/unresolved pairs. Inverse relations are validated, not invented.

Each final source claim carries observation_ids_json, preserving every original observation that fed it; final S-ids are not substituted for pre-consolidation observation IDs. An observation ID is created by the deterministic pipeline from existing run/institution/source claim/activity-span identities. It is not an external institutional identity and never creates search rows. T-022/T-023 produce per-page observation references; T-026 retains and maps them when consolidating; T-028 validates endpoint closure. Q2a accepts explicit fixture observations now; it does not pretend current Stage6 already retains all internally coded activities.

## 5. Instrument record and producer ownership

setup_pointer references instrument_id in a real immutable instrument record. Approved path: final/instruments/<instrument_id>.json; instrument_id is sha256 of the payload only, serialized as UTF-8 JSON with sorted keys, separators comma/colon, ensure_ascii=false, no trailing newline and no NaN/Infinity; the payload excludes instrument_id. The outer record is {instrument_id,payload}; a separate record_sha256 verifies its exact stored bytes. Do not confuse the payload ID with the record byte hash; no setup-<run_id> placeholders.

Required setup payload: schema version; codebook release and exact SHA256; codebook item hashes; extract/validate contract labels; question-set version and generated question/prompt hashes; configured jev model; extractor model ID, prompt SHA256 and actual configuration; chunker/estimator version and token budget; matcher library/version and PI-approved threshold; chosen-answer confidence threshold; producer code revision; actual signed instrument approval reference. All are supplied from the executed configuration/approved artifacts, not current defaults. Credentials and secrets never enter this record. The record must be finalized only when all actual required settings exist.

Approved owner remap:
- T-012: g3o/common/instrument.py and matching tests; builder/validator plus Stage7 lookup/refusal; explicit representative fixture setup records. Record creation is deterministic local work. No provider call.
- T-030: runtime binding from actual planning/run configuration into the builder, before any 2.7 row can be emitted. Assign the instrument-binding hunks of g3o/run/presweep/planning.py and relevant run-manifest path after touchpoint verification.
- T-035: CLI/backfill/transfer runtime binding and final pins, in its existing sole CLI ownership.
- T-027: per-code response provenance, distinct from setup provenance.
- T-028: end-to-end writer checks against actual upstream outputs; T-051/052: storage, loader and capability guard.

Historical runs lack the instrument record. Decision S1 governs their explicit absent storage/provenance fields; no retrospective certification. Unknown configured models must not be populated from today's model names.

## 6. Publication, correction layer and consumer gates

Unchanged approved requirements:
- Every 2.7 row is hidden until PI release, including ordinary runs. Correction/backfill rows are wave-free; ordinary runs retain wave windows.
- Corrections link original observation IDs and preserve original values/stamps/evidence. Reject reuse of an original run_id for a correction release.
- Default API shows the most recent eligible institution row; history exposes older labelled rows. v2.5 latest rows hide new fields; old none is displayed as no with its v2.5 verdict_rule.
- Only activities on confirms_activity pages are public/count toward tier. Other permitted internal activity observations remain internal. Published summary unresolved/not_assessable become unknown; raw coding values stay internal.
- Full supporting text in API/CSV; website cap remains PI-set, with access to full text. Display-only translation does not replace stored text.
- Generated dictionary is the API README's definition source. The two-way translation and legacy-column mapping remain the signed rules; unmappable cells stay explicit.
- Colin owns migrations, projection views, v_wave_* and materialized aggregates, explicit refresh and watermark checks, API/site/history, bulk export and its README link. One draft issue per T-051/T-052/T-053, external posting only after PI instruction.
- Indices stay withheld.

The existing API loader enumerates old maps and ignores added CSV columns. Q2a cannot be sent to that loader as successful 2.7 ingestion. T-052 must reject unsupported codebook/interface versions before any DML, then accept only after required mapping/capability checks. No DB, staging or production write is authorized by this approval.

## 7. Approved dependency remap (decision P1a)

T-050A is a contract milestone within existing T-050, not a newly launched lane: requires signed T-010/T-013 and T-012's accepted inventory; produces the PI-reviewed field map and instrument protocol. It does not require built T-012 or T-027.
T-012 then completes Q2a locally against T-050A and explicit fixtures; the moved writer subset includes normalized columns, lossless serialization, provenance validation/refusal and regression tests. It does not claim pipeline/API/DB readiness.
T-027 starts only after T-012 is proposed verified (E4). Missing-probability policy returns to PI first.
T-050B requires T-012 + T-027, verifies the implemented contracts, and obtains PI send approval plus Colin acceptance (A-019).
T-028 retains T-015/T-024/T-026/T-027 + T-050B, integrated outputs and remaining writer/integrity work; it begins after T-012 releases the shared writer claim.
T-051/T-052/T-053 keep consumer acceptance, publication and DB/deployment gates.
T-030/T-035 own runtime instrument wiring; they cannot claim readiness while the producer is fixture-only.

P1a removes T-012 -> T-050 -> T-027 -> T-012 by accepting the local subset before Colin. T-050A is now the approved contract milestone; the graph T-050 node represents remaining T-050B. A-019 remains before API/site. T-012 implementation is authorized, not already verified.

## 8. Verification contract and acceptance

Before Q2a is proposed verified:
1. All 120 codebook items accounted for; 108 runtime-mapped items, one signed release-2.7 language slot deferred to its external owner, and 11 out-of-release placeholders; signed grain and visibility retained for all 120. No duplicate column names.
2. Golden normalized CSVs for three institutions cover legacy v2.5, 2.7 one-page/multi-activity, and multiple-source/combined activity; per-item, multipart and list-member support round-trip without truncation.
3. Same physical page/two activities has distinct source IDs and distinct evaluation values with no overwrite; existing n_sources semantics retained.
4. Original observation endpoints survive consolidation into the same final activity; dangling endpoints rejected.
5. Version guards accept exactly v2.5 and 2.7; unknown/missing historical provenance never becomes 2.7; invalid/incomplete new instrument records rejected.
6. Exact domains/counts and unavailable states follow the PI choices; no email leakage through public extracted-email fields.
7. No obsolete old-loader compatibility claim; planned capability guard and A-019 remain explicit.
8. Existing ENUM suite stays green except approved strict expected pin/schema failures until T-035. Regeneration of final contract goldens remains T-035 only.

T-024 handoff: consume generated support_entailment labels, instruction_page and signed label_rules. Multipart labels preserve parts plus first-part top-level alias. Check each selected multivalue separately, use year strings for computed years, and do not demand finite answer-label maps for free text. No raw item code is substituted for a plain-language label. Signed support exemptions are retained.

Acceptance record: P2 APPROVED; S1a/S2a/P1a APPROVED (reply above); independent draft review ready for PI review with all 12 findings addressed (Drive engineer-review/review.json SHA256 96ae98990998c3c92c3f3db14fcb8ccbf406bd75166db102cc246b4dd649cf33); local implementation IN PROGRESS; Colin A-019 PENDING; send approval PENDING.
