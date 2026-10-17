"""Tests for jev integration in Stage 6 (validate).

Covers:
- jev_validate: state building, question building, result parsing
- stage_validate: routing logic (_is_jev_model)
"""

from __future__ import annotations

from g3o.common.contract import (
    ConsolidatedInstitutionResponse,
)
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.run.presweep.stage_validate import _is_jev_model
from g3o.validate.jev_validate import (
    JEV_QUESTION_SET_VERSION,
    JevValidateResult,
    build_validate_questions,
    build_validate_state,
    parse_validate_result,
)

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


# ---------------------------------------------------------------------------
# Stage 6 runner: account errors
# ---------------------------------------------------------------------------


class TestRunValidateJevAccountError:
    """An account error (e.g. 402 no credits) aborts Stage 6 without .done."""

    def test_account_error_raises_and_skips_mark_done(self, tmp_path):
        from unittest.mock import patch

        import pytest

        from g3o.common.credentials import Credentials, resolve
        from g3o.common.jev_client import JevAccountError
        from g3o.common.run_state import is_done
        from g3o.run.presweep.stage_validate import _run_validate_jev

        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        inputs = [
            ({"institution_id": f"INST-{i:03d}"}, [{"row": i}], 1) for i in range(3)
        ]
        with (
            patch(
                "g3o.validate.consolidate.assemble_per_institution_inputs",
                return_value=inputs,
            ),
            patch("g3o.validate.jev_validate.build_validate_state", return_value={}),
            patch("g3o.validate.jev_validate.build_validate_questions", return_value={}),
            patch(
                "g3o.run.presweep.jev_stage_runner.ask",
                side_effect=JevAccountError("402 no credits"),
            ) as mock_ask,
            pytest.raises(JevAccountError),
        ):
            _run_validate_jev(
                tmp_path,
                [{}, {}, {}],
                model="jev-1.13.0",
                credentials=credentials,
                concurrency=1,
            )

        assert mock_ask.call_count == 1
        assert not is_done(tmp_path, "validate")


class TestRunValidateJevParallel:
    """Stage 6 jev runs through the bounded-concurrency driver."""

    def test_requests_overlap_and_stage_is_marked_done(self, tmp_path):
        import threading
        import time
        from unittest.mock import patch

        from g3o.common.credentials import Credentials, resolve
        from g3o.common.paths import institution_dir
        from g3o.common.run_state import is_done
        from g3o.run.presweep.stage_validate import _run_validate_jev

        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        ids = [f"INST-{i:03d}" for i in range(8)]
        for inst_id in ids:
            institution_dir(tmp_path, inst_id).mkdir(parents=True)
        # One institution already validated: resume must skip it.
        (institution_dir(tmp_path, ids[0]) / "6_validate.json").write_text("{}")
        inputs = [({"institution_id": i}, [{"row": i}], 1) for i in ids]

        lock = threading.Lock()
        in_flight = 0
        peak = 0

        def fake_ask(state, questions, *, client, model):
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return JevResult(
                answers={}, response_model="jev-1.13.0", request_id="r",
                input_tokens=10, output_tokens=1,
            )

        def fake_write(run_dir, institution_id, response):
            (institution_dir(run_dir, institution_id) / "6_validate.json").write_text("{}")

        with (
            patch(
                "g3o.validate.consolidate.assemble_per_institution_inputs",
                return_value=inputs,
            ),
            patch("g3o.validate.consolidate.write_consolidated_output", side_effect=fake_write),
            patch("g3o.validate.jev_validate.build_validate_state", return_value={}),
            patch("g3o.validate.jev_validate.build_validate_questions", return_value={}),
            patch("g3o.validate.jev_validate.parse_validate_result"),
            patch("g3o.run.presweep.jev_stage_runner.ask", side_effect=fake_ask),
        ):
            summary = _run_validate_jev(
                tmp_path,
                [{}] * len(ids),
                model="jev-1.13.0",
                credentials=credentials,
                concurrency=4,
            )

        assert peak > 1
        assert summary["n_consolidated"] == len(ids)
        assert summary["n_failed"] == 0
        assert is_done(tmp_path, "validate")


