"""Lossless per-code records; no provider calls or consumer wiring (T-027).

``from_jev`` captures one actual answer from one actual result/chunk. Pass the
signed item rule for release-2.7 categorical answers. Without a rule this is a
raw legacy answer, and ``downgraded`` is None (not a passed confidence check).
Noul's probability is type-not-applicable, distinct from a missing categorical
distribution. Multi-select questions use one record per selected code, never a
synthetic joint probability; consumers own their actual question expansion.

Persist ``to_json``/``records_to_json`` in the per-institution artifact. The Q2a
``storage_projection`` is deliberately smaller: it references an EXISTING
support for the ORIGINAL code. It omits final_value, cause, generic confidence,
rule and setup linkage; callers MUST retain the complete companion record.
It neither fabricates a support nor rewrites a support/value to pass validation.
The owning T-021/023/026/028 cards bind the two artifacts and any downstream
support-status updates; no integrated writer/runtime readiness is implied.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, fields
from typing import Any

import yaml

from g3o.common.jev_client import JevResult

FORMAT = "g3o-coder-record-v1"
NOT_APPLICABLE = "coder_not_applicable"
_PROVIDER_FIELDS = ("configured_model", "actual_response_model", "request_id")
_STORAGE_FIELDS = (
    "support_id", "observation_id", "item_id", "item_part", "coder_type",
    "coder_version", "configured_model", "actual_response_model", "request_id",
    "question_set_version", "chunk_id", "chosen_value",
)


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be supplied from actual provenance")


def _probability(value: Any) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("probability/confidence must be finite and between 0 and 1")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class ClassifierRule:
    """One explicit signed item/part mapping, never a universal fallback."""

    item_id: str
    item_part: str | None
    codebook_sha256: str
    downgrade_target: str
    threshold: float = 0.8

    def __post_init__(self) -> None:
        _text(self.item_id, "rule item_id")
        if self.item_part is not None:
            _text(self.item_part, "rule item_part")
        if not re.fullmatch(r"[0-9a-f]{64}", self.codebook_sha256):
            raise ValueError("rule requires exact codebook SHA256")
        _text(self.downgrade_target, f"{self.item_id}: signed downgrade mapping")
        if self.downgrade_target == "none":
            raise ValueError(f"{self.item_id}: no signed applicable downgrade mapping")
        if self.threshold != 0.8:
            raise ValueError("approved chosen-answer probability bar is 0.8")
        if self.downgrade_target == "tag_only" and self.item_id != "core.page_verdict":
            raise ValueError("tag_only is the signed page-verdict exception")
        if self.item_id == "core.page_verdict" and self.downgrade_target != "tag_only":
            raise ValueError("page verdict must be retained with a downgrade tag")


def load_classifier_rules(codebook: bytes, *, expected_sha256: str) -> dict[tuple[str, str | None], ClassifierRule]:
    """Read mappings from exact caller-pinned signed bytes, not local defaults.

    The caller obtains expected_sha256 from the approved instrument/handoff,
    not by blessing whichever file is on disk. No questions or rules are edited.
    """
    digest = hashlib.sha256(codebook).hexdigest()
    if digest != expected_sha256:
        raise ValueError("codebook does not match the approved SHA256")
    items = yaml.safe_load(codebook)["items"]
    rules = {}
    for item_id, item in items.items():
        if item.get("coder") != "classifier":
            continue
        if item.get("threshold") != {"metric": "chosen_answer_probability", "bar": 0.8}:
            raise ValueError(f"{item_id}: missing signed chosen-answer threshold")
        values = item.get("values", {})
        parts = values.get("parts", [None]) if isinstance(values, dict) else [None]
        for part in parts:
            rules[item_id, part] = ClassifierRule(
                item_id, part, digest, item.get("downgrade_target"),
            )
    return rules


@dataclass(frozen=True)
class CoderRecord:
    """Raw response plus explicit context; derived facts cannot contradict it.

    Required unknown response/model/request/version/setup inputs are refused.
    Non-provider mechanical/derived records instead carry typed nulls and an
    actual rule reference. A nonempty string is not proof of provenance: the
    caller must supply observed metadata, never a current-default substitute.
    """

    item_id: str
    item_part: str | None
    question_id: str | None
    support_id: str | None
    observation_id: str | None
    chunk_id: str | None
    coder_type: str
    coder_version: str
    configured_model: str | None
    actual_response_model: str | None
    request_id: str | None
    question_set_version: str
    setup_pointer: str
    answer_type: str
    chosen_value: Any
    confidence: float | None
    probability_distribution: dict[str | int, float] | None
    rule_reference: str | None = None
    classifier_rule: ClassifierRule | None = None

    def __post_init__(self) -> None:
        for name in ("item_id", "coder_version", "question_set_version"):
            _text(getattr(self, name), name)
        if not isinstance(self.setup_pointer, str) or not re.fullmatch(r"[0-9a-f]{64}", self.setup_pointer):
            raise ValueError("setup_pointer must be an actual instrument payload SHA256")
        for name in ("item_part", "question_id", "support_id", "observation_id", "chunk_id", "rule_reference"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        if self.coder_type not in {"classifier", "quote_step", "detector", "mechanical", "derived"}:
            raise ValueError("unknown automated coder type")
        mechanical = self.coder_type in {"mechanical", "derived"}
        if mechanical:
            if any(getattr(self, n) is not None for n in _PROVIDER_FIELDS):
                raise ValueError("mechanical provenance must use typed null provider fields")
            if self.confidence is not None or self.probability_distribution is not None:
                raise ValueError("mechanical probability is not applicable")
            _text(self.rule_reference, "mechanical rule_reference")
            if self.classifier_rule is not None or self.answer_type != "rule":
                raise ValueError("mechanical records do not apply classifier downgrade rules")
        else:
            for name in _PROVIDER_FIELDS:
                _text(getattr(self, name), name)
        if self.confidence is not None:
            _probability(self.confidence)
        if self.probability_distribution is not None:
            if not isinstance(self.probability_distribution, dict):
                raise ValueError("probability_distribution must be a mapping or None")
            for key, value in self.probability_distribution.items():
                if type(key) not in (str, int):
                    raise ValueError("distribution keys must be choice strings or score integers")
                _probability(value)
            # Detach caller-owned mutable input; serialization validates again.
            object.__setattr__(self, "probability_distribution", dict(self.probability_distribution))
        if self.answer_type == "choice":
            _text(self.chosen_value, "chosen choice")
            if self.probability_distribution is not None and any(type(k) is not str for k in self.probability_distribution):
                raise ValueError("choice distribution requires string keys")
        elif self.answer_type in {"noul", "score"}:
            if type(self.chosen_value) not in (int, float) or not math.isfinite(self.chosen_value):
                raise ValueError("numeric answer must be finite")
            if self.answer_type == "noul":
                _probability(self.chosen_value)
                if self.probability_distribution is not None or self.confidence is not None:
                    raise ValueError("Noul does not carry a distribution or confidence")
            elif self.probability_distribution is not None and any(type(k) is not int for k in self.probability_distribution):
                raise ValueError("score distribution requires integer keys")
        elif self.answer_type not in {"rule", "extracted", "detected"}:
            raise ValueError("unknown answer type")
        if self.coder_type == "classifier" and self.answer_type not in {"choice", "noul", "score"}:
            raise ValueError("classifier requires a typed jev answer")
        if self.classifier_rule is not None:
            if self.coder_type != "classifier" or self.answer_type != "choice":
                raise ValueError("signed r11 questions are categorical, not Noul/Score")
            if (self.item_id, self.item_part) != (self.classifier_rule.item_id, self.classifier_rule.item_part):
                raise ValueError("signed downgrade rule belongs to a different item/part")
        # Reject non-JSON output (including NaN) and detach nested chosen values.
        object.__setattr__(self, "chosen_value", json.loads(_json(self.chosen_value)))

    @classmethod
    def from_jev(cls, result: JevResult, *, question_id: str, **context: Any) -> CoderRecord:
        """Capture exactly this request's answer and actual response metadata."""
        if question_id not in result.answers:
            raise ValueError(f"missing answer: {question_id}")
        answer = result.answers[question_id]
        if answer.question_id != question_id or answer.type not in {"choice", "noul", "score"}:
            raise ValueError("answer identity/type mismatch")
        slots = {"choice": answer.choice, "noul": answer.noul, "score": answer.score}
        if slots[answer.type] is None or any(v is not None for k, v in slots.items() if k != answer.type):
            raise ValueError("answer must have exactly its declared typed value")
        return cls(question_id=question_id, coder_type="classifier", answer_type=answer.type,
                   chosen_value=slots[answer.type], confidence=answer.confidence,
                   probability_distribution=answer.probabilities,
                   actual_response_model=result.response_model, request_id=result.request_id,
                   **context)

    @property
    def probability_status(self) -> str:
        if self.coder_type in {"mechanical", "derived"}:
            return NOT_APPLICABLE
        if self.answer_type == "noul":
            return "answer_type_not_applicable"
        if self.answer_type != "choice" and self.answer_type != "score":
            return "answer_type_not_applicable"
        if self.probability_distribution is None:
            return "distribution_unavailable"
        if self.chosen_value not in self.probability_distribution:
            return "chosen_answer_unavailable"
        return "available"

    @property
    def chosen_answer_probability(self) -> float | None:
        if self.probability_status != "available":
            return None
        return self.probability_distribution[self.chosen_value]

    @property
    def downgrade_cause(self) -> str | None:
        if self.classifier_rule is None:
            return None
        if self.probability_status != "available":
            return self.probability_status
        if self.chosen_answer_probability < self.classifier_rule.threshold:
            return "below_threshold"
        return None

    @property
    def downgraded(self) -> bool | None:
        if self.classifier_rule is None:
            return None
        return self.downgrade_cause is not None

    @property
    def final_value(self) -> Any:
        if self.downgraded and self.classifier_rule.downgrade_target != "tag_only":
            return self.classifier_rule.downgrade_target
        return self.chosen_value

    def to_dict(self) -> dict[str, Any]:
        self.__post_init__()
        data = asdict(self)
        # JSON object keys cannot losslessly represent score integers. Encode
        # the full distribution as ordered [key, probability] pairs on this wire.
        data["probability_distribution"] = None if self.probability_distribution is None else list(map(list, self.probability_distribution.items()))
        data.update(format=FORMAT, chosen_answer_probability=self.chosen_answer_probability,
                    probability_status=self.probability_status, downgraded=self.downgraded,
                    downgrade_cause=self.downgrade_cause, final_value=self.final_value)
        return data

    def to_json(self) -> str:
        return _json(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoderRecord:
        if not isinstance(data, dict):
            raise ValueError("record must be a JSON object")
        derived = {"format", "chosen_answer_probability", "probability_status", "downgraded", "downgrade_cause", "final_value"}
        if set(data) != {f.name for f in fields(cls)} | derived:
            raise ValueError("unsupported record format or fields")
        data = dict(data)
        computed = {k: data.pop(k) for k in ("chosen_answer_probability", "probability_status", "downgraded", "downgrade_cause", "final_value")}
        if data.pop("format", None) != FORMAT or set(data) != {f.name for f in fields(cls)}:
            raise ValueError("unsupported record format or fields")
        dist = data["probability_distribution"]
        if dist is not None:
            if not isinstance(dist, list) or any(not isinstance(p, list) or len(p) != 2 for p in dist):
                raise ValueError("invalid distribution wire format")
            restored = {}
            for key, value in dist:
                if type(key) not in (str, int) or key in restored:
                    raise ValueError("duplicate or invalid distribution key")
                restored[key] = value
            data["probability_distribution"] = restored
        if data["classifier_rule"] is not None:
            data["classifier_rule"] = ClassifierRule(**data["classifier_rule"])
        record = cls(**data)
        if any(_json(getattr(record, k)) != _json(v) for k, v in computed.items()):
            raise ValueError("serialized derived facts disagree with raw answer")
        return record

    @classmethod
    def from_json(cls, text: str) -> CoderRecord:
        return cls.from_dict(json.loads(text, object_pairs_hook=_object))

    def storage_projection(self, *, support: dict[str, Any], instrument: dict[str, Any]) -> dict[str, Any]:
        """Project ORIGINAL-code provenance into unchanged Q2a CoderRecord.

        Requires an actual matching support and the immutable instrument record.
        The return is not a substitute for this complete record's JSON. Do not
        manufacture original-code support to use this adapter after a downgrade.
        """
        from g3o.common.instrument import validate_instrument

        validate_instrument(instrument)
        if instrument["instrument_id"] != self.setup_pointer:
            raise ValueError("record references a different instrument")
        payload = instrument["payload"]
        if self.question_set_version != payload["question_set_version"]:
            raise ValueError("question-set version differs from the instrument")
        if self.classifier_rule is not None and self.classifier_rule.codebook_sha256 != payload["codebook_sha256"]:
            raise ValueError("signed downgrade rule differs from the instrument codebook")
        expected = {"support_id": self.support_id, "observation_id": self.observation_id,
                    "item_id": self.item_id, "item_part": self.item_part,
                    "chunk_id": self.chunk_id, "value_json": self.chosen_value}
        if self.support_id is None or any(support.get(k) != v for k, v in expected.items()):
            raise ValueError("existing support must match the original code and context")
        if self.coder_type in {"mechanical", "derived"}:
            if support.get("support_status") != "set_by_rule" or support.get("support_rule_name") != self.rule_reference:
                raise ValueError("existing support must name the actual mechanical rule")
        if self.coder_type not in {"mechanical", "derived"}:
            key = "configured_jev_model" if self.coder_type == "classifier" else "extractor_model_id"
            if self.configured_model != payload[key]:
                raise ValueError("configured model differs from the instrument")
        self.__post_init__()
        result = {k: getattr(self, k) for k in _STORAGE_FIELDS}
        result.update(chosen_answer_probability=self.chosen_answer_probability,
                      probability_distribution=None if self.probability_distribution is None else {str(k): v for k, v in self.probability_distribution.items()})
        if self.coder_type in {"mechanical", "derived"}:
            result["field_availability"] = {k: NOT_APPLICABLE for k in (*_PROVIDER_FIELDS, "chosen_answer_probability", "probability_distribution")}
        return result


def records_to_json(records: list[CoderRecord]) -> str:
    """Keep every chunk/request in caller order; never collapse by question ID."""
    return _json({"format": "g3o-coder-records-v1", "records": [r.to_dict() for r in records]})


def records_from_json(text: str) -> list[CoderRecord]:
    data = json.loads(text, object_pairs_hook=_object)
    if not isinstance(data, dict) or set(data) != {"format", "records"} or data["format"] != "g3o-coder-records-v1" or not isinstance(data["records"], list):
        raise ValueError("unsupported records envelope")
    return [CoderRecord.from_dict(d) for d in data["records"]]
