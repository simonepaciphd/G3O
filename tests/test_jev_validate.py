"""Tests for jev integration in Stage 6 (validate).

Covers:
- jev_validate: state building, question building, result parsing
- stage_validate: routing logic (_is_jev_model)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from g3o.common.contract import (
    ConsolidatedActivity,
    ConsolidatedInstitution,
    ConsolidatedInstitutionResponse,
    ConsolidationMetadata,
    SourceRecord,
)
from g3o.common.credentials import Credentials, resolve
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.validate.jev_validate import (
    JEV_QUESTION_SET_VERSION,
    JevValidateResult,
    build_validate_questions,
    build_validate_state,
    parse_validate_result,
)
from g3o.run.presweep.stage_validate import _is_jev_model


# ---------------------------------------------------------------------------
# _is_jev_model routing
# ---------------------------------------------------------------------------


class TestIsJevModel:
    """_is_jev_model identifies jev models by prefix."""

    def test_jev_model(self):
        assert _is_jev_model("jev-1.13.0") is True

    def test_jev_latest(self):
        assert _is_jev_model("jev-latest") is True

    def test_openai_model(self):
        assert _is_jev_model("gpt-5-nano") is False


# ---------------------------------------------------------------------------
# jev_validate state building
# ---------------------------------------------------------------------------


class TestJevValidateState:
    """build_validate_state builds the jev state correctly."""

    def test_build_state(self):
        institution = {
            "institution_id": "INST-001",
            "institution_name": "Test Institution",
            "country": "US",
        }
        input_rows = [
            {
                "activity_name": "AI Chatbot",
                "genai_evidence": "confirms_activity",
                "source_url": "https://example.gov/ai",
            },
            {
                "activity_name": "AI Chatbot",
                "genai_evidence": "confirms_activity",
                "source_url": "https://example.gov/news",
            },
        ]
        n_input_pages = 2

        state = build_validate_state(institution, input_rows, n_input_pages)
        assert state["institution"] == institution
        assert state["input_rows"] == input_rows
        assert state["n_input_pages"] == 2
        assert state["n_input_rows"] == 2


# ---------------------------------------------------------------------------
# jev_validate question building
# ---------------------------------------------------------------------------


class TestJevValidateQuestions:
    """build_validate_questions builds the right questions."""

    def test_build_questions_no_activity_rows(self):
        """No activity rows → no pairwise questions."""
        input_rows = [
            {"genai_evidence": "confirms_absence", "activity_name": "_NA_"},
        ]
        questions = build_validate_questions(input_rows)
        # Should have no pairwise questions
        pairwise = [q for q in questions if q.startswith("same_activity_")]
        assert len(pairwise) == 0

    def test_build_questions_single_activity_row(self):
        """Single activity row → no pairwise questions."""
        input_rows = [
            {"genai_evidence": "confirms_activity", "activity_name": "AI Chatbot"},
        ]
        questions = build_validate_questions(input_rows)
        pairwise = [q for q in questions if q.startswith("same_activity_")]
        assert len(pairwise) == 0

    def test_build_questions_two_different_activities(self):
        """Two different activity names → one pairwise question."""
        input_rows = [
            {"genai_evidence": "confirms_activity", "activity_name": "AI Chatbot"},
            {"genai_evidence": "confirms_activity", "activity_name": "AI Translation"},
        ]
        questions = build_validate_questions(input_rows)
        pairwise = [q for q in questions if q.startswith("same_activity_")]
        assert len(pairwise) == 1

    def test_build_questions_two_same_activities(self):
        """Two same activity names → no pairwise question (already grouped)."""
        input_rows = [
            {"genai_evidence": "confirms_activity", "activity_name": "AI Chatbot"},
            {"genai_evidence": "confirms_activity", "activity_name": "AI Chatbot"},
        ]
        questions = build_validate_questions(input_rows)
        pairwise = [q for q in questions if q.startswith("same_activity_")]
        assert len(pairwise) == 0

    def test_build_questions_with_conflicts(self):
        """Conflicting fields → conflict resolution questions."""
        input_rows = [
            {
                "genai_evidence": "confirms_activity",
                "activity_name": "AI Chatbot",
                "adoption_stage": "pilot",
            },
            {
                "genai_evidence": "confirms_activity",
                "activity_name": "AI Chatbot",
                "adoption_stage": "production",
            },
        ]
        questions = build_validate_questions(input_rows)
        conflict = [q for q in questions if q.startswith("conflict_")]
        assert len(conflict) > 0

    def test_build_questions_with_summaries(self):
        """Multiple summaries → summary selection question."""
        input_rows = [
            {
                "genai_evidence": "confirms_activity",
                "activity_name": "AI Chatbot",
                "institution_summary": "Summary A",
            },
            {
                "genai_evidence": "confirms_activity",
                "activity_name": "AI Translation",
                "institution_summary": "Summary B",
            },
        ]
        questions = build_validate_questions(input_rows)
        assert "institution_summary" in questions


# ---------------------------------------------------------------------------
# jev_validate result parsing
# ---------------------------------------------------------------------------


class TestJevValidateParse:
    """parse_validate_result parses jev results correctly."""

    def test_parse_simple_case(self):
        """Simple case: one activity, two sources."""
        institution = {
            "institution_id": "INST-001",
            "institution_name": "Test Institution",
            "country": "US",
            "branch_of_government": "executive",
            "level_of_government": "national",
            "institution_search_languages": "en",
        }
        input_rows = [
            {
                "activity_name": "AI Chatbot",
                "genai_evidence": "confirms_activity",
                "source_url": "https://example.gov/ai",
                "source_title": "AI Initiative",
                "source_publication_date": "2024-01-01",
                "source_access_date": "2024-06-01",
                "source_type": "official_gov",
                "source_language": "en",
                "source_credibility": "high",
                "source_snippet": "We launched an AI chatbot.",
                "confidence": "high",
                "uncertainty_flags": "none",
                "institution_summary": "Test has AI chatbot.",
                "activity_type": "public_facing_service",
                "adoption_stage": "production",
                "access_type": "proprietary_vendor",
                "interaction_type": "chatbot",
                "tool_name": "ChatGPT",
                "vendor": "OpenAI",
                "deployment_mode": "standalone",
                "target_users": "public",
                "year_announced": "2023",
                "year_deployed": "2024",
                "has_human_oversight": "yes",
                "has_transparency_notice": "yes",
                "has_data_classification": "yes",
                "has_risk_assessment": "yes",
                "reported_outcomes": "none_reported",
                "reported_incidents": "none_reported",
                "scope_notes": "none",
            },
            {
                "activity_name": "AI Chatbot",
                "genai_evidence": "confirms_activity",
                "source_url": "https://example.gov/news",
                "source_title": "News Article",
                "source_publication_date": "2024-02-01",
                "source_access_date": "2024-06-01",
                "source_type": "news_major",
                "source_language": "en",
                "source_credibility": "medium",
                "source_snippet": "Chatbot launched.",
                "confidence": "medium",
                "uncertainty_flags": "none",
                "institution_summary": "Test has AI chatbot.",
                "activity_type": "public_facing_service",
                "adoption_stage": "production",
                "access_type": "proprietary_vendor",
                "interaction_type": "chatbot",
                "tool_name": "ChatGPT",
                "vendor": "OpenAI",
                "deployment_mode": "standalone",
                "target_users": "public",
                "year_announced": "2023",
                "year_deployed": "2024",
                "has_human_oversight": "yes",
                "has_transparency_notice": "yes",
                "has_data_classification": "yes",
                "has_risk_assessment": "yes",
                "reported_outcomes": "none_reported",
                "reported_incidents": "none_reported",
                "scope_notes": "none",
            },
        ]

        # Mock jev result
        result = JevResult(
            answers={
                "institution_summary": JevAnswer(
                    question_id="institution_summary",
                    type="choice",
                    choice="s0",
                    confidence=0.9,
                    probabilities={"s0": 0.9},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-validate-1",
            input_tokens=500,
            output_tokens=0,
        )

        parsed = parse_validate_result(result, institution, input_rows, 2)
        assert isinstance(parsed, JevValidateResult)
        assert parsed.response_model == "jev-1.13.0"
        assert len(parsed.activity_groups) == 1
        assert len(parsed.activity_groups[0]) == 2  # both rows in same group

        response = parsed.response
        assert isinstance(response, ConsolidatedInstitutionResponse)
        assert response.institution.has_genai_activity == "yes"
        assert len(response.activities) == 1
        assert len(response.sources) == 2
        assert response.activities[0].n_sources == 2

    def test_parse_no_activity(self):
        """No activity rows → has_genai_activity=no."""
        institution = {
            "institution_id": "INST-002",
            "institution_name": "Test Institution 2",
            "country": "US",
            "branch_of_government": "executive",
            "level_of_government": "national",
            "institution_search_languages": "en",
        }
        input_rows = [
            {
                "activity_name": "_NA_",
                "genai_evidence": "confirms_absence",
                "source_url": "https://example.gov/",
                "source_title": "Homepage",
                "source_publication_date": "unknown",
                "source_access_date": "2024-06-01",
                "source_type": "official_gov",
                "source_language": "en",
                "source_credibility": "high",
                "source_snippet": "No AI mentioned.",
                "confidence": "high",
                "uncertainty_flags": "none",
                "institution_summary": "No AI evidence found.",
                "activity_type": "unknown",
                "adoption_stage": "unknown",
                "access_type": "unknown",
                "interaction_type": "unknown",
                "tool_name": "unknown",
                "vendor": "unknown",
                "deployment_mode": "unknown",
                "target_users": "unknown",
                "year_announced": "unknown",
                "year_deployed": "unknown",
                "has_human_oversight": "not_documented",
                "has_transparency_notice": "not_documented",
                "has_data_classification": "not_documented",
                "has_risk_assessment": "not_documented",
                "reported_outcomes": "none_reported",
                "reported_incidents": "none_reported",
                "scope_notes": "none",
            },
        ]

        result = JevResult(
            answers={
                "institution_summary": JevAnswer(
                    question_id="institution_summary",
                    type="choice",
                    choice="s0",
                    confidence=0.9,
                    probabilities={"s0": 0.9},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-validate-2",
            input_tokens=300,
            output_tokens=0,
        )

        parsed = parse_validate_result(result, institution, input_rows, 1)
        response = parsed.response
        assert response.institution.has_genai_activity == "no"
        assert len(response.activities) == 0
        assert len(response.sources) == 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module constants are set correctly."""

    def test_jev_question_set_version(self):
        assert JEV_QUESTION_SET_VERSION == "g3o.validate.jev.v1"
