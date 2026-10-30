"""Generators: build every derived artefact from the codebook (T-013).

Rules every generator follows (R-025, item-template §4 checks 3, 6, 15, 16):

- Slot ``text`` is copied byte for byte. The only additions are fixed
  scaffolding: headings, item ids, hashes, numbering, field labels and slot
  paths. ``.json`` outputs apply standard JSON string escaping, the one
  declared escaping step; decoding the JSON gives the signed text back.
- Every generated question, prompt section and enum carries its item id and
  item hash, and every file records the codebook release hash in its header.
- In every generated question and prompt section, each value's definition is
  followed by the item's full rule set (own slots and expanded shared rules),
  repeated for each value (check 16, PI ruling 2 a).
- A generator never fills a gap with its own wording. When an item cannot be
  expressed (no value list, no instruction) or a target needs text the
  codebook does not hold, the item or target is skipped and recorded in
  ``not_generated`` / ``BLOCKED_TARGETS`` for the integrator.

Outputs are written under ``g3o/codebook/generated/``. Paths owned by other
cards (T-011, T-012, T-090, and the live prompt files of T-022 / T-032) are
not written; ``INTENDED_TARGETS`` names where each output is meant to land.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from g3o.codebook.loader import NONE, Codebook, RuleText

GENERATED_DIR = "g3o/codebook/generated"
GENERATOR_ID = "g3o.codebook.generators"

#: Marker formats parsed back by the checks (check 6, 16).
ITEM_MARKER = "<!-- item: {item_id} sha256: {item_hash} -->"
VALUE_MARKER = "<!-- value: {code} -->"
RULES_HEADING = "Rules:"

#: Where each generated output is meant to land; the owning card moves it.
INTENDED_TARGETS: dict[str, str] = {
    "jev_questions.json": "T-011 jev question and choice sets (path chosen by T-011)",
    "extractor_prompt_sections.md": "T-022 / T-032 extractor prompt sections (path chosen there)",
    "enums.py": "T-012 enum constants (g3o/common/contract.py or a module T-012 names)",
    "item_schemas.json": "T-012 JSON schema (g3o/common/contract.py response schema)",
    "data_dictionary.md": "T-090 data dictionary (docs/data_dictionary.md)",
    "extract_output_contract.md": "T-010 g3o/extract/prompts/output_contract.md",
    "validate_output_contract.md": "T-010 g3o/validate/prompts/output_contract.md",
    "system_prompt.md": "T-022 / T-032 g3o/extract/prompts/system_prompt.md (and the Stage 6 prompts)",
}

#: Targets no generator can build when the codebook lacks their text (the
#: signed release 2.7 lacks both; the RC-D-005 candidate holds them under
#: ``shared``, item-template amendment A7). ``blocked_targets(cb)`` lists the
#: ones still blocked for a given codebook.
BLOCKED_TARGETS: list[dict[str, str]] = [
    {
        "target": "g3o/extract/prompts/system_prompt.md",
        "reason": (
            "The codebook holds no system-prompt wording (role, task framing, output "
            "format instructions). A generator may not write that wording itself (R-025)."
        ),
    },
    {
        "target": "part prompts for long pages (check 16, all-03 a)",
        "reason": (
            "The codebook holds the temporary value text 'not covered by this part' but no "
            "signed part-prompt sentence stating that the text is only part of the document "
            "(SPEC R-044 marker 'RC-D-003 §2: the part-prompt sentence'); only a rule "
            "description of it (combining_conventions.not_covered_by_this_part)."
        ),
    },
]


def blocked_targets(cb: Codebook) -> list[dict[str, str]]:
    out = []
    if cb.shared_slot("system_prompt") is None:
        out.append(BLOCKED_TARGETS[0])
    if cb.shared_slot("part_prompt/sentence") is None or cb.shared_slot("part_prompt/temporary_answer/label") is None:
        out.append(BLOCKED_TARGETS[1])
    return out


@dataclass
class GeneratedFile:
    """One generated artefact plus the slots it used (for check 3)."""

    name: str
    content: str
    used_slots: list[tuple[str, str]] = field(default_factory=list)

    @property
    def relpath(self) -> str:
        return f"{GENERATED_DIR}/{self.name}"

    @property
    def is_json(self) -> bool:
        return self.name.endswith(".json")

    def bytes(self) -> bytes:
        return self.content.encode("utf-8")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _md_header(cb: Codebook, target: str) -> str:
    return (
        "<!-- GENERATED FILE - do not edit. Built from codebook/codebook.yaml by "
        f"{GENERATOR_ID}.{target}. -->\n"
        f"<!-- codebook release: {cb.label} | codebook sha256: {cb.sha256} -->\n"
    )


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _json_header(cb: Codebook, target: str) -> dict[str, Any]:
    return {
        "generated_by": f"{GENERATOR_ID}.{target}",
        "do_not_edit": True,
        "codebook_release": cb.label,
        "codebook_sha256": cb.sha256,
    }


def _values_with_rules(cb: Codebook, item_id: str) -> list[tuple[str, str, str, list[RuleText]]]:
    """(code, definition path, definition text, full rules) per value."""
    rules = cb.rule_texts(item_id)
    out = []
    for n, value in enumerate(cb.value_list(item_id) or []):
        slot = cb.definition(item_id, n)
        if slot is None:
            continue
        out.append((str(value["code"]), slot.path, slot.text, rules))
    return out


def _numbered(rules: list[RuleText]) -> str:
    return "\n".join(f"{n}. {r.text}" for n, r in enumerate(rules, start=1))


def _value_block(definition: str, rules: list[RuleText]) -> str:
    """A value's definition followed by the item's full rules (check 16)."""
    if not rules:
        return definition
    return f"{definition}\n\n{RULES_HEADING}\n{_numbered(rules)}"


def _expressible_choice_item(cb: Codebook, item_id: str) -> str | None:
    """Why a choice item cannot be assembled verbatim, or None when it can."""
    item = cb.items[item_id]
    if cb.instruction(item_id) is None:
        return "instruction is not a text slot"
    parts = cb.parts(item_id)
    if parts is not None:
        for n, (name, part) in enumerate(parts):
            if cb.part_instruction(item_id, n) is None:
                return f"part {name!r} has no instruction slot (values.part_instructions)"
            bad = [str(v["code"]) for i, v in enumerate(part) if cb.part_definition(item_id, name, i) is None]
            if bad:
                return f"part {name!r} values without a definition text slot: {bad}"
        return None
    if cb.computed_values(item_id) is not None:
        return None
    values = cb.value_list(item_id)
    if values is None:
        return f"values are not an ordered list of {{code, definition}} (got {type(item.get('values')).__name__}: {str(item.get('values'))[:80]!r})"
    missing = [str(v["code"]) for n, v in enumerate(values) if cb.definition(item_id, n) is None]
    if missing:
        return f"values without a definition text slot: {missing}"
    return None


# ---------------------------------------------------------------------------
# generic verbatim renderer (data dictionary, output contracts)
# ---------------------------------------------------------------------------


def _walk_slots(node: Any, path: str) -> list[tuple[str, str]]:
    """Every slot text under ``node`` in document order, with its path."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        if isinstance(node.get("text"), str):
            found.append((path, node["text"]))
        for key, child in node.items():
            if key == "text" or key.endswith("_before_r4") or key == "frozen_text":
                continue
            found.extend(_walk_slots(child, f"{path}/{key}"))
    elif isinstance(node, list):
        for n, child in enumerate(node):
            found.extend(_walk_slots(child, f"{path}/{n}"))
    return found


