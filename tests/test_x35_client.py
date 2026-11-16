"""The X35 entailment client (PI ruling 139 a) and its two gates. Fake SDK clients only."""
from __future__ import annotations

import json
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from g3o.common import support_check as sc
from g3o.common.support_check import Entailment, SupportGateError
from g3o.extract import x35_client as xc

USAGE = {"input_tokens": 300, "output_tokens": 40, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
QUESTION = "Does the text state that CivicBot is a chatbot?"
WINDOW = "The city launched CivicBot, a chatbot {with braces} for residents."


def _message(payload: Any, *, stop: str = "end_turn", usage: dict | None = None) -> SimpleNamespace:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(model="claude-haiku-5-5", id="msg-1", _request_id="req-1", stop_reason=stop,
                           usage=dict(USAGE if usage is None else usage),
                           content=[{"type": "thinking", "thinking": "..."}, {"type": "text", "text": text}])


class FakeSDK:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.params: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params: Any) -> Any:
        self.params.append(params)
        return self.replies.pop(0)


def _client(*replies: Any) -> tuple[xc.AnthropicX35Client, FakeSDK]:
    sdk = FakeSDK(*replies)
    return xc.AnthropicX35Client(sdk, model="claude-haiku-5-5", probability_source="stated"), sdk


def test_gates_are_unruled_by_default():
    assert xc.X35_PROBABILITY_SOURCE is None  # new PI question: the probability source
    assert xc.X35_PROBABILITY_SOURCES == frozenset({"stated"})
    assert xc.X35_EFFORT == "medium"
    assert isinstance(xc.X35_MAX_TOKENS, int) and xc.X35_MAX_TOKENS > 0


def test_params_shape_model_schema_effort_and_exact_question():
    client, sdk = _client(_message({"answer": "true", "probability": 0.93}))
    client(QUESTION, WINDOW)
    (params,) = sdk.params
    assert params["model"] == "claude-haiku-5-5"
    assert params["max_tokens"] == xc.X35_MAX_TOKENS
    assert params["system"] == xc.X35_SYSTEM_DRAFT
    assert params["output_config"] == {"effort": xc.X35_EFFORT,
                                       "format": {"type": "json_schema", "schema": xc.X35_OUTPUT_SCHEMA}}
    assert xc.X35_OUTPUT_SCHEMA["properties"]["answer"]["enum"] == ["true", "false"]
    assert set(xc.X35_OUTPUT_SCHEMA["required"]) == {"answer", "probability"}
    (msg,) = params["messages"]
    assert msg["role"] == "user"
    assert msg["content"] == xc.X35_USER_TEMPLATE_DRAFT.format(text=WINDOW, question=QUESTION)
    assert msg["content"].endswith("\n\n" + QUESTION)  # the question exactly as given
    assert WINDOW in msg["content"]  # the window whole, never truncated
    assert not any(k in params for k in ("thinking", "temperature", "top_p"))


def test_model_is_the_one_passed_and_required():
    client, sdk = _client(_message({"answer": "false", "probability": 0.7}))
    client2 = xc.AnthropicX35Client(sdk, model="pinned-x35", probability_source="stated")
    assert client2.params(QUESTION, WINDOW)["model"] == "pinned-x35"
    with pytest.raises(ValueError, match="x35 model"):
        xc.AnthropicX35Client(sdk, model="", probability_source="stated")
    with pytest.raises(ValueError, match="not implemented"):
        xc.AnthropicX35Client(sdk, model="m", probability_source="logprobs")
    with pytest.raises(ValueError, match="injected"):
        xc.AnthropicX35Client(None, model="m", probability_source="stated")
    assert "key" not in repr(client).lower()


@pytest.mark.parametrize("answer,prob,expected", [
    ("true", 0.93, Entailment("true", 0.93)),
    ("false", 0.81, Entailment("false", 0.81)),
    ("true", 1, Entailment("true", 1.0)),
    ("true", 0, Entailment("true", 0.0)),
])
def test_parses_answer_and_stated_probability(answer, prob, expected):
    client, _ = _client(_message({"answer": answer, "probability": prob}))
    ent, usage = client.entail_with_usage(QUESTION, WINDOW)
    assert ent == expected and usage == USAGE


@pytest.mark.parametrize("payload", [
    {"answer": "true"},
    {"answer": "true", "probability": None},
    {"answer": "true", "probability": "0.9"},
    {"answer": "true", "probability": True},
    {"answer": "true", "probability": 1.2},
    {"answer": "true", "probability": -0.1},
    '{"answer": "true", "probability": NaN}',
])
def test_missing_or_invalid_probability_is_none_and_fails_the_bar(payload):
    client, _ = _client(_message(payload))
    ent = client(QUESTION, WINDOW)
    assert ent == Entailment("true", None)
    flags: list[str] = []
    assert sc._entailment_fails(ent, 0.8, flags) is True
    assert flags == [sc.ENTAILMENT_PROBABILITY_UNAVAILABLE]


@pytest.mark.parametrize("reply,match", [
    (_message({"answer": "maybe", "probability": 0.9}), "'true' or 'false'"),
    (_message("not json"), "not JSON"),
    (_message([1, 2]), "not a JSON object"),
    (_message({"answer": "true", "probability": 0.9}, stop="refusal"), "refusal"),
    (_message({"answer": "true", "probability": 0.9}, stop="max_tokens"), "max_tokens"),
])
def test_no_usable_answer_raises_with_the_billed_usage(reply, match):
    client, _ = _client(reply)
    with pytest.raises(xc.X35ResponseError, match=match) as err:
        client(QUESTION, WINDOW)
    assert err.value.usage == USAGE


