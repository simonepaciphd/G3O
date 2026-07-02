"""Batch 2 — GenAI definition adherence enforcement (2026-07).

The June validation report found two recurring over-coding patterns in the
prior (v0) pipeline's output:

  (a) ordinary automation / RPA / rule-based systems coded as confirmed
      GenAI activity, and
  (b) "might use AI in the future" / exploratory language coded as a
      confirmed activity (typically `adoption_stage = announced`).

The GenAI definition itself is unchanged (`output_contract.md` is untouched
by this batch). What changed is enforcement: tightened wording in
`g3o/extract/prompts/system_prompt.md` and
`g3o/validate/prompts/system_prompt.md`, plus two heuristic, audit-only QC
flags in `g3o.validate.qc` (`weak_generative_signal_activities`,
`speculative_adoption_activities`) that make it cheap to sample candidate
over-coded activities from a real run for human review.

This suite is a **static** audit: it exercises the new deterministic QC
heuristics against a labeled corpus (real snippets drawn from the published
`data/pilot_v1` dataset plus synthetic cases modeled on the two failure
patterns) and proves the heuristics fire on the failure-mode cases and stay
silent on the legitimate-activity controls. It does NOT call the LLM to
prove the tightened prompt wording changes actual model behavior — that
would require a small live OpenAI Batch API run, which was not authorized
in this session (see PR description). A live-sample empirical audit is a
suggested follow-up before the tightened prompts are treated as validated
in production.
"""

from __future__ import annotations

from typing import Any

from g3o.validate.qc import (
    qc_per_institution,
    speculative_adoption_activities,
    weak_generative_signal_activities,
)

# ---------------------------------------------------------------------------
# Builders (same shape conventions as tests/test_consolidated_contract.py)
# ---------------------------------------------------------------------------


def _meta(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "institution_id": "INST-0001",
        "n_input_pages": 1,
        "n_input_rows": 1,
        "response_timestamp": "2026-05-09T12:00:00Z",
        "model_label": "gpt-5-nano",
        "notes": "none",
    }
    base.update(overrides)
    return base


def _institution(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "institution_id": "INST-0001",
        "institution_name": "Test Ministry",
        "country": "Testland",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "has_genai_activity": "yes",
        "institution_summary": "GenAI activity documented.",
        "institution_search_languages": "en",
    }
    base.update(overrides)
    return base


