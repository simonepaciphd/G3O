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
}

#: Targets no generator can build from the codebook as signed.
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


def gen_jev_questions(cb: Codebook) -> GeneratedFile:
    """jev question and choice sets: one question per ``jev_choice`` item (T-011)."""
    used: list[tuple[str, str]] = []
    questions: list[dict[str, Any]] = []
    not_generated: list[dict[str, str]] = []
    for item_id, item in cb.build_items().items():
        if item.get("linkage") != "jev_choice":
            continue
        reason = _expressible_choice_item(cb, item_id)
        if reason is not None:
            not_generated.append({"item_id": item_id, "reason": reason})
            continue
        ins = cb.instruction(item_id)
        assert ins is not None
        used.append((ins.path, ins.text))
        criteria = []
        for code, def_path, definition, rules in _values_with_rules(cb, item_id):
            used.append((def_path, definition))
            used.extend((r.path, r.text) for r in rules)
            criteria.append({
                "code": code,
                "text": _value_block(definition, rules),
                "definition_slot": def_path,
                "rule_slots": [r.path for r in rules],
            })
        questions.append({
            "question_id": item_id,
            "item_id": item_id,
            "item_hash": cb.item_hash(item_id),
            "column": item.get("name"),
            "pass": item.get("pass"),
            "round": item.get("round"),
            "gate": item.get("gate"),
            "answer_type": item.get("answer_type"),
            "threshold": item.get("threshold"),
            "frozen_signature": item.get("frozen_signature"),
            "instructions": ins.text,
            "instruction_slot": ins.path,
            "criteria": criteria,
        })
    doc = _json_header(cb, "jev_questions")
    doc["intended_target"] = INTENDED_TARGETS["jev_questions.json"]
    doc["questions"] = questions
    doc["not_generated"] = not_generated
    return GeneratedFile("jev_questions.json", _json_dump(doc), used)


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
    for item_id, item in cb.build_items().items():
        values = cb.value_list(item_id)
        if values is None:
            continue
        codes = ", ".join(repr(str(v["code"])) for v in values)
        lines.append(f"    {item_id!r}: ({cb.item_hash(item_id)!r}, ({codes},)),")
        names.append((_const_name(str(item.get("name"))), item_id))
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
    doc["blocked_targets"] = BLOCKED_TARGETS
    return GeneratedFile("manifest.json", _json_dump(doc))


GENERATORS = (
    gen_jev_questions,
    gen_extractor_sections,
    gen_enums,
    gen_item_schemas,
    gen_data_dictionary,
    gen_extract_output_contract,
    gen_validate_output_contract,
)


def generate_all(cb: Codebook) -> list[GeneratedFile]:
    """Every generated artefact, manifest last."""
    files = [gen(cb) for gen in GENERATORS]
    files.append(gen_manifest(cb, files))
    return files