# ---------------------------------------------------------------------------
# Oversize fallback: chunked validation (PI ruling E1=b, 2026-10-17)
# ---------------------------------------------------------------------------

_INST = {
    "institution_id": "INST-OVR",
    "institution_name": "Oversize Institution",
    "country": "US",
    "branch_of_government": "executive",
    "level_of_government": "national",
    "institution_search_languages": "en",
}

_GROUP_D = (
    "activity_name", "activity_type", "adoption_stage", "access_type",
    "interaction_type", "tool_name", "vendor", "deployment_mode",
    "target_users", "year_announced", "year_deployed",
    "has_human_oversight", "has_transparency_notice",
    "has_data_classification", "has_risk_assessment",
    "reported_outcomes", "reported_incidents", "scope_notes",
)


def _row(url, *, name="AI Chatbot", evidence="confirms_activity",
         snippet="snippet", summary="", **overrides):
    row = {
        "activity_name": name,
        "genai_evidence": evidence,
        "source_url": url,
        "source_title": "Title",
        "source_publication_date": "2024-01-01",
        "source_access_date": "2024-06-01",
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "source_snippet": snippet,
        "confidence": "medium",
        "uncertainty_flags": "none",
        "institution_summary": summary,
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
    }
    if evidence != "confirms_activity":
        for f in _GROUP_D:
            row[f] = "_NA_"
    row.update(overrides)
    return row


def _empty_result(tokens=10):
    return JevResult(
        answers={}, response_model="jev-1.13.0", request_id="r",
        input_tokens=tokens, output_tokens=1,
    )


def _oversize_error():
    import httpx2
    import typesafe_sdk as ts

    return ts.TypeSafeBadRequestError(
        400, {"detail": {"error_type": "max_tokens_exceeded"}}, httpx2.Headers()
    )


def _response(rows, n_pages=1):
    return parse_validate_result(_empty_result(), _INST, rows, n_pages).response


class TestOversizeDetection:
    def test_max_tokens_400_detected(self):
        from g3o.validate.jev_validate import is_max_tokens_exceeded

        assert is_max_tokens_exceeded(_oversize_error())

    def test_other_400_not_detected(self):
        import httpx2
        import typesafe_sdk as ts

        from g3o.validate.jev_validate import is_max_tokens_exceeded

        exc = ts.TypeSafeBadRequestError(
            400, {"detail": {"error_type": "invalid_question"}}, httpx2.Headers()
        )
        assert not is_max_tokens_exceeded(exc)
        # No status 400 -> never oversize, whatever the text says.
        assert not is_max_tokens_exceeded(RuntimeError("max_tokens_exceeded"))