def _activity(activity_id: str = "A1", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "activity_id": activity_id,
        "activity_name": "Test activity",
        "activity_type": "internal_operational",
        "adoption_stage": "production",
        "access_type": "unknown",
        "interaction_type": "chatbot",
        "tool_name": "unknown",
        "vendor": "unknown",
        "deployment_mode": "unknown",
        "target_users": "public",
        "year_announced": "unknown",
        "year_deployed": "unknown",
        "has_human_oversight": "not_documented",
        "has_transparency_notice": "not_documented",
        "has_data_classification": "not_documented",
        "has_risk_assessment": "not_documented",
        "reported_outcomes": "none_reported",
        "reported_incidents": "none_reported",
        "scope_notes": "none",
        "n_sources": 1,
        "confidence": "medium",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def _source(
    source_id: str = "S1",
    activity_id: str = "A1",
    **overrides: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_id": source_id,
        "activity_id": activity_id,
        "source_url": "https://example.gov/page",
        "source_title": "Test page",
        "source_publication_date": "2025",
        "source_access_date": "2026-05-08",
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_activity",
        "source_snippet": "placeholder",
    }
    base.update(overrides)
    return base


def _response(
    *, activity: dict[str, Any], source: dict[str, Any], **overrides: Any
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "consolidation_metadata": _meta(),
        "institution": _institution(),
        "activities": [activity],
        "sources": [source],
    }
    base.update(overrides)
    return base


def _validate(payload: dict[str, Any]):
    from g3o.common.contract import ConsolidatedInstitutionResponse

    return ConsolidatedInstitutionResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# Failure mode (a): automation / RPA / rule-based coded as confirmed GenAI
# ---------------------------------------------------------------------------


def test_flags_ai_chatbot_with_no_generative_signal() -> None:
    """Synthetic case modeled on the exact wording added to the extract prompt.

    "AI-powered chatbot" with no model name, no generative-capability
    description, and no genai_vs_traditional_ai flag — exactly the over-coding
    pattern the tightened prompt now tells the extractor to route to
    `unclear`/`ambiguous` instead of `confirms_activity`.
    """
    resp = _validate(
        _response(
            activity=_activity(uncertainty_flags="none"),
            source=_source(
                source_snippet=(
                    "Our new AI-powered citizen chatbot instantly answers "
                    "common questions about permits."
                )
            ),
        )
    )
    assert weak_generative_signal_activities(resp) == ["A1"]


def test_does_not_flag_chatbot_naming_a_foundation_model() -> None:
    """Contrast case from the same worked example: naming GPT-4 clears the bar."""
    resp = _validate(
        _response(
            activity=_activity(),
            source=_source(
                source_snippet=(
                    "Our new chatbot, built on GPT-4, drafts personalized "
                    "responses to citizen inquiries."
                )
            ),
        )
    )
    assert weak_generative_signal_activities(resp) == []


def test_does_not_flag_real_pilot_v1_generative_image_case() -> None:
    """Real snippet from data/pilot_v1 (Dept. of the Interior, Adobe Firefly).

    A should-remain-confirmed regression control: "generative" is explicit,
    so this must never be swept up by the heuristic even though it's
    otherwise a plain vendor-tool description.
    """
    resp = _validate(
        _response(
            activity=_activity(activity_type="internal_operational"),
            source=_source(
                source_snippet=(
                    "Adobe's Firefly generative image AI model was used "
                    "within Photoshop to create artistic sketches of "
                    "different nature scenes."
                )
            ),
        )
    )
    assert weak_generative_signal_activities(resp) == []


def test_does_not_double_flag_already_flagged_activity() -> None:
    """If the extractor already caught the ambiguity, the QC flag stays quiet."""
    resp = _validate(
        _response(
            activity=_activity(uncertainty_flags="genai_vs_traditional_ai"),
            source=_source(
                source_snippet="Our AI-powered automation platform handles requests."
            ),
        )
    )
    assert weak_generative_signal_activities(resp) == []


def test_flags_rpa_described_activity() -> None:
    """Plain RPA/automation language, no generative signal anywhere."""
    resp = _validate(
        _response(
            activity=_activity(activity_type="internal_operational", interaction_type="document_processing"),
            source=_source(
                source_snippet=(
                    "The agency deployed robotic process automation to "
                    "route incoming forms to the correct department."
                )
            ),
        )
    )
    assert weak_generative_signal_activities(resp) == ["A1"]


# ---------------------------------------------------------------------------
# Failure mode (b): "might use AI in future" coded as confirmed adoption_stage
# ---------------------------------------------------------------------------


def test_flags_real_pilot_v1_speculative_copilot_case() -> None:
    """Real snippet from data/pilot_v1 (EPA, legacy federal-inventory ingest).

    "Several potential use cases are possible ... anticipated in upcoming
    releases" is exactly the hedged, undated language the tightened extract
    prompt now says does not clear the `announced` bar. This row was
    ingested from an external federal inventory rather than produced by the
    g3o extract/validate prompts, so it is illustrative of the failure
    pattern rather than a direct false positive of this pipeline — flagged
    here as a corpus case, not attributed to this codebase's prompts.
    """
    resp = _validate(
        _response(
            activity=_activity(adoption_stage="announced", activity_type="pilot_experiment"),
            source=_source(
                source_snippet=(
                    "Several potential use cases are possible with the "
                    "addition of CoPilot into the product which is "
                    "anticipated in upcoming releases within our GCC tenant."
                )
            ),
        )
    )
    assert speculative_adoption_activities(resp) == ["A1"]


def test_does_not_flag_real_pilot_v1_firm_commitment_case() -> None:
    """Real snippet from data/pilot_v1 (chatgpt_web_v1 run, Supreme Court of Mongolia).

    "plans to introduce 'Generative AI'" with a named capability and a dated
    announcement is a genuine `announced` case — the tightened wording's
    worked-example contrast — and must not be flagged.
    """
    resp = _validate(
        _response(
            activity=_activity(adoption_stage="announced", activity_type="internal_operational"),
            source=_source(
                source_snippet=(
                    "The Court says it “plans to introduce "
                    "‘Generative AI’” technology to retrieve "
                    "similar court decisions from databases and provide "
                    "research-level assistance for judges."
                )
            ),
        )
    )
    assert speculative_adoption_activities(resp) == []


def test_does_not_flag_speculative_language_outside_announced_stage() -> None:
    """The heuristic only screens `announced`; other stages are out of scope here."""
    resp = _validate(
        _response(
            activity=_activity(adoption_stage="pilot"),
            source=_source(
                source_snippet="The agency is considering expanding the pilot."
            ),
        )
    )
    assert speculative_adoption_activities(resp) == []


def test_qc_per_institution_surfaces_both_flags() -> None:
    """Integration: the per-institution QC dict exposes both audit flags."""
    resp = _validate(
        _response(
            activity=_activity(
                adoption_stage="announced", uncertainty_flags="none"
            ),
            source=_source(
                source_snippet="The Ministry may explore automation for permits."
            ),
        )
    )
    qc = qc_per_institution(resp)
    assert qc["weak_generative_signal_activities"] == ["A1"]
    assert qc["speculative_adoption_activities"] == ["A1"]