def _scalar(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(f"`{v}`" for v in value) if value else NONE
    if isinstance(value, dict):
        compact = {k: v for k, v in value.items() if not isinstance(v, dict | list) or k in ("values", "order")}
        return "`" + json.dumps(compact, ensure_ascii=False) + "`"
    return f"`{value}`"


_DICT_FIELDS = (
    "family", "name", "level", "pipelines", "linkage", "coder", "pass", "round",
    "answer_type", "order_tie_rule", "support_required", "downgrade_target",
    "threshold", "missing_tokens", "input_text", "visibility", "frozen_signature",
    "version_introduced", "status",
)


def _render_item_reference(cb: Codebook, item_id: str, used: list[tuple[str, str]]) -> str:
    """One item, rules stated once (allowed for the dictionary and contracts, check 16)."""
    item = cb.items[item_id]
    h = cb.item_hash(item_id)
    lines = [f"## `{item_id}`", ITEM_MARKER.format(item_id=item_id, item_hash=h), ""]
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| item hash | `{h}` |")
    for key in _DICT_FIELDS:
        lines.append(f"| {key} | {_scalar(item.get(key))} |")
    for key in ("gate", "long_page_rule", "translation_v25"):
        value = item.get(key)
        lines.append(f"| {key} | {_scalar(value) if not isinstance(value, dict) else _scalar({k: v for k, v in value.items() if not isinstance(v, dict)})} |")
    lines.append("")

    ins = cb.instruction(item_id)
    if ins is not None:
        lines += ["### Instruction", "", ins.text, ""]
        used.append((ins.path, ins.text))

    values = cb.value_list(item_id)
    if values is not None:
        lines += ["### Values", ""]
        for n, value in enumerate(values):
            lines.append(f"#### `{value['code']}`")
            lines.append("")
            slot = cb.definition(item_id, n)
            if slot is not None:
                lines += [slot.text, ""]
                used.append((slot.path, slot.text))
    elif isinstance(item.get("values"), dict):
        lines += ["### Values (structured; rendered by slot path)", ""]
        for path, text in _walk_slots(item["values"], f"items/{item_id}/values"):
            lines += [f"`{path}`", "", text, ""]
            used.append((path, text))

    rules = cb.rule_texts(item_id)
    nontext = cb.rule_slots_without_text(item_id)
    if rules or nontext:
        lines += ["### Rules", ""]
        for n, rule in enumerate(rules, start=1):
            label = f" (shared rule `{rule.shared_rule}`)" if rule.shared_rule else ""
            lines += [f"{n}. `{rule.path}`{label}", "", rule.text, ""]
            used.append((rule.path, rule.text))
        for path in nontext:
            lines.append(f"Rule entry without a `text` slot, rendered by slot path: `{path}`")
            lines.append("")
            idx = int(path.rsplit("/", 1)[1])
            for sub_path, text in _walk_slots(item["rules"][idx], path):
                lines += [f"`{sub_path}`", "", text, ""]
                used.append((sub_path, text))

    for key in ("gate", "long_page_rule"):
        value = item.get(key)
        if isinstance(value, dict):
            slots = _walk_slots(value, f"items/{item_id}/{key}")
            if slots:
                lines += [f"### {key} text", ""]
                for path, text in slots:
                    lines += [f"`{path}`", "", text, ""]
                    used.append((path, text))
    return "\n".join(lines).rstrip("\n") + "\n"


def _reference_doc(cb: Codebook, target: str, title: str, item_ids: list[str]) -> GeneratedFile:
    used: list[tuple[str, str]] = []
    parts = [_md_header(cb, target), f"# {title}", "", f"Codebook release `{cb.label}`, sha256 `{cb.sha256}`. {len(item_ids)} items.", ""]
    for item_id in item_ids:
        parts.append(_render_item_reference(cb, item_id, used))
    return GeneratedFile(target_name(target), "\n".join(parts), used)


def target_name(target: str) -> str:
    return {
        "data_dictionary": "data_dictionary.md",
        "extract_output_contract": "extract_output_contract.md",
        "validate_output_contract": "validate_output_contract.md",
    }[target]


# ---------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------


def _offered(values: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    """Values offered as jev choices: every value except those flagged
    ``jev_choice: false`` (e.g. ``not_assessable``, P3; amendment A7)."""
    return [(n, v) for n, v in enumerate(values) if v.get("jev_choice") is not False]


def _missing_criteria(cb: Codebook, item_id: str, rules: list[RuleText],
                      used: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Missing labels offered as choices (RC-D-005 12 a): the label's meaning
    rule(s), then the item's full rules (check 16)."""
    out = []
    for code, slots in cb.missing_choices(item_id):
        if not slots:
            continue
        meaning = "\n".join(s.text for s in slots)
        used.extend((s.path, s.text) for s in slots)
        used.extend((r.path, r.text) for r in rules)
        out.append({"code": code, "missing_label": True, "text": _value_block(meaning, rules),
                    "definition_slot": slots[0].path, "rule_slots": [r.path for r in rules]})
    return out


def _part_prompt(cb: Codebook, used: list[tuple[str, str]]) -> dict[str, Any] | None:
    """The part-prompt sentence and temporary answer (all-03 a; RC-D-005 5 a)."""
    sentence = cb.shared_slot("part_prompt/sentence")
    label = cb.shared_slot("part_prompt/temporary_answer/label")
    meaning = cb.shared_slot("part_prompt/temporary_answer/meaning")
    if sentence is None or label is None:
        return None
    used.append((sentence.path, sentence.text))
    used.append((label.path, label.text))
    answer: dict[str, Any] = {"label": label.text, "label_slot": label.path}
    if meaning is not None:
        used.append((meaning.path, meaning.text))
        answer.update({"meaning": meaning.text, "meaning_slot": meaning.path})
    return {"sentence": sentence.text, "sentence_slot": sentence.path, "temporary_answer": answer}


def _question(cb: Codebook, item_id: str, item: dict[str, Any], question_id: str, ins: Any,
              criteria: list[dict[str, Any]], gate: Any, part: str | None,
              temp: dict[str, Any] | None) -> dict[str, Any]:
    q: dict[str, Any] = {
        "question_id": question_id,
        "item_id": item_id,
        "item_hash": cb.item_hash(item_id),
        "column": item.get("name"),
        "pass": item.get("pass"),
        "round": item.get("round"),
        "gate": gate,
        "answer_type": item.get("answer_type"),
        "threshold": item.get("threshold"),
        "frozen_signature": item.get("frozen_signature"),
        "instructions": ins.text,
        "instruction_slot": ins.path,
        "criteria": criteria,
    }
    if part is not None:
        q["part"] = part
    ctx = item.get("question_context")
    if isinstance(ctx, dict) and ctx.get("shows_value_of"):
        q["shows_value_of"] = ctx["shows_value_of"]
    if temp is not None:
        q["part_prompt_answer"] = temp["temporary_answer"]
    return q


def _criterion(code: str, d: Any, rules: list[RuleText], used: list[tuple[str, str]]) -> dict[str, Any]:
    used.append((d.path, d.text))
    used.extend((r.path, r.text) for r in rules)
    return {"code": code, "text": _value_block(d.text, rules), "definition_slot": d.path,
            "rule_slots": [r.path for r in rules]}


def gen_jev_questions(cb: Codebook) -> GeneratedFile:
    """jev question and choice sets: one question per ``jev_choice`` item, one
    per part for a parts item (amendment A6) (T-011). Values flagged
    ``jev_choice: false`` are not offered; offered missing labels are added
    with their meaning rule; computed-value items (A2) carry their rules once
    after the instruction. When the codebook holds the part-prompt texts, the
    file carries the part sentence and every question the temporary answer."""
    used: list[tuple[str, str]] = []
    questions: list[dict[str, Any]] = []
    not_generated: list[dict[str, str]] = []
    temp = _part_prompt(cb, used)
    for item_id, item in cb.build_items().items():
        if item.get("linkage") != "jev_choice":
            continue
        reason = _expressible_choice_item(cb, item_id)
        if reason is not None:
            not_generated.append({"item_id": item_id, "reason": reason})
            continue
        rules = cb.rule_texts(item_id)
        parts = cb.parts(item_id)
        if parts is not None:
            for n, (name, part) in enumerate(parts):
                ins = cb.part_instruction(item_id, n)
                assert ins is not None
                used.append((ins.path, ins.text))
                criteria = []
                for i, value in _offered(part):
                    d = cb.part_definition(item_id, name, i)
                    assert d is not None
                    criteria.append(_criterion(str(value["code"]), d, rules, used))
                criteria += _missing_criteria(cb, item_id, rules, used)
                gate = item.get("gate") if n == 0 else cb.part_gate(item_id, name)
                qid = item_id if n == 0 else f"{item_id}#{name}"
                questions.append(_question(cb, item_id, item, qid, ins, criteria, gate, name, temp))
            continue
        ins = cb.instruction(item_id)
        assert ins is not None
        used.append((ins.path, ins.text))
        computed = cb.computed_values(item_id)
        if computed is not None:
            q = _question(cb, item_id, item, item_id, ins, _missing_criteria(cb, item_id, rules, used),
                          item.get("gate"), None, temp)
            q["computed_values"] = computed
            nots = (item.get("values") or {}).get("candidates_not_offered")
            if isinstance(nots, dict) and nots.get("codes"):
                q["candidates_not_offered"] = nots["codes"]     # kept as values, set mechanically (12 a, round 2)
            q["rules_text"] = f"{RULES_HEADING}\n{_numbered(rules)}" if rules else ""
            q["rule_slots"] = [r.path for r in rules]
            used.extend((r.path, r.text) for r in rules)
            questions.append(q)
            continue
        criteria = []
        for n, value in _offered(cb.value_list(item_id) or []):
            d = cb.definition(item_id, n)
            assert d is not None
            criteria.append(_criterion(str(value["code"]), d, rules, used))
        criteria += _missing_criteria(cb, item_id, rules, used)
        questions.append(_question(cb, item_id, item, item_id, ins, criteria, item.get("gate"), None, temp))
    doc = _json_header(cb, "jev_questions")
    doc["intended_target"] = INTENDED_TARGETS["jev_questions.json"]
    if temp is not None:
        doc["part_prompt"] = temp
    doc["questions"] = questions
    doc["not_generated"] = not_generated
    return GeneratedFile("jev_questions.json", _json_dump(doc), used)


def gen_system_prompt(cb: Codebook) -> GeneratedFile | None:
    """The shared system prompt(s) (RC-D-005 6 a; amendment A7), when the
    codebook holds them: one section per ``shared/system_prompt*`` slot."""
    shared = cb.data.get("shared") or {}
    keys = [k for k in shared if k.startswith("system_prompt") and cb.shared_slot(k) is not None]
    if not keys:
        return None
    used: list[tuple[str, str]] = []
    parts = [_md_header(cb, "system_prompt"), "# System prompts", "",
             f"Codebook release `{cb.label}`, sha256 `{cb.sha256}`. "
             f"Intended target: {INTENDED_TARGETS['system_prompt.md']}.", ""]
    for k in keys:
        slot = cb.shared_slot(k)
        assert slot is not None
        applies = shared[k].get("applies_to") if isinstance(shared[k], dict) else None
        parts += [f"## `{slot.path}`", "", f"Applies to: {_scalar(applies) if applies else NONE}.", "", slot.text, ""]
        used.append((slot.path, slot.text))
    return GeneratedFile("system_prompt.md", "\n".join(parts).rstrip("\n") + "\n", used)


def gen_extractor_sections(cb: Codebook) -> GeneratedFile:
    """Extractor prompt sections: one section per ``extractor`` item (T-022, T-032)."""
    used: list[tuple[str, str]] = []
    parts = [_md_header(cb, "extractor_prompt_sections"),
             "# Extractor prompt sections", "",
             f"Codebook release `{cb.label}`, sha256 `{cb.sha256}`. "
             f"Intended target: {INTENDED_TARGETS['extractor_prompt_sections.md']}.", ""]
    for item_id, item in cb.build_items().items():
        if item.get("linkage") != "extractor":
            continue
        h = cb.item_hash(item_id)
        block = [f"## `{item_id}`", ITEM_MARKER.format(item_id=item_id, item_hash=h), "",
                 f"Column `{item.get('name')}`; item hash `{h}`.", ""]
        ins = cb.instruction(item_id)
        if ins is not None:
            block += ["### Instruction", "", ins.text, ""]
            used.append((ins.path, ins.text))
        rules = cb.rule_texts(item_id)
        values = _values_with_rules(cb, item_id)
        if values:
            block += ["### Values", ""]
            for code, def_path, definition, rules in values:
                block += [f"#### `{code}`", VALUE_MARKER.format(code=code), "", _value_block(definition, rules), ""]
                used.append((def_path, definition))
                used.extend((r.path, r.text) for r in rules)
        elif rules:
            block += ["### Rules", "", _numbered(rules), ""]
            used.extend((r.path, r.text) for r in rules)
        parts.append("\n".join(block))
    return GeneratedFile("extractor_prompt_sections.md", "\n".join(parts).rstrip("\n") + "\n", used)


def _const_name(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).upper()


def gen_enums(cb: Codebook) -> GeneratedFile:
    """Python enum constants: one per item with a value list (T-012)."""
    lines = [
        "# GENERATED FILE - do not edit. Built from codebook/codebook.yaml by",
        f"# {GENERATOR_ID}.enums.",
        f"# codebook release: {cb.label} | codebook sha256: {cb.sha256}",
        f"# Intended target: {INTENDED_TARGETS['enums.py']}.",
        '"""Codebook value lists as constants; each carries its item id and item hash."""',
        "",
        "from __future__ import annotations",
        "",
        f"CODEBOOK_RELEASE = {cb.label!r}",
        f"CODEBOOK_SHA256 = {cb.sha256!r}",
        "",
        "#: item id -> (item hash, value codes in codebook order)",
        "ITEM_ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {",
    ]
    names: list[tuple[str, str]] = []
    part_lines: list[str] = []
    for item_id, item in cb.build_items().items():
        values = cb.value_list(item_id)
        parts = cb.parts(item_id)
        if values is None and parts is None:
            continue
        if parts is not None:
            values = parts[0][1]
            for name, part in parts:
                pcodes = ", ".join(repr(str(v["code"])) for v in part)
                part_lines.append(f"    ({item_id!r}, {name!r}): ({pcodes},),")
        codes = ", ".join(repr(str(v["code"])) for v in values)
        lines.append(f"    {item_id!r}: ({cb.item_hash(item_id)!r}, ({codes},)),")
        names.append((_const_name(str(item.get("name"))), item_id))
    lines.append("}")
    lines.append("")
    if part_lines:
        lines.append("#: (item id, part) -> value codes, for items in the parts form (first part as ITEM_ENUMS)")
        lines.append("ITEM_PART_ENUMS: dict[tuple[str, str], tuple[str, ...]] = {")
        lines.extend(part_lines)
        lines.append("}")
        lines.append("")
    for const, item_id in names:
        lines.append(f"{const} = ITEM_ENUMS[{item_id!r}][1]  # {item_id}")
    return GeneratedFile("enums.py", "\n".join(lines) + "\n")


def _item_schema(cb: Codebook, item_id: str) -> dict[str, Any]:
    item = cb.items[item_id]
    missing = [str(t) for t in item.get("missing_tokens") or [] if isinstance(item.get("missing_tokens"), list)]
    values = cb.value_list(item_id)
    codes = [str(v["code"]) for v in values] if values is not None else None
    answer = item.get("answer_type")
    meta = {"x-item-id": item_id, "x-item-hash": cb.item_hash(item_id), "x-answer-type": answer}
    parts = cb.parts(item_id)
    if parts is not None:
        meta["x-parts"] = {name: [str(v["code"]) for v in part] for name, part in parts}
        return {**meta, "type": "string"}
    if codes is not None and answer == "multi":
        schema: dict[str, Any] = {"anyOf": [{"type": "array", "items": {"enum": codes}}, {"enum": missing}]}
    elif codes is not None:
        schema = {"enum": codes + [m for m in missing if m not in codes]}
    elif answer == "number":
        schema = {"anyOf": [{"type": "number"}, {"enum": missing}]}
    elif answer == "list":
        schema = {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"enum": missing}]}
    else:
        schema = {"type": "string"}
    return {**meta, **schema}


def gen_item_schemas(cb: Codebook) -> GeneratedFile:
    """Per-item JSON-schema fragments keyed by column name (T-012 assembles rows)."""
    doc = _json_header(cb, "item_schemas")
    doc["intended_target"] = INTENDED_TARGETS["item_schemas.json"]
    doc["$defs"] = {str(item.get("name")): _item_schema(cb, item_id) for item_id, item in cb.build_items().items()}
    return GeneratedFile("item_schemas.json", _json_dump(doc))


def gen_data_dictionary(cb: Codebook) -> GeneratedFile:
    return _reference_doc(cb, "data_dictionary", "G3O codebook data dictionary", list(cb.build_items()))


def gen_extract_output_contract(cb: Codebook) -> GeneratedFile:
    ids = [i for i, it in cb.build_items().items() if "web_extract" in (it.get("pipelines") or [])]
    return _reference_doc(cb, "extract_output_contract", "G3O output contract (extract), generated from the codebook", ids)


def gen_validate_output_contract(cb: Codebook) -> GeneratedFile:
    ids = [i for i, it in cb.build_items().items() if "stage6" in (it.get("pipelines") or [])]
    return _reference_doc(cb, "validate_output_contract", "G3O output contract (validate, Stage 6), generated from the codebook", ids)


def gen_manifest(cb: Codebook, files: list[GeneratedFile]) -> GeneratedFile:
    """Release record: per-item hashes (A-001), generated files and blocked targets."""
    from g3o.codebook.loader import sha256_bytes

    doc = _json_header(cb, "manifest")
    doc["build_scope"] = cb.build_scope
    doc["items"] = [
        {"item_id": i, "item_hash": cb.item_hash(i), "frozen_signature": it.get("frozen_signature"),
         "in_build_scope": cb.in_build_scope(i)}
        for i, it in cb.items.items()
    ]
    doc["generated_files"] = [{"path": f.relpath, "sha256": sha256_bytes(f.bytes()),
                               "intended_target": INTENDED_TARGETS.get(f.name)} for f in files]
    doc["blocked_targets"] = blocked_targets(cb)
    return GeneratedFile("manifest.json", _json_dump(doc))


GENERATORS = (
    gen_jev_questions,
    gen_extractor_sections,
    gen_enums,
    gen_item_schemas,
    gen_data_dictionary,
    gen_extract_output_contract,
    gen_validate_output_contract,
    gen_system_prompt,
)


def generate_all(cb: Codebook) -> list[GeneratedFile]:
    """Every generated artefact, manifest last."""
    files = [f for f in (gen(cb) for gen in GENERATORS) if f is not None]
    files.append(gen_manifest(cb, files))
    return files
