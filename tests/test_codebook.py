"""Codebook loader, generators and generator checks 1-16 (T-013).

Two layers:

- The signed codebook (``codebook/codebook.yaml``, release 2.7): its hash, the
  committed generated files reproducing byte for byte (check 5), CX question
  text byte-identical to the signed item text (R-025), A-001 linkage, and the
  current check results pinned so a change in either the codebook or the
  checks is visible.
- Each check against a small synthetic codebook with one seeded fault, so a
  check that silently stops catching its fault fails here.

No network, no API keys.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest
import yaml

from g3o.codebook import checks as C
from g3o.codebook.cli import main as cli_main
from g3o.codebook.generators import GENERATED_DIR, generate_all
from g3o.codebook.loader import REPO_ROOT, Codebook, load_codebook

SIGNED_SHA256 = "d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764"


@pytest.fixture(scope="module")
def cb() -> Codebook:
    return load_codebook()


@pytest.fixture(scope="module")
def ctx(cb: Codebook) -> C.Context:
    return C.default_context(cb)


# ---------------------------------------------------------------------------
# signed codebook
# ---------------------------------------------------------------------------


def test_signed_codebook_hash(cb: Codebook) -> None:
    """The file on disk is the PI-signed file (signoff-record.md)."""
    assert cb.sha256 == SIGNED_SHA256
    assert cb.raw.count(b"\r\n") > 0, "signed file is CRLF; a newline conversion would change its hash"


def test_regeneration_reproduces_committed_files(cb: Codebook) -> None:
    """Self-check 1 / check 5: every committed generated file is byte-identical."""
    for f in generate_all(cb):
        committed = REPO_ROOT / f.relpath
        assert committed.read_bytes() == f.bytes(), f.relpath


def test_generation_is_deterministic(cb: Codebook) -> None:
    a = [(f.name, f.bytes()) for f in generate_all(cb)]
    b = [(f.name, f.bytes()) for f in generate_all(load_codebook())]
    assert a == b


def _copy_generated(tmp_path: Path) -> Path:
    shutil.copytree(REPO_ROOT / GENERATED_DIR, tmp_path / GENERATED_DIR)
    return tmp_path


def test_drift_check_fails_on_seeded_drift(cb: Codebook, tmp_path: Path, capsys) -> None:
    """Self-check 2: one changed byte in a generated file fails the drift step."""
    root = _copy_generated(tmp_path)
    assert cli_main(["drift", "--repo-root", str(root)]) == 0
    target = root / GENERATED_DIR / "jev_questions.json"
    data = target.read_bytes()
    target.write_bytes(data.replace(b"What kind of document is this page?", b"What kind of document is this page!", 1))
    assert cli_main(["drift", "--repo-root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "jev_questions.json: differs from regeneration" in out


def test_drift_check_fails_on_stray_and_missing_files(cb: Codebook, tmp_path: Path) -> None:
    root = _copy_generated(tmp_path)
    (root / GENERATED_DIR / "hand_written.md").write_text("x", encoding="utf-8")
    (root / GENERATED_DIR / "enums.py").unlink()
    res = C.check_05_no_drift(cb, C.Context(generated=generate_all(cb), repo_root=root))
    assert res.status == "fail"
    assert any("hand_written.md: no generator produces it" in f for f in res.findings)
    assert any("enums.py: not committed" in f for f in res.findings)


def test_cx_question_byte_identical_to_signed_text(cb: Codebook) -> None:
    """Self-check 3: generated CX questions carry the signed text byte for byte."""
    doc = json.loads((REPO_ROOT / GENERATED_DIR / "jev_questions.json").read_text(encoding="utf-8"))
    cx = [q for q in doc["questions"] if q["frozen_signature"] != "none"]
    assert {q["item_id"] for q in cx} >= {"core.disclosure_form"}
    for q in cx:
        item = cb.items[q["item_id"]]
        assert q["instructions"] == item["instruction"]["text"]
        assert q["instructions"].encode("utf-8") in cb.raw  # the signed bytes themselves
        if item["instruction"].get("draft_action") == "no_change":
            assert q["instructions"] == item["instruction"]["frozen_text"]
        for n, crit in enumerate(q["criteria"]):
            definition = item["values"][n]["definition"]["text"]
            assert crit["text"].startswith(definition)
    form = next(q for q in cx if q["item_id"] == "core.disclosure_form")
    assert form["instructions"] == "What kind of document is this page?"


def test_every_question_and_section_carries_item_id_and_hash(cb: Codebook) -> None:
    """Self-check 4: A-001 linkage on the committed outputs."""
    doc = json.loads((REPO_ROOT / GENERATED_DIR / "jev_questions.json").read_text(encoding="utf-8"))
    assert doc["codebook_sha256"] == cb.sha256
    for q in doc["questions"]:
        assert q["item_hash"] == cb.item_hash(q["item_id"])
    md = (REPO_ROOT / GENERATED_DIR / "extractor_prompt_sections.md").read_text(encoding="utf-8")
    extractor = [i for i, it in cb.build_items().items() if it["linkage"] == "extractor"]
    for item_id in extractor:
        assert f"<!-- item: {item_id} sha256: {cb.item_hash(item_id)} -->" in md
    enums = (REPO_ROOT / GENERATED_DIR / "enums.py").read_text(encoding="utf-8")
    assert f"'core.page_verdict': ('{cb.item_hash('core.page_verdict')}'," in enums


def test_generated_enums_import(cb: Codebook) -> None:
    from g3o.codebook.generated import enums

    assert enums.CODEBOOK_SHA256 == cb.sha256
    assert enums.PAGE_VERDICT[0] == "confirms_activity"
    assert set(enums.ITEM_ENUMS) <= set(cb.items)


def test_blocked_targets_recorded(cb: Codebook) -> None:
    manifest = json.loads((REPO_ROOT / GENERATED_DIR / "manifest.json").read_text(encoding="utf-8"))
    targets = {b["target"] for b in manifest["blocked_targets"]}
    assert "g3o/extract/prompts/system_prompt.md" in targets
    assert len(manifest["items"]) == len(cb.items)


#: Results of checks 1-16 on the signed release 2.7 file. The failures are
#: codebook findings reported to the integrator (T-013 return report); they are
#: fixed by a codebook delta and a re-signature, never here. When the codebook
#: changes, update this pin from `python -m g3o.codebook checks`.
SIGNED_RESULTS = {
    1: "fail", 2: "pass", 3: "pass", 4: "pass", 5: "pass", 6: "fail", 7: "fail", 8: "pass",
    9: "fail", 10: "fail", 11: "fail", 12: "n/a", 13: "fail", 14: "pass", 15: "pass", 16: "pass",
}


def test_signed_codebook_known_check_results(cb: Codebook, ctx: C.Context) -> None:
    results = {r.number: r.status for r in C.run_checks(cb, ctx)}
    assert results == SIGNED_RESULTS


def test_cli_checks_and_hash(capsys) -> None:
    assert cli_main(["hash"]) == 0
    assert capsys.readouterr().out.strip() == SIGNED_SHA256
    assert cli_main(["checks", "-v"]) == 1  # failing checks on the signed file (see SIGNED_RESULTS)
    out = capsys.readouterr().out
    assert "check 13 sign-off gate: FAIL" in out


def test_schema_file_is_valid_json_and_names_every_template_field() -> None:
    schema = json.loads((REPO_ROOT / "codebook" / "schema.json").read_text(encoding="utf-8"))
    item = schema["$defs"]["item"]
    assert set(item["required"]) == set(C.TEMPLATE_FIELDS)


def test_schema_validates_the_template_shape_when_jsonschema_available() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO_ROOT / "codebook" / "schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    good = _mini()
    jsonschema.validate(good, schema)
    bad = _mini()
    del bad["items"]["core.alpha"]["family"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


# ---------------------------------------------------------------------------
# synthetic codebooks: each check catches its seeded fault
# ---------------------------------------------------------------------------


def _slot(text: str) -> dict[str, str]:
    return {"text": text, "origin": "pi"}


def _item(item_id: str, **over) -> dict:
    name = item_id.split(".", 1)[1]
    base = {
        "id": item_id, "family": "verdict", "name": name, "level": ["page"],
        "pipelines": ["web_extract"], "linkage": "jev_choice", "coder": "classifier",
        "pass": 1, "round": 1, "gate": "none", "answer_type": "single",
        "instruction": _slot(f"Question for {name}?"),
        "values": [{"code": "yes_value", "definition": _slot(f"{name} yes.")},
                   {"code": "no_value", "definition": _slot(f"{name} no.")}],
        "rules": [_slot(f"Own rule of {name}."), "core.rule.shared"],
        "order_tie_rule": "first_in_order", "long_page_rule": "first_section",
        "support_required": True, "downgrade_target": "unknown",
        "threshold": {"metric": "chosen_answer_probability", "bar": 0.8},
        "missing_tokens": ["not_asked", "not_documented", "unknown"],
        "input_text": "main", "visibility": "public", "frozen_signature": "none",
        "version_introduced": "2.7", "translation_v25": "new", "refs": ["R-001"], "status": "signed",
    }
    base.update(over)
    return base


def _mini() -> dict:
    return {
        "release": {"label": "2.7", "status": "signed", "namespaces": ["core"],
                    "signature_record": "record.md", "hash_rule": "sha256 of the file bytes"},
        "vocabularies": {
            "missing": {"values": ["not_asked", "not_documented", "unknown", "_NA_"]},
            "pipeline": {"values": ["web_extract", "stage6", "procurement", "ai_text"]},
            "level": {"values": ["institution", "page", "activity", "source", "row"]},
            "family": {"values": ["verdict", "completeness"]},
        },
        "shared_rules": {"core.rule.shared": [_slot("Shared rule text.")]},
        "items": {
            "core.alpha": _item("core.alpha"),
            "core.beta": _item("core.beta", round=2,
                               gate={"item": "core.alpha", "values": ["yes_value"]}),
            "core.gamma": _item("core.gamma", linkage="extractor", coder="quote_step", pass_="none",
                                instruction="none", values="none", answer_type="text",
                                threshold="none", long_page_rule="none", rules=[_slot("Quote it.")]),
        },
        "retired": [],
    }


def _cb(data: dict) -> Codebook:
    for it in data["items"].values():
        if "pass_" in it:
            it["pass"] = it.pop("pass_")
        if it.get("round") and it.get("pass") == "none":
            it["round"] = "none"
    return Codebook(yaml.safe_dump(data, allow_unicode=True, sort_keys=False).encode("utf-8"))


def _run(data: dict, number: int, **ctx_over) -> C.CheckResult:
    cb = _cb(data)
    ctx = C.Context(generated=generate_all(cb), **ctx_over)
    return C.CHECKS[number - 1](cb, ctx)


def test_mini_codebook_passes_every_check(tmp_path: Path) -> None:
    cb = _cb(_mini())
    files = generate_all(cb)
    for f in files:
        (tmp_path / f.relpath).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f.relpath).write_bytes(f.bytes())
    record = f"| sha256 | `{cb.sha256}` |\n"
    ctx = C.Context(generated=files, repo_root=tmp_path, signature_record=record, v25_columns=())
    results = {r.number: (r.status, r.findings) for r in C.run_checks(cb, ctx)}
    assert all(status in ("pass", "n/a") for status, _ in results.values()), results


def test_check01_flags_missing_field_and_bad_forms() -> None:
    d = _mini()
    del d["items"]["core.alpha"]["refs"]
    d["items"]["core.beta"]["status"] = "approved"
    d["items"]["core.beta"]["values"] = "none"
    res = _run(d, 1)
    assert res.status == "fail"
    assert any("core.alpha: field refs: missing" in f for f in res.findings)
    assert any("core.beta: field status" in f for f in res.findings)
    assert any("core.beta: field values: none, but answer_type 'single'" in f for f in res.findings)


def test_check01_out_of_scope_items_are_notes_only() -> None:
    d = _mini()
    d["release"]["namespaces"] = ["core", "proc"]
    d["release"]["build_scope_v2_7"] = "core"
    d["items"]["proc.delta"] = _item("proc.delta", version_introduced="open")
    res = _run(d, 1)
    assert res.status == "pass"
    assert any("proc.delta" in n for n in res.notes)


def test_check02_duplicate_names_and_disappearing_ids() -> None:
    d = _mini()
    d["items"]["core.beta"]["name"] = "alpha"
    assert _run(d, 2).status == "fail"
    prev = _cb(_mini())
    d2 = _mini()
    del d2["items"]["core.gamma"]
    res = _run(d2, 2, previous=prev)
    assert any("core.gamma: in the previous release, gone" in f for f in res.findings)


def test_check03_flags_rewritten_text() -> None:
    cb = _cb(_mini())
    files = generate_all(cb)
    jev = next(f for f in files if f.name == "jev_questions.json")
    jev.content = jev.content.replace("Question for alpha?", "Question about alpha?")
    res = C.check_03_verbatim(cb, C.Context(generated=files))
    assert res.status == "fail"
    assert any("items/core.alpha/instruction" in f for f in res.findings)


def test_check04_frozen_needs_matching_record() -> None:
    d = _mini()
    d["items"]["core.alpha"]["frozen_signature"] = "CX-01.3:CX-10"
    cb = _cb(d)
    good = f"| sha256 | `{cb.sha256}` |\n| CX-10 | `core.alpha` |\n"
    assert _run(d, 4, signature_record=good).status == "pass"
    stale = "| sha256 | `" + "0" * 64 + "` |\n| CX-10 | `core.alpha` |\n"
    assert _run(d, 4, signature_record=stale).status == "fail"
    unlisted = f"| sha256 | `{cb.sha256}` |\n"
    assert _run(d, 4, signature_record=unlisted).status == "fail"


def test_check04_record_abbreviated_ids() -> None:
    record = "| CX-41 | `core.eval_type_pre`, `_pilot` |\n"
    assert C._record_items(record, ["core.eval_type_pre", "core.eval_type_pilot"]) == {
        "core.eval_type_pre", "core.eval_type_pilot"}


def test_check06_flags_stale_hash_and_missing_question() -> None:
    cb = _cb(_mini())
    files = generate_all(cb)
    jev = next(f for f in files if f.name == "jev_questions.json")
    doc = json.loads(jev.content)
    doc["questions"][0]["item_hash"] = "0" * 64
    doc["questions"] = doc["questions"][:1]
    jev.content = json.dumps(doc)
    res = C.check_06_linkage(cb, C.Context(generated=files))
    assert any("is not the item's hash" in f for f in res.findings)
    assert any("core.beta: jev_choice item yields 0 questions" in f for f in res.findings)


def test_check07_gate_values_rounds_and_cycles() -> None:
    d = _mini()
    d["items"]["core.beta"]["gate"] = {"item": "core.alpha", "values": ["maybe"]}
    assert any("'maybe'" in f for f in _run(d, 7).findings)
    d = _mini()
    d["items"]["core.beta"]["round"] = 1
    assert any("is not after gate" in f for f in _run(d, 7).findings)
    d = _mini()
    d["items"]["core.alpha"]["gate"] = {"item": "core.beta", "values": ["yes_value"]}
    assert any("cycle" in f for f in _run(d, 7).findings)


def test_check08_codes() -> None:
    d = _mini()
    d["items"]["core.alpha"]["values"][1]["code"] = "unknown"
    d["items"]["core.beta"]["values"][1]["code"] = "Not-Snake"
    res = _run(d, 8)
    assert any("equals a missing token" in f for f in res.findings)
    assert any("not snake_case" in f for f in res.findings)
    d["items"]["core.alpha"]["missing_map"] = {"unknown": "unknown"}
    assert not any("core.alpha" in f for f in _run(d, 8).findings)


def test_check09_coder_fields() -> None:
    d = _mini()
    d["items"]["core.alpha"]["threshold"] = "none"
    d["items"]["core.gamma"]["coder"] = "mechanical"
    d["items"]["core.gamma"]["rules"] = "none"
    res = _run(d, 9)
    assert any("core.alpha: classifier without a threshold" in f for f in res.findings)
    assert any("core.gamma: mechanical item without rules" in f for f in res.findings)


def test_check10_long_pages() -> None:
    d = _mini()
    d["items"]["core.alpha"]["long_page_rule"] = "none"
    d["items"]["core.beta"]["long_page_rule"] = {"rule": "priority_order", "order": "S3 a"}
    res = _run(d, 10)
    assert any("core.alpha: page-level classifier" in f for f in res.findings)
    assert any("core.beta: priority_order does not list its order" in f for f in res.findings)


def test_check11_procurement_exclusions() -> None:
    d = _mini()
    d["items"]["core.alpha"]["input_text"] = "main_plus_chrome"
    d["items"]["core.alpha"]["pipelines"] = ["web_extract", "procurement"]
    res = _run(d, 11)
    assert any("chrome text item includes procurement" in f for f in res.findings)


def test_check12_version_steps() -> None:
    d = _mini()
    d["items"]["core.alpha"]["values"].append({"code": "third", "definition": _slot("Third.")})
    two_steps, one_step = _mini(), _mini()
    two_steps["release"]["label"] = "2.5"
    one_step["release"]["label"] = "2.6"
    assert _run(copy.deepcopy(d), 12, previous=_cb(two_steps)).status == "pass"
    res = _run(d, 12, previous=_cb(one_step))
    assert res.status == "fail" and "is 1 steps" in res.findings[0]
    assert _run(_mini(), 12).status == "n/a"


def test_check13_markers_and_status() -> None:
    d = _mini()
    d["items"]["core.alpha"]["values"][0]["definition"]["marker"] = "SPEC text - PI to write"
    d["items"]["core.beta"]["status"] = "slot"
    cb = _cb(d)
    res = _run(d, 13, signature_record=f"| sha256 | `{cb.sha256}` |")
    assert any("carries a marker" in f for f in res.findings)
    assert any("status 'slot'" in f for f in res.findings)
    d["release"]["status"] = "draft"
    assert _run(d, 13).status == "n/a"


def test_check14_translation() -> None:
    d = _mini()
    d["items"]["core.alpha"]["translation_v25"] = {"column": "alpha", "map": {"yes_value": "yes"}}
    res = _run(d, 14, v25_columns=("beta",))
    assert any("'no_value' neither mapped" in f for f in res.findings)
    assert any("core.beta: column 'beta' exists in v2.5" in f for f in res.findings)
    d["items"]["core.alpha"]["translation_v25"]["unmappable"] = ["no_value"]
    assert not any("core.alpha" in f for f in _run(d, 14).findings)


def test_check15_header_hash() -> None:
    cb = _cb(_mini())
    files = generate_all(cb)
    files[0].content = files[0].content.replace(cb.sha256, "x" * 64)
    assert C.check_15_hash(cb, C.Context(generated=files)).status == "fail"


def test_check16_every_value_carries_full_rules() -> None:
    cb = _cb(_mini())
    files = generate_all(cb)
    assert C.check_16_full_rules(cb, C.Context(generated=files)).status == "pass"
    jev = next(f for f in files if f.name == "jev_questions.json")
    doc = json.loads(jev.content)
    crit = doc["questions"][0]["criteria"][1]
    assert "Shared rule text." in crit["text"] and "Own rule of alpha." in crit["text"]
    crit["text"] = crit["text"].replace("Shared rule text.", "")
    jev.content = json.dumps(doc)
    res = C.check_16_full_rules(cb, C.Context(generated=files))
    assert any("core.alpha value 'no_value'" in f for f in res.findings)


def test_unexpressible_item_is_not_generated_and_is_reported() -> None:
    d = _mini()
    d["items"]["core.alpha"]["instruction"] = "none"
    cb = _cb(d)
    doc = json.loads(next(f for f in generate_all(cb) if f.name == "jev_questions.json").content)
    assert [q["item_id"] for q in doc["questions"]] == ["core.beta"]
    assert doc["not_generated"][0]["item_id"] == "core.alpha"


def test_generate_command_writes_files(tmp_path: Path) -> None:
    assert cli_main(["generate", "--repo-root", str(tmp_path)]) == 0
    assert (tmp_path / GENERATED_DIR / "manifest.json").exists()


# ---------------------------------------------------------------------------
# RC-D-005 forms (planning/t010/item-template-r5-amendments.md A1-A8)
# ---------------------------------------------------------------------------


def _all_pass(d: dict, tmp_path: Path) -> dict:
    cb = _cb(d)
    files = generate_all(cb)
    for f in files:
        (tmp_path / f.relpath).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f.relpath).write_bytes(f.bytes())
    ctx = C.Context(generated=files, repo_root=tmp_path, signature_record=f"| sha256 | `{cb.sha256}` |\n",
                    v25_columns=())
    return {r.number: (r.status, r.findings) for r in C.run_checks(cb, ctx)}


def _parts_item() -> dict:
    return _item("core.rel", level=["activity"], pass_=2, round=1, values={
        "structure": "Two linked parts in one item",
        "parts": ["relationship", "role"],
        "relationship": [{"code": "own", "definition": _slot("Own activity.")},
                         {"code": "unresolved", "definition": _slot("Not settled. The role is not asked.")}],
        "role": [{"code": "buyer", "definition": _slot("It buys.")}],
        "part_instructions": {"role": _slot("What part does it play?")},
        "role_gate": {"part": "role", "not_asked_when_relationship": ["unresolved"]},
    })


def test_parts_form_yields_one_question_per_part(tmp_path: Path) -> None:
    d = _mini()
    d["items"]["core.rel"] = _parts_item()
    results = _all_pass(d, tmp_path)
    assert all(s in ("pass", "n/a") for s, _ in results.values()), results
    doc = json.loads(next(f for f in generate_all(_cb(d)) if f.name == "jev_questions.json").content)
    qs = [q for q in doc["questions"] if q["item_id"] == "core.rel"]
    assert [q["question_id"] for q in qs] == ["core.rel", "core.rel#role"]
    assert qs[1]["instructions"] == "What part does it play?" and qs[1]["gate"]["key"] == "role_gate"
    del d["items"]["core.rel"]["values"]["part_instructions"]
    assert any("part 'role' without an instruction slot" in f for f in _run(d, 9).findings)


def test_computed_values_question_carries_rules_once(tmp_path: Path) -> None:
    d = _mini()
    d["items"]["core.year"] = _item("core.year", level=["activity"], pass_=2, round=1,
                                    values={"candidates": "deterministic year extraction, plus unknown (C16)"},
                                    long_page_rule="earliest_year")
    results = _all_pass(d, tmp_path)
    assert all(s in ("pass", "n/a") for s, _ in results.values()), results
    doc = json.loads(next(f for f in generate_all(_cb(d)) if f.name == "jev_questions.json").content)
    q = next(q for q in doc["questions"] if q["item_id"] == "core.year")
    assert q["computed_values"].startswith("deterministic") and "Own rule of year." in q["rules_text"]
    d["items"]["core.year"]["coder"] = "mechanical"
    assert any("computed value list" in f for f in _run(d, 1).findings)


def test_jev_choice_false_and_missing_choice(tmp_path: Path) -> None:
    d = _mini()
    alpha = d["items"]["core.alpha"]
    alpha["values"].append({"code": "set_mechanically", "definition": _slot("Set by a rule."), "jev_choice": False})
    alpha["rules"].append(_slot("not_documented: the page is silent."))
    alpha["jev_missing_choice"] = {"offered": ["not_documented"], "rule": ["items/core.alpha/rules/2"]}
    results = _all_pass(d, tmp_path)
    assert all(s in ("pass", "n/a") for s, _ in results.values()), results
    cb = _cb(d)
    files = generate_all(cb)
    jev = next(f for f in files if f.name == "jev_questions.json")
    doc = json.loads(jev.content)
    q = next(q for q in doc["questions"] if q["item_id"] == "core.alpha")
    assert [c["code"] for c in q["criteria"]] == ["yes_value", "no_value", "not_documented"]
    q["criteria"] = q["criteria"][:2]
    jev.content = json.dumps(doc)
    assert any("are not the offered values" in f for f in C.check_16_full_rules(cb, C.Context(generated=files)).findings)
    alpha["jev_missing_choice"] = {"offered": ["not_documented"], "rule": "none"}
    assert any("without rule slots" in f for f in _run(d, 1).findings)


def test_any_value_gate_missing_tokens_none_and_values_none_forms(tmp_path: Path) -> None:
    d = _mini()
    d["items"]["core.alpha"]["missing_tokens"] = "none"
    d["items"]["core.number"] = _item("core.number", linkage="extractor", coder="quote_step", pass_="none",
                                      instruction="none", values="none", answer_type="number", threshold="none",
                                      long_page_rule="none", rules=[_slot("Copy the number.")],
                                      gate={"item": "core.alpha", "values": ["yes_value"]})
    d["items"]["core.unit"] = _item("core.unit", round=2, gate={"item": "core.number", "values": "any"})
    d["items"]["core.flag"] = _item("core.flag", linkage="deterministic", coder="derived", pass_="none",
                                    instruction="none", values="none", answer_type="single", threshold="none",
                                    long_page_rule="none", rules=[_slot("Derived.")], value_vocabulary="family")
    d["items"]["core.after_flag"] = _item("core.after_flag", linkage="deterministic", coder="mechanical",
                                          pass_="none", instruction="none", values="none", answer_type="text",
                                          threshold="none", long_page_rule="none", rules=[_slot("Name it.")],
                                          gate={"item": "core.flag", "values": ["verdict"]})
    results = _all_pass(d, tmp_path)
    assert all(s in ("pass", "n/a") for s, _ in results.values()), results
    d["items"]["core.number"]["gate"] = "none"                 # a quote-step gate item: noted, not failed (A5)
    assert _run(d, 7).status == "pass"
    d["items"]["core.ent"] = _item("core.ent", pass_="none")   # a classifier gate item without a round fails
    d["items"]["core.after_ent"] = _item("core.after_ent", round=2, gate={"item": "core.ent", "values": ["yes_value"]})
    assert any("a classifier with no pass/round" in f for f in _run(d, 7).findings)
    d["items"]["core.flag"]["value_vocabulary"] = "no_such_list"
    assert any("names no vocabulary" in f for f in _run(d, 1).findings)


def test_shared_prompt_slots_unblock_system_and_part_prompts(tmp_path: Path) -> None:
    d = _mini()
    d["shared"] = {"part_prompt": {"sentence": _slot("Only part of the page."),
                                   "temporary_answer": {"label": _slot("not covered by this part"),
                                                        "meaning": _slot("Not in this part.")}},
                   "system_prompt": {**_slot("You are a coder."), "applies_to": ["pass 1"]}}
    results = _all_pass(d, tmp_path)
    assert all(s in ("pass", "n/a") for s, _ in results.values()), results
    cb = _cb(d)
    files = generate_all(cb)
    assert "You are a coder." in next(f for f in files if f.name == "system_prompt.md").content
    manifest = json.loads(next(f for f in files if f.name == "manifest.json").content)
    assert manifest["blocked_targets"] == []
    jev = next(f for f in files if f.name == "jev_questions.json")
    doc = json.loads(jev.content)
    assert doc["part_prompt"]["sentence"] == "Only part of the page."
    del doc["questions"][0]["part_prompt_answer"]
    jev.content = json.dumps(doc)
    assert any("no temporary answer" in f for f in C.check_16_full_rules(cb, C.Context(generated=files)).findings)


#: The RC-D-005 approved candidate (r8 sign-off build, PI 2026-10-30 "approved
#: and cut"), copied byte for byte from planning/t010/candidate-r8/ on
#: reclass/rc-d-005-codebook, so the schema is tested on both the signed file
#: and the candidate shapes (item-template amendments D1-D8).
R8_CANDIDATE = REPO_ROOT / "tests" / "fixtures" / "codebook" / "codebook-r8-signoff.yaml"
R8_SHA256 = "f0b1348cddbbe1ab0de8e16b80dae64a3e3400fe71788a6673f5cfc52348c72f"


def test_schema_validates_signed_file_and_rc_d_005_candidate() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((REPO_ROOT / "codebook" / "schema.json").read_text(encoding="utf-8"))
    cand = load_codebook(R8_CANDIDATE)
    assert cand.sha256 == R8_SHA256
    for cb in (load_codebook(), cand):
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(cb.data))
        assert not errors, [(list(e.absolute_path)[:3], e.message[:120]) for e in errors[:5]]