def _settings(model: str = "claude-haiku-5-5") -> SimpleNamespace:
    return SimpleNamespace(x35_model=model)


def _creds(key: str | None = "anthropic-test") -> SimpleNamespace:
    return SimpleNamespace(anthropic_api_key=key)


def test_x35_entail_fn_returns_the_refusing_stub_while_the_source_is_unruled():
    from g3o.run.presweep import v27_entry

    fn = v27_entry.x35_entail_fn(_settings(), _creds())
    assert fn is sc.run_entailment
    with pytest.raises(SupportGateError, match="probability source"):
        fn(QUESTION, WINDOW)


def test_x35_entail_fn_returns_the_lazy_client_once_the_source_is_stated(monkeypatch):
    from g3o.run.presweep import v27_entry

    built: list[dict[str, Any]] = []
    sdk = FakeSDK(_message({"answer": "true", "probability": 0.9}))

    class Anthropic:
        def __init__(self, **kw: Any) -> None:
            built.append(kw)
            self.messages = sdk.messages

    module = types.ModuleType("anthropic")
    module.Anthropic = Anthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", module)
    monkeypatch.setattr(xc, "X35_PROBABILITY_SOURCE", "stated")

    fn = v27_entry.x35_entail_fn(_settings("pinned-x35"), _creds())
    assert isinstance(fn, v27_entry.LazyX35) and fn is not sc.run_entailment
    assert not fn.constructed and built == []  # nothing built before the first call
    assert "anthropic-test" not in repr(fn)
    ent, usage = fn.entail_with_usage(QUESTION, WINDOW)
    assert ent == Entailment("true", 0.9) and usage == USAGE
    assert built == [{"api_key": "anthropic-test", "max_retries": 0}]  # PI ruling 135 a
    assert sdk.params[0]["model"] == "pinned-x35"  # the pinned x35_model (RC-D-033 C1 a)


def test_journal_records_x35_usage_per_request_and_replays_without_it(tmp_path):
    from g3o.run.presweep.stage_validate_v27 import RequestJournal

    path = tmp_path / "journal.jsonl"
    journal = RequestJournal(path)
    _, wrap_entail = journal.seams({"x35_model": "claude-haiku-5-5"})
    client, _ = _client(_message({"answer": "true", "probability": 0.9}),
                        _message({"answer": "true", "probability": 0.9}, stop="refusal",
                                 usage={**USAGE, "output_tokens": 5}))
    entail = wrap_entail(client)
    assert entail(QUESTION, WINDOW) == Entailment("true", 0.9)
    with pytest.raises(xc.X35ResponseError):
        entail(QUESTION, WINDOW + " more")
    assert journal.x35_usages() == [USAGE, {**USAGE, "output_tokens": 5}]
    assert journal.usage()["x35_calls"] == 1 and journal.usage()["x35_failed"] == 1
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["kind"] == "x35" and entries[0]["response"] == {"value": "true", "probability": 0.9,
                                                                       "usage": USAGE}

    reloaded = RequestJournal(path, read_only=True)
    _, wrap_again = reloaded.seams({"x35_model": "claude-haiku-5-5"})

    def no_call(*_a: Any) -> Entailment:
        raise AssertionError("a recorded X35 answer must be replayed")

    assert wrap_again(no_call)(QUESTION, WINDOW) == Entailment("true", 0.9)  # usage key not passed on
    assert reloaded.x35_usages() == [USAGE, {**USAGE, "output_tokens": 5}]


def test_journal_of_a_plain_entail_fn_records_no_usage(tmp_path):
    from g3o.run.presweep.stage_validate_v27 import RequestJournal

    path = tmp_path / "journal.jsonl"
    journal = RequestJournal(path)
    _, wrap_entail = journal.seams({"x35_model": "fake"})
    assert wrap_entail(lambda q, t: Entailment("false", 0.95))(QUESTION, WINDOW) == Entailment("false", 0.95)
    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["response"] == {"value": "false", "probability": 0.95}
    assert journal.x35_usages() == [None]


def test_journal_marks_a_responseless_x35_failure_and_does_not_price_it(tmp_path):
    """Review O2 M1 (PI ruling 131.1 b, as for the extractor): an exception raised before any response
    came back is counted in ``x35_failed`` but marked ``usage_absent: no_response`` and skipped by
    ``x35_usages``, so it is neither priced nor makes the X35 part unpriced. A billed failure is kept."""
    from g3o.run.presweep.stage_validate_v27 import RequestJournal

    path = tmp_path / "journal.jsonl"
    journal = RequestJournal(path)
    _, wrap_entail = journal.seams({"x35_model": "claude-haiku-5-5"})

    def transport_error(*_a: Any) -> Entailment:
        raise ConnectionError("simulated connection reset before any response")

    with pytest.raises(ConnectionError):
        wrap_entail(transport_error)(QUESTION, WINDOW)
    client, _ = _client(_message({"answer": "true", "probability": 0.9}, stop="refusal"))
    with pytest.raises(xc.X35ResponseError):
        wrap_entail(client)(QUESTION, WINDOW + " other")
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [e["kind"] for e in entries] == ["x35_failed", "x35_failed"]
    assert entries[0]["response"]["usage_absent"] == "no_response" and "usage" not in entries[0]["response"]
    assert "usage_absent" not in entries[1]["response"] and entries[1]["response"]["usage"] == USAGE
    assert journal.usage()["x35_failed"] == 2  # still counted
    assert journal.x35_usages() == [USAGE]  # the responseless failure is not priced (never $0, never None)
    assert RequestJournal(path, read_only=True).x35_usages() == [USAGE]