class TestChunkInputRows:
    def _pages(self, n_pages=6, rows_per_page=2):
        return [
            _row(f"https://p{p}.gov/", name=f"Act {p}", snippet=f"s{p}-{r}")
            for p in range(n_pages)
            for r in range(rows_per_page)
        ]

    def test_chunks_respect_budget_and_keep_pages_whole(self):
        from g3o.validate.jev_validate import chunk_input_rows, estimate_request_bytes

        rows = self._pages()
        two_pages = rows[:4]
        budget = estimate_request_bytes(
            build_validate_state(_INST, two_pages, 2),
            build_validate_questions(two_pages),
        )
        chunks = chunk_input_rows(_INST, rows, budget_bytes=budget)
        assert len(chunks) >= 3
        # Order preserved; every row exactly once.
        assert [r for c in chunks for r in c.input_rows] == rows
        seen_urls: set[str] = set()
        for c in chunks:
            urls = {r["source_url"] for r in c.input_rows}
            assert not urls & seen_urls  # a page never spans two chunks
            seen_urls |= urls
            assert c.n_input_pages == len(urls)
            assert c.request_bytes <= budget
            assert c.request_bytes == estimate_request_bytes(
                build_validate_state(_INST, c.input_rows, c.n_input_pages),
                build_validate_questions(c.input_rows),
            )

    def test_single_oversize_page_is_its_own_chunk(self):
        from g3o.validate.jev_validate import chunk_input_rows

        rows = [_row("https://small0.gov/", name="A", snippet="a")]
        rows += [_row("https://big.gov/", name=f"B{i}", snippet=f"b{i}") for i in range(8)]
        rows += [_row("https://small1.gov/", name="C", snippet="c")]
        one = chunk_input_rows(_INST, rows[:1], budget_bytes=10**9)[0].request_bytes
        chunks = chunk_input_rows(_INST, rows, budget_bytes=one + 200)
        assert [len(c.input_rows) for c in chunks] == [1, 8, 1]
        assert chunks[1].request_bytes > one + 200

    def test_non_contiguous_page_rows_grouped_in_order(self):
        from g3o.validate.jev_validate import chunk_input_rows

        rows = [
            _row("https://a.gov/", snippet="a1"),
            _row("https://b.gov/", snippet="b1"),
            _row("https://a.gov/", snippet="a2"),
        ]
        chunks = chunk_input_rows(_INST, rows, budget_bytes=1)
        assert [[r["source_snippet"] for r in c.input_rows] for c in chunks] == [
            ["a1", "a2"], ["b1"],
        ]


class TestMergeChunkResponses:
    def _merge(self, parts, n_pages=None):
        from g3o.validate.jev_validate import merge_chunk_responses

        responses = [(_response(rows), len(rows)) for rows in parts]
        return merge_chunk_responses(
            responses,
            n_input_pages=n_pages or sum(len({r["source_url"] for r in p}) for p in parts),
            n_input_rows=sum(len(p) for p in parts),
        )

    def test_exact_name_merge_with_field_fill(self):
        c1 = [_row("https://a.gov/", name="Bot", vendor="unknown",
                   has_risk_assessment="not_documented", tool_name="T1")]
        c2 = [
            _row("https://b.gov/", name="Other", snippet="o"),
            _row("https://c.gov/", name="Bot", vendor="OpenAI",
                 has_risk_assessment="yes", tool_name="T2", confidence="high",
                 uncertainty_flags="date_uncertain", snippet="b"),
        ]
        merged = self._merge([c1, c2])
        assert [a.activity_name for a in merged.activities] == ["Bot", "Other"]
        bot = merged.activities[0]
        assert bot.activity_id == "A1"
        assert bot.vendor == "OpenAI"  # "unknown" filled from later chunk
        assert bot.has_risk_assessment == "yes"  # "not_documented" filled
        assert bot.tool_name == "T1"  # first chunk's real value kept
        assert bot.confidence == "high"
        assert bot.uncertainty_flags == "date_uncertain"
        assert bot.n_sources == 2
        assert merged.activities[1].n_sources == 1

    def test_source_links_renumbered_and_consistent(self):
        c1 = [
            _row("https://a.gov/", name="X", snippet="x"),
            _row("https://n.gov/", evidence="ambiguous", snippet="n"),
        ]
        c2 = [_row("https://b.gov/", name="Y", snippet="y"),
              _row("https://c.gov/", name="X", snippet="x2")]
        merged = self._merge([c1, c2])
        assert [s.source_id for s in merged.sources] == ["S1", "S2", "S3", "S4"]
        links = {s.source_url: s.activity_id for s in merged.sources}
        assert links == {
            "https://a.gov/": "A1", "https://n.gov/": "_NA_",
            "https://b.gov/": "A2", "https://c.gov/": "A1",
        }

    def test_cross_chunk_duplicate_source_dropped(self):
        from g3o.validate.jev_validate import merge_chunk_responses

        c1 = [_row("https://a.gov/", name="X", snippet="dup"),
              _row("https://n.gov/", evidence="ambiguous", snippet="n")]
        c2 = [_row("https://a.gov/", name="X", snippet="dup"),
              _row("https://b.gov/", name="X", snippet="other")]
        merged = merge_chunk_responses(
            [(_response(c1), 2), (_response(c2), 2)], n_input_pages=3, n_input_rows=4
        )
        assert [s.source_url for s in merged.sources] == [
            "https://a.gov/", "https://n.gov/", "https://b.gov/",
        ]
        assert merged.activities[0].n_sources == 2

    def test_has_genai_precedence(self):
        absent = [_row("https://n.gov/", evidence="confirms_absence", snippet="n")]
        unclear = [_row("https://u.gov/", evidence="ambiguous", snippet="u")]
        yes = [_row("https://y.gov/", name="Y", snippet="y")]
        assert self._merge([absent, unclear]).institution.has_genai_activity == "unclear"
        assert self._merge([absent, yes, unclear]).institution.has_genai_activity == "yes"
        absent2 = [_row("https://m.gov/", evidence="confirms_absence", snippet="m")]
        assert self._merge([absent, absent2]).institution.has_genai_activity == "no"

    def test_summary_choice_tie_breaks(self):
        no = [_row("https://n.gov/", evidence="confirms_absence", summary="none here")]
        yes_small = [_row("https://y1.gov/", name="A", summary="small yes")]
        yes_big = [_row("https://y2.gov/", name="B", summary="big yes", snippet="1"),
                   _row("https://y2.gov/", name="B", summary="big yes", snippet="2")]
        yes_other = [_row("https://y3.gov/", name="C", summary="other yes")]
        # has_genai rank beats chunk size and order
        assert self._merge([no, yes_small]).institution.institution_summary == "small yes"
        # rank tie -> chunk with more input rows
        assert self._merge([yes_small, yes_big]).institution.institution_summary == "big yes"
        # rank and size tie -> earlier chunk
        assert (
            self._merge([yes_small, yes_other]).institution.institution_summary
            == "small yes"
        )

    def test_metadata_totals_and_notes(self):
        merged = self._merge(
            [[_row("https://a.gov/", name="A")],
             [_row("https://b.gov/", name="B"), _row("https://c.gov/", name="C")]],
            n_pages=3,
        )
        meta = merged.consolidation_metadata
        assert meta.n_input_pages == 3
        assert meta.n_input_rows == 3
        assert meta.notes == (
            "Consolidated via jev decision model; validate_oversize_split: 2 chunks"
        )


