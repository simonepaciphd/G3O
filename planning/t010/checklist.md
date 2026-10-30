# T-010 checklist: SPEC rule -> codebook item (DRAFT, uncommitted per P6)

Generated 2026-10-30 from `codebook/codebook.yaml` (worktree `C:/Users/spaci/worktrees/G3O-integrator`; build sha256 `23cb4857a6f9fb525c52f969d4b1922f252f0bf36c6f9cf060be8ea1fb28bf8b`) by the plan integrator's subagent, after the final fold (PI 2026-10-30 "all accepted"). Self-check for T-010: every R-010..R-045 and R-087 maps to at least one item or shared rule. Mapped rows list every item whose `refs` name the row and every shared rule cut from it; cross-cutting rows are kept as written.

| SPEC row | Codebook items / shared rules | Status |
|---|---|---|
| R-010 | `core.rule.ws10_event` | mapped |
| R-011 | `core.rule.ws10_governance` | mapped |
| R-012 | `core.rule.ws10_excluded_only` | mapped |
| R-013 | `core.adoption_stage`, `core.rule.ws10_proposals` | mapped |
| R-014 | `core.observed_actor_name`, `core.observed_actor_relationship`, `core.observed_actor_role`, `core.rule.v26_detail_fields` | mapped |
| R-015 | `core.page_review_state`, `core.page_verdict` | mapped |
| R-016 | `core.page_verdict`, `core.rule.genai_boundary` | mapped |
| R-017 | `core.activity_relation_cross_page`, `core.activity_segment`, `core.rule.activity_unit` | mapped |
| R-020 | `core.disclosure_form` | mapped |
| R-021 | `core.disclosure_scope` | mapped |
| R-022 | `core.evaluation_documented`, `core.evaluation_type_bias_or_safety_testing`, `core.evaluation_type_independent_audit`, `core.evaluation_type_ongoing_monitoring`, `core.evaluation_type_pilot_evaluation`, `core.evaluation_type_pre_deployment_testing`, `core.evaluation_type_user_feedback` | mapped |
| R-023 | `core.content_contact`, `core.content_contact_details`, `core.content_contact_emails`, `core.content_contact_named`, `core.content_data`, `core.content_human_oversight`, `core.content_purpose`, `core.content_risk_assessment`, `core.content_status_date`, `core.content_tool_or_model`, `core.content_user_notification`, `core.content_users`, `core.content_vendor` | mapped |
| R-024 | `core.incident_kind`, `core.outcome_kind`, `core.reported_incidents`, `core.reported_outcomes` | mapped |
| R-025 | every item with `frozen_signature` (CX items; template field 23, check 4) | cross-cutting |
| R-026 | `core.coder_record`, `core.setup_pointer` | mapped |
| R-030 | `core.page_complete` | mapped |
| R-031 | `core.page_complete`, `core.discovery_path` (pipeline rule, not an item; exempt for procurement, r2#54) | cross-cutting |
| R-032 | `core.page_review_state`, `core.discovery_path` (hop limit and cap are pipeline settings) | cross-cutting |
| R-033 | `core.discovery_path` (link eligibility is a pipeline rule) | cross-cutting |
| R-034 | `core.discovery_path` | mapped |
| R-035 | `core.discovery_path`, `core.text_source` (back-fill following is a pipeline rule) | cross-cutting |
| R-036 | `core.discovery_path` | mapped |
| R-040 | `core.source_publication_date`, `core.support_entailment`, `core.supporting_text` | mapped |
| R-041 | `core.support_rule_name`, `core.support_status`, `core.support_status_second_reason` | mapped |
| R-042 | `core.source_publication_date`, `core.supporting_text` | mapped |
| R-044 | template field 16 `long_page_rule` on every page-level classifier item; verdict order on `core.page_verdict` | cross-cutting |
| R-043 | `core.supporting_text` | mapped |
| R-045 | `vocabularies.missing`; template field 20 `missing_tokens` | cross-cutting |
| R-087 | `core.adoption_stage` | mapped |

## Fields still `open` (count of items)

| Field | Items |
|---|---|
| `version_introduced` | 120 |
| `translation_v25` | 32 |

Open paths outside items: `release.label`, `release.signature_record` (set at sign-off, P3 / P4).
