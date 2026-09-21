"""Tests for the TypeSafe jev client seam (g3o.common.jev_client).

Covers:
- JevAnswer / JevResult parsing from SDK answer types
- client_from_credentials builds a client with the right key
- ask() submits and parses a response
- serialize_state produces canonical JSON
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typesafe_sdk as ts

from g3o.common.credentials import Credentials, ResolvedCredentials, resolve
from g3o.common.jev_client import (
    DEFAULT_JEV_MODEL,
    JevAnswer,
    JevResult,
    _parse_answer,
    ask,
    client_from_credentials,
    serialize_state,
)


# ---------------------------------------------------------------------------
# JevAnswer parsing
# ---------------------------------------------------------------------------


class TestParseAnswer:
    """_parse_answer converts SDK answer types to JevAnswer."""

    def test_choice_answer(self):
        sdk_answer = ts.ChoiceAnswer(
            type="choice",
            choice="u0",
            confidence=0.85,
            probabilities={"u0": 0.85, "u1": 0.10, "none": 0.05},
        )
        result = _parse_answer("official_site", sdk_answer)
        assert result.question_id == "official_site"
        assert result.type == "choice"
        assert result.choice == "u0"
        assert result.confidence == 0.85
        assert result.probabilities == {"u0": 0.85, "u1": 0.10, "none": 0.05}
        assert result.noul is None
        assert result.score is None

    def test_noul_answer(self):
        sdk_answer = ts.NoulAnswer(type="noul", noul=0.92)
        result = _parse_answer("keep_u0", sdk_answer)
        assert result.question_id == "keep_u0"
        assert result.type == "noul"
        assert result.noul == 0.92
        assert result.choice is None
        assert result.score is None
        assert result.confidence is None

    def test_score_answer(self):
        sdk_answer = ts.ScoreAnswer(
            type="score",
            score=2.0,
            confidence=0.75,
            legend={0: "low", 1: "medium", 2: "high", 3: "very high"},
            probabilities={0: 0.05, 1: 0.20, 2: 0.75},
        )
        result = _parse_answer("site_confidence", sdk_answer)
        assert result.question_id == "site_confidence"
        assert result.type == "score"
        assert result.score == 2.0
        assert result.confidence == 0.75
        assert result.probabilities == {0: 0.05, 1: 0.20, 2: 0.75}
        assert result.choice is None
        assert result.noul is None

    def test_unknown_answer_type_raises(self):
        with pytest.raises(TypeError, match="unknown jev answer type"):
            _parse_answer("q1", "not an answer")


# ---------------------------------------------------------------------------
# client_from_credentials
# ---------------------------------------------------------------------------


class TestClientFromCredentials:
    """client_from_credentials builds a TypeSafeClient with the right key."""

    def test_builds_client_with_key(self):
        creds = resolve(
            Credentials(typesafe_api_key="test-key-123"),
            env={"TYPESAFE_API_KEY": "test-key-123"},
        )
        client = client_from_credentials(creds)
        assert isinstance(client, ts.TypeSafeClient)

    def test_raises_without_key(self):
        creds = resolve(Credentials(), env={})
        with pytest.raises(RuntimeError, match="TypeSafe API key is not set"):
            client_from_credentials(creds)

    def test_model_override(self):
        creds = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        client = client_from_credentials(creds, model="jev-1.13.0")
        assert isinstance(client, ts.TypeSafeClient)


# ---------------------------------------------------------------------------
# ask()
# ---------------------------------------------------------------------------


class TestAsk:
    """ask() submits a request and parses the response."""

    def test_ask_parses_response(self):
        # Mock the SDK client
        mock_client = MagicMock(spec=ts.TypeSafeClient)
        mock_response = MagicMock()
        mock_response.model = "jev-1.13.0"
        mock_response.request_id = "req-123"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 0
        mock_response.answers = {
            "q1": ts.ChoiceAnswer(
                type="choice",
                choice="a",
                confidence=0.9,
                probabilities={"a": 0.9, "b": 0.1},
            ),
            "q2": ts.NoulAnswer(type="noul", noul=0.8),
        }
        mock_client.system_one.return_value = mock_response

        questions = {
            "q1": ts.Choice(instructions="Pick one", criteria={"a": "A", "b": "B"}),
            "q2": ts.Noul(instructions="Is it true?"),
        }
        result = ask({"state": "data"}, questions, client=mock_client)

        assert isinstance(result, JevResult)
        assert result.response_model == "jev-1.13.0"
        assert result.request_id == "req-123"
        assert result.input_tokens == 100
        assert result.output_tokens == 0
        assert len(result.answers) == 2
        assert result.answers["q1"].choice == "a"
        assert result.answers["q2"].noul == 0.8

    def test_ask_with_model_override(self):
        mock_client = MagicMock(spec=ts.TypeSafeClient)
        mock_response = MagicMock()
        mock_response.model = "jev-1.13.0"
        mock_response.request_id = "req-456"
        mock_response.usage.input_tokens = 50
        mock_response.usage.output_tokens = 0
        mock_response.answers = {}
        mock_client.system_one.return_value = mock_response

        ask({}, {}, client=mock_client, model="jev-1.13.0")
        mock_client.system_one.assert_called_once()
        call_kwargs = mock_client.system_one.call_args.kwargs
        assert call_kwargs["model"] == "jev-1.13.0"


# ---------------------------------------------------------------------------
# serialize_state
# ---------------------------------------------------------------------------


class TestSerializeState:
    """serialize_state produces canonical JSON for hashing."""

    def test_canonical_json(self):
        state = {"b": 2, "a": 1}
        result = serialize_state(state)
        assert result == '{"a": 1, "b": 2}'

    def test_unicode_preserved(self):
        state = {"name": "日本語"}
        result = serialize_state(state)
        assert "日本語" in result
        assert "\\u" not in result


# ---------------------------------------------------------------------------
# Integration with credentials
# ---------------------------------------------------------------------------


class TestCredentialsIntegration:
    """jev_client integrates with the credentials module."""

    def test_typesafe_key_resolved(self):
        creds = resolve(
            Credentials(typesafe_api_key="explicit-key"),
            env={"TYPESAFE_API_KEY": "env-key"},
        )
        assert creds.typesafe_api_key == "explicit-key"
        assert creds.typesafe_source == "explicit"

    def test_typesafe_key_from_env(self):
        creds = resolve(Credentials(), env={"TYPESAFE_API_KEY": "env-key"})
        assert creds.typesafe_api_key == "env-key"
        assert creds.typesafe_source == "env"

    def test_typesafe_fingerprint(self):
        creds = resolve(
            Credentials(typesafe_api_key="test-key"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        assert creds.typesafe_fingerprint is not None
        assert len(creds.typesafe_fingerprint) == 8

    def test_has_typesafe(self):
        creds_with = resolve(
            Credentials(typesafe_api_key="key"),
            env={"TYPESAFE_API_KEY": "key"},
        )
        creds_without = resolve(Credentials(), env={})
        assert creds_with.has_typesafe is True
        assert creds_without.has_typesafe is False

    def test_telemetry_includes_typesafe(self):
        creds = resolve(
            Credentials(typesafe_api_key="test-key", label="test-label"),
            env={"TYPESAFE_API_KEY": "test-key"},
        )
        telemetry = creds.telemetry()
        assert "typesafe" in telemetry
        assert telemetry["typesafe"]["source"] == "explicit"
        assert telemetry["typesafe"]["fingerprint"] is not None
        assert telemetry["typesafe"]["label"] == "test-label"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Module constants are set correctly."""

    def test_default_jev_model(self):
        assert DEFAULT_JEV_MODEL == "jev-1.13.0"
