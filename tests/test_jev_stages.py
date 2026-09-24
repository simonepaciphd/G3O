"""Tests for jev integration in Stages 2 and 3.

Covers:
- jev_official_site: question building, state building, result parsing
- jev_url_triage: question building, state building, result parsing
- jev_stage_runner: synchronous driver with concurrency
- stage_classify: routing logic (_is_jev_model)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from g3o.classify.jev_official_site import (
    CONFIDENCE_LEVELS,
    CONFIDENCE_THRESHOLD_HIGH,
    CONFIDENCE_THRESHOLD_LOW,
    JEV_QUESTION_SET_VERSION,
    JevOfficialSiteResult,
    build_official_site_questions,
    build_official_site_state,
    parse_official_site_result,
)
from g3o.classify.jev_url_triage import (
    JEV_QUESTION_SET_VERSION as TRIAGE_JEV_QUESTION_SET_VERSION,
    KEEP_THRESHOLD,
    JevURLDecision,
    JevURLTriageResult,
    build_triage_questions,
    build_triage_state,
    parse_triage_result,
)
from g3o.common.credentials import Credentials, resolve
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.paths import institution_dir
from g3o.run.presweep.jev_stage_runner import (
    DEFAULT_JEV_CONCURRENCY,
    JevStageMetrics,
    run_jev_stage,
)
from g3o.run.presweep.stage_classify import _is_jev_model


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

    def test_other_model(self):
        assert _is_jev_model("claude-3-opus") is False


# ---------------------------------------------------------------------------
# jev_official_site
# ---------------------------------------------------------------------------


class TestJevOfficialSiteState:
    """build_official_site_state builds the jev state correctly."""

    def test_build_state(self):
        institution = {
            "institution_id": "INST-001",
            "name": "Test Institution",
            "country": "US",
        }
        search_results = [
            {"link": "https://example.gov", "title": "Example Gov", "snippet": "Official site"},
            {"link": "https://wikipedia.org/example", "title": "Wikipedia", "snippet": "About"},
        ]
        state = build_official_site_state(institution, search_results)
        assert state["institution"] == institution
        assert len(state["search_results"]) == 2
        assert state["search_results"][0]["url"] == "https://example.gov"
        assert state["search_results"][0]["title"] == "Example Gov"
        assert state["search_results"][0]["snippet"] == "Official site"

    def test_build_state_empty_results(self):
        institution = {"institution_id": "INST-001"}
        state = build_official_site_state(institution, [])
        assert state["search_results"] == []


class TestJevOfficialSiteQuestions:
    """build_official_site_questions builds a single Choice question."""

    def test_build_questions(self):
        candidate_urls = ["https://example.gov", "https://wikipedia.org/example"]
        questions = build_official_site_questions(candidate_urls)
        assert "official_site" in questions
        # Only one question now (site_confidence removed)
        assert len(questions) == 1
        # Check Choice criteria has positional ids
        choice_q = questions["official_site"]
        assert "u0" in choice_q.criteria
        assert "u1" in choice_q.criteria
        assert "none" in choice_q.criteria

    def test_build_questions_empty(self):
        questions = build_official_site_questions([])
        assert "official_site" in questions
        # Choice criteria should only have "none"
        choice_q = questions["official_site"]
        assert "none" in choice_q.criteria
        assert "u0" not in choice_q.criteria


class TestJevOfficialSiteParse:
    """parse_official_site_result parses jev results correctly."""

    def test_parse_high_confidence(self):
        result = JevResult(
            answers={
                "official_site": JevAnswer(
                    question_id="official_site",
                    type="choice",
                    choice="u0",
                    confidence=0.9,
                    probabilities={"u0": 0.9, "u1": 0.1, "none": 0.0},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-123",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov", "https://wikipedia.org"]
        parsed = parse_official_site_result(result, candidate_urls)
        assert parsed.url == "https://example.gov"
        assert parsed.confidence == "high"
        assert parsed.jev_confidence == 0.9
        assert parsed.response_model == "jev-1.13.0"

    def test_parse_low_confidence_gate(self):
        """Confidence < 0.5 forces url=None."""
        result = JevResult(
            answers={
                "official_site": JevAnswer(
                    question_id="official_site",
                    type="choice",
                    choice="u0",
                    confidence=0.3,  # Below threshold
                    probabilities={"u0": 0.3, "u1": 0.7, "none": 0.0},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-456",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov", "https://wikipedia.org"]
        parsed = parse_official_site_result(result, candidate_urls)
        assert parsed.url is None  # Confidence gate forced null
        assert parsed.confidence == "none"

    def test_parse_none_choice(self):
        """Choice 'none' means no URL selected."""
        result = JevResult(
            answers={
                "official_site": JevAnswer(
                    question_id="official_site",
                    type="choice",
                    choice="none",
                    confidence=0.8,
                    probabilities={"u0": 0.1, "u1": 0.1, "none": 0.8},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-789",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov", "https://wikipedia.org"]
        parsed = parse_official_site_result(result, candidate_urls)
        assert parsed.url is None
        assert parsed.confidence == "none"

    def test_parse_invalid_choice_index(self):
        """Choice index out of range raises."""
        result = JevResult(
            answers={
                "official_site": JevAnswer(
                    question_id="official_site",
                    type="choice",
                    choice="u5",  # Out of range
                    confidence=0.9,
                    probabilities={},
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-err",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov"]
        with pytest.raises(RuntimeError, match="out of range"):
            parse_official_site_result(result, candidate_urls)


# ---------------------------------------------------------------------------
# jev_url_triage
# ---------------------------------------------------------------------------


class TestJevURLTriageState:
    """build_triage_state builds the jev state correctly."""

    def test_build_state(self):
        institution = {"institution_id": "INST-001", "name": "Test"}
        candidate_urls = ["https://example.gov/ai", "https://wikipedia.org"]
        official_site = "https://example.gov"
        state = build_triage_state(institution, candidate_urls, official_site)
        assert state["institution"] == institution
        assert state["official_site"] == official_site
        assert len(state["candidate_urls"]) == 2
        assert state["candidate_urls"][0]["url"] == "https://example.gov/ai"

    def test_build_state_no_official_site(self):
        institution = {"institution_id": "INST-001"}
        candidate_urls = ["https://example.gov"]
        state = build_triage_state(institution, candidate_urls, None)
        assert state["official_site"] is None


class TestJevURLTriageQuestions:
    """build_triage_questions builds one Noul per URL."""

    def test_build_questions(self):
        candidate_urls = ["https://example.gov/ai", "https://wikipedia.org"]
        questions = build_triage_questions(candidate_urls)
        assert len(questions) == 2
        assert "keep_u0" in questions
        assert "keep_u1" in questions
        # Each question is a Noul
        for q in questions.values():
            assert q.type == "noul"

    def test_build_questions_empty(self):
        questions = build_triage_questions([])
        assert len(questions) == 0


class TestJevURLTriageParse:
    """parse_triage_result parses jev results correctly."""

    def test_parse_all_keep(self):
        result = JevResult(
            answers={
                "keep_u0": JevAnswer(
                    question_id="keep_u0",
                    type="noul",
                    noul=0.9,
                ),
                "keep_u1": JevAnswer(
                    question_id="keep_u1",
                    type="noul",
                    noul=0.8,
                ),
            },
            response_model="jev-1.13.0",
            request_id="req-triage-1",
            input_tokens=200,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov/ai", "https://example.gov/news"]
        parsed = parse_triage_result(result, candidate_urls)
        assert len(parsed.decisions) == 2
        assert parsed.decisions[0].url == "https://example.gov/ai"
        assert parsed.decisions[0].decision == "keep"
        assert parsed.decisions[0].noul == 0.9
        assert parsed.decisions[1].url == "https://example.gov/news"
        assert parsed.decisions[1].decision == "keep"
        assert parsed.kept_urls == candidate_urls

    def test_parse_mixed_decisions(self):
        result = JevResult(
            answers={
                "keep_u0": JevAnswer(question_id="keep_u0", type="noul", noul=0.9),
                "keep_u1": JevAnswer(question_id="keep_u1", type="noul", noul=0.3),
                "keep_u2": JevAnswer(question_id="keep_u2", type="noul", noul=0.6),
            },
            response_model="jev-1.13.0",
            request_id="req-triage-2",
            input_tokens=300,
            output_tokens=0,
        )
        candidate_urls = [
            "https://example.gov/ai",
            "https://wikipedia.org",
            "https://example.gov/news",
        ]
        parsed = parse_triage_result(result, candidate_urls)
        assert len(parsed.decisions) == 3
        assert parsed.decisions[0].decision == "keep"
        assert parsed.decisions[1].decision == "drop"
        assert parsed.decisions[2].decision == "keep"
        assert parsed.kept_urls == [
            "https://example.gov/ai",
            "https://example.gov/news",
        ]

    def test_parse_custom_threshold(self):
        """Custom keep threshold changes decisions."""
        result = JevResult(
            answers={
                "keep_u0": JevAnswer(question_id="keep_u0", type="noul", noul=0.45),
            },
            response_model="jev-1.13.0",
            request_id="req-threshold",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov"]
        # Default threshold 0.5: 0.45 < 0.5 → drop
        parsed_default = parse_triage_result(result, candidate_urls)
        assert parsed_default.decisions[0].decision == "drop"
        # Custom threshold 0.4: 0.45 >= 0.4 → keep
        parsed_custom = parse_triage_result(result, candidate_urls, keep_threshold=0.4)
        assert parsed_custom.decisions[0].decision == "keep"

    def test_parse_missing_answer(self):
        """Missing answer for a URL raises."""
        result = JevResult(
            answers={
                "keep_u0": JevAnswer(question_id="keep_u0", type="noul", noul=0.9),
                # keep_u1 missing
            },
            response_model="jev-1.13.0",
            request_id="req-missing",
            input_tokens=100,
            output_tokens=0,
        )
        candidate_urls = ["https://example.gov", "https://wikipedia.org"]
        with pytest.raises(RuntimeError, match="missing or invalid"):
            parse_triage_result(result, candidate_urls)


# ---------------------------------------------------------------------------
# jev_stage_runner
# ---------------------------------------------------------------------------


class TestJevStageRunner:
    """run_jev_stage drives jev stages synchronously."""

    def test_run_stage_success(self, tmp_path: Path):
        """Successful run processes all institutions."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Create institution directories
        inst_dir_1 = institution_dir(run_dir, "INST-001")
        inst_dir_1.mkdir(parents=True)
        inst_dir_2 = institution_dir(run_dir, "INST-002")
        inst_dir_2.mkdir(parents=True)

        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )

        institutions = [
            {"institution_id": "INST-001", "name": "Test 1"},
            {"institution_id": "INST-002", "name": "Test 2"},
        ]

        def build_request(inst):
            return {"state": "data"}, {"q1": "question"}

        def process_result(inst_id, result, inst):
            # Write artifact
            inst_dir = institution_dir(run_dir, inst_id)
            (inst_dir / "jev_result.json").write_text("{}")

        # Mock the ask function to return a result
        with patch("g3o.run.presweep.jev_stage_runner.ask") as mock_ask:
            mock_ask.return_value = JevResult(
                answers={},
                response_model="jev-1.13.0",
                request_id="req-mock",
                input_tokens=100,
                output_tokens=0,
            )
            metrics = run_jev_stage(
                run_dir=run_dir,
                stage="test_stage",
                institutions=institutions,
                build_request=build_request,
                process_result=process_result,
                credentials=credentials,
                model="jev-1.13.0",
                concurrency=2,
                artifact_filename="jev_result.json",
            )

        assert metrics.n_institutions == 2
        assert metrics.n_success == 2
        assert metrics.n_failed == 0
        assert metrics.total_input_tokens == 200  # 2 * 100

    def test_run_stage_resume(self, tmp_path: Path):
        """Resume skips institutions with existing artifacts."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Pre-create artifact for INST-001 using the correct path structure
        inst_dir_1 = institution_dir(run_dir, "INST-001")
        inst_dir_1.mkdir(parents=True)
        (inst_dir_1 / "jev_result.json").write_text("{}")
        # Create directory for INST-002
        inst_dir_2 = institution_dir(run_dir, "INST-002")
        inst_dir_2.mkdir(parents=True)

        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )

        institutions = [
            {"institution_id": "INST-001", "name": "Test 1"},
            {"institution_id": "INST-002", "name": "Test 2"},
        ]

        def build_request(inst):
            return {"state": "data"}, {"q1": "question"}

        def process_result(inst_id, result, inst):
            inst_dir = institution_dir(run_dir, inst_id)
            (inst_dir / "jev_result.json").write_text("{}")

        with patch("g3o.run.presweep.jev_stage_runner.ask") as mock_ask:
            mock_ask.return_value = JevResult(
                answers={},
                response_model="jev-1.13.0",
                request_id="req-mock",
                input_tokens=100,
                output_tokens=0,
            )
            metrics = run_jev_stage(
                run_dir=run_dir,
                stage="test_stage",
                institutions=institutions,
                build_request=build_request,
                process_result=process_result,
                credentials=credentials,
                model="jev-1.13.0",
                concurrency=2,
                artifact_filename="jev_result.json",
            )

        assert metrics.n_institutions == 2
        assert metrics.n_success == 1  # Only INST-002 processed
        assert metrics.n_skipped == 1  # INST-001 skipped
        assert metrics.n_failed == 0

    def test_run_stage_failure(self, tmp_path: Path):
        """Failed requests are recorded in attrition."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        inst_dir = institution_dir(run_dir, "INST-001")
        inst_dir.mkdir(parents=True)

        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )

        institutions = [{"institution_id": "INST-001", "name": "Test 1"}]

        def build_request(inst):
            return {"state": "data"}, {"q1": "question"}

        def process_result(inst_id, result, inst):
            pass

        with patch("g3o.run.presweep.jev_stage_runner.ask") as mock_ask:
            mock_ask.side_effect = RuntimeError("API error")
            metrics = run_jev_stage(
                run_dir=run_dir,
                stage="test_stage",
                institutions=institutions,
                build_request=build_request,
                process_result=process_result,
                credentials=credentials,
                model="jev-1.13.0",
                concurrency=1,
                artifact_filename="jev_result.json",
            )

        assert metrics.n_institutions == 1
        assert metrics.n_success == 0
        assert metrics.n_failed == 1


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module constants are set correctly."""

    def test_official_site_constants(self):
        assert JEV_QUESTION_SET_VERSION == "g3o.classify.official_site.jev.v1"
        assert CONFIDENCE_THRESHOLD_LOW == 0.5
        assert CONFIDENCE_THRESHOLD_HIGH == 0.8
        assert CONFIDENCE_LEVELS == ["none", "low", "medium", "high"]

    def test_triage_constants(self):
        assert TRIAGE_JEV_QUESTION_SET_VERSION == "g3o.classify.url_triage.jev.v1"
        assert KEEP_THRESHOLD == 0.5

    def test_runner_constants(self):
        assert DEFAULT_JEV_CONCURRENCY == 20