class TestRunValidateJevOversize:
    """Stage 6: a 400 max_tokens_exceeded falls back to chunked validation."""

    def _run(self, tmp_path, rows, fake_ask, budget):
        from unittest.mock import patch

        from g3o.common import attrition
        from g3o.common.credentials import Credentials, resolve
        from g3o.common.paths import institution_dir
        from g3o.run.presweep.stage_validate import _run_validate_jev

        attrition._reset_cache()
        credentials = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        institution_dir(tmp_path, _INST["institution_id"]).mkdir(parents=True)
        n_pages = len({r["source_url"] for r in rows})
        with (
            patch(
                "g3o.validate.consolidate.assemble_per_institution_inputs",
                return_value=[(_INST, rows, n_pages)],
            ),
            patch("g3o.validate.jev_validate.CHUNK_BUDGET_BYTES", budget),
            patch("g3o.run.presweep.jev_stage_runner.ask", side_effect=fake_ask),
        ):
            return _run_validate_jev(
                tmp_path, [_INST], model="jev-1.13.0", credentials=credentials,
                concurrency=1,
            )

    def _rows(self):
        return [
            _row(f"https://p{p}.gov/", name=f"Act {p % 2}", snippet=f"s{p}-{r}")
            for p in range(4)
            for r in range(2)
        ]

    def _budget(self, rows):
        from g3o.validate.jev_validate import estimate_request_bytes

        page = rows[:2]
        return estimate_request_bytes(
            build_validate_state(_INST, page, 1), build_validate_questions(page)
        ) + 50

    def _ledger(self, run_dir):
        from g3o.common import attrition

        return attrition.read_records(run_dir)

    def test_oversize_400_splits_and_writes_one_merged_artifact(self, tmp_path):
        import json

        from g3o.common.paths import institution_dir
        from g3o.common.run_state import done_path

        rows = self._rows()
        sent = []

        def fake_ask(state, questions, *, client, model):
            sent.append(state["n_input_rows"])
            if state["n_input_rows"] > 2:
                raise _oversize_error()
            return _empty_result(tokens=100)

        summary = self._run(tmp_path, rows, fake_ask, self._budget(rows))
        assert sent == [8, 2, 2, 2, 2]  # full request first, then one per page
        assert summary["n_consolidated"] == 1
        assert summary["n_failed"] == 0
        assert summary["n_oversize_split"] == 1
        payload = json.loads(
            (institution_dir(tmp_path, "INST-OVR") / "6_validate.json").read_text(
                encoding="utf-8"
            )
        )
        resp = ConsolidatedInstitutionResponse.model_validate(payload)
        assert [a.activity_name for a in resp.activities] == ["Act 0", "Act 1"]
        assert [a.n_sources for a in resp.activities] == [4, 4]
        assert resp.consolidation_metadata.n_input_rows == 8
        assert resp.consolidation_metadata.n_input_pages == 4
        assert "validate_oversize_split: 4 chunks" in resp.consolidation_metadata.notes
        recs = self._ledger(tmp_path)
        assert [r["reason"] for r in recs] == ["validate_oversize_split"]
        assert recs[0]["stage"] == "validate"
        assert recs[0]["detail"].startswith("n_chunks=4; depth=1; chunk_bytes=[")
        # Usage of all four chunk requests reaches the stage totals.
        done = json.loads(done_path(tmp_path, "validate").read_text(encoding="utf-8"))
        assert done["usage"]["prompt_tokens"] == 400
        assert done["usage"]["completion_tokens"] == 4

    def test_other_400_does_not_split(self, tmp_path):
        import httpx2
        import typesafe_sdk as ts

        rows = self._rows()
        calls = []

        def fake_ask(state, questions, *, client, model):
            calls.append(1)
            raise ts.TypeSafeBadRequestError(
                400, {"detail": {"error_type": "invalid_question"}}, httpx2.Headers()
            )

        summary = self._run(tmp_path, rows, fake_ask, self._budget(rows))
        assert len(calls) == 1
        assert summary["n_failed"] == 1
        assert summary["n_oversize_split"] == 0
        assert [r["reason"] for r in self._ledger(tmp_path)] == ["jev_request_failed"]

    def test_generic_error_does_not_split(self, tmp_path):
        rows = self._rows()
        calls = []

        def fake_ask(state, questions, *, client, model):
            calls.append(1)
            raise RuntimeError("boom")

        summary = self._run(tmp_path, rows, fake_ask, self._budget(rows))
        assert len(calls) == 1
        assert summary["n_failed"] == 1
        assert [r["reason"] for r in self._ledger(tmp_path)] == ["jev_request_failed"]

    def test_chunk_failure_fails_the_institution(self, tmp_path):
        from g3o.common.paths import institution_dir

        rows = self._rows()
        n = 0

        def fake_ask(state, questions, *, client, model):
            nonlocal n
            n += 1
            if n == 1:
                raise _oversize_error()
            if n == 3:
                raise RuntimeError("chunk boom")
            return _empty_result()

        summary = self._run(tmp_path, rows, fake_ask, self._budget(rows))
        assert n == 3  # stops at the failing chunk
        assert summary["n_failed"] == 1
        assert summary["n_consolidated"] == 0
        assert not (institution_dir(tmp_path, "INST-OVR") / "6_validate.json").exists()
        recs = self._ledger(tmp_path)
        assert [r["reason"] for r in recs] == [
            "validate_oversize_split", "jev_request_failed",
        ]
        assert "chunk boom" in recs[1]["detail"]

    def test_single_page_institution_is_not_split(self, tmp_path):
        rows = [_row("https://one.gov/", snippet=f"s{i}") for i in range(4)]
        calls = []

        def fake_ask(state, questions, *, client, model):
            calls.append(1)
            raise _oversize_error()

        summary = self._run(tmp_path, rows, fake_ask, 1)
        assert len(calls) == 1
        assert summary["n_failed"] == 1
        assert [r["reason"] for r in self._ledger(tmp_path)] == ["jev_request_failed"]

    # -- forced split and recursive re-split (coordinator refinement) --------

    def _pages_rows(self, n_pages, rows_per_page=1):
        return [
            _row(f"https://q{p}.gov/", name="Act", snippet=f"s{p}-{r}")
            for p in range(n_pages)
            for r in range(rows_per_page)
        ]

    def test_forced_split_when_estimate_under_budget(self, tmp_path):
        rows = self._pages_rows(4)
        sent = []

        def fake_ask(state, questions, *, client, model):
            sent.append(state["n_input_rows"])
            if len(sent) == 1:
                raise _oversize_error()
            return _empty_result()

        summary = self._run(tmp_path, rows, fake_ask, 10**9)
        assert summary["n_consolidated"] == 1
        assert summary["n_oversize_split"] == 1
        assert sent[0] == 4 and len(sent) >= 3  # >= 2 chunks despite the budget
        assert sum(sent[1:]) == 4
        assert "depth=1" in self._ledger(tmp_path)[0]["detail"]

    def test_chunk_oversize_is_resplit(self, tmp_path):
        rows = self._pages_rows(8, rows_per_page=2)
        sent = []

        def fake_ask(state, questions, *, client, model):
            sent.append(state["n_input_pages"])
            if state["n_input_pages"] > 1:
                raise _oversize_error()
            return _empty_result(tokens=7)

        summary = self._run(tmp_path, rows, fake_ask, 10**9)
        assert summary["n_consolidated"] == 1
        assert summary["n_failed"] == 0
        assert sent.count(1) == 8  # every page answered exactly once
        assert any(1 < n < 8 for n in sent)  # a multi-page chunk was re-split
        detail = self._ledger(tmp_path)[0]["detail"]
        assert "n_chunks=8" in detail
        assert "depth=2" in detail

    def test_depth_cap_fails_the_institution(self, tmp_path):
        from g3o.common.paths import institution_dir
        from g3o.validate.jev_validate import MAX_SPLIT_DEPTH

        assert MAX_SPLIT_DEPTH == 3
        rows = self._pages_rows(64)
        sent = []

        def fake_ask(state, questions, *, client, model):
            sent.append(state["n_input_rows"])
            if state["n_input_rows"] > 1:
                raise _oversize_error()
            return _empty_result()

        summary = self._run(tmp_path, rows, fake_ask, 10**9)
        assert summary["n_failed"] == 1
        assert min(sent) >= 2  # never split past depth 3 down to single pages
        assert not (institution_dir(tmp_path, "INST-OVR") / "6_validate.json").exists()
        recs = self._ledger(tmp_path)
        assert [r["reason"] for r in recs] == [
            "validate_oversize_split", "jev_request_failed",
        ]
        assert "depth=3" in recs[0]["detail"]

    def test_single_page_chunk_still_oversize_fails(self, tmp_path):
        rows = [_row("https://small.gov/", name="Act", snippet="a")]
        rows += [_row("https://big.gov/", name="Act", snippet=f"b{i}") for i in range(3)]
        sent = []

        def fake_ask(state, questions, *, client, model):
            sent.append(state["n_input_rows"])
            if any(r["source_url"] == "https://big.gov/" for r in state["input_rows"]):
                raise _oversize_error()
            return _empty_result()

        summary = self._run(tmp_path, rows, fake_ask, 10**9)
        assert summary["n_failed"] == 1
        assert sent == [4, 1, 3]  # full, small page, big page (not re-splittable)
        recs = self._ledger(tmp_path)
        assert [r["reason"] for r in recs] == [
            "validate_oversize_split", "jev_request_failed",
        ]
        assert "depth=1" in recs[0]["detail"]
