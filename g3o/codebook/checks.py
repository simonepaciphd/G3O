"""Generator checks 1-16 (planning/t010/item-template.md §4; T-013 implements).

Each check returns a :class:`CheckResult` with ``status`` ``pass`` / ``fail`` /
``n/a`` and one finding per failing item or field, with evidence. Checks never
repair the codebook and never relax to make a file pass: a failure on a signed
file is fixed by a codebook delta and a re-signature.

Scope: findings on items outside the release's build scope
(``release.build_scope_v2_7``: ``core``; the procurement and AI-text
placeholders, PI ruling P1) are reported as notes and do not fail a check.

The allowed forms are read from item-template §2 as written. Where the
template's wording needs a reading to be testable, the reading is stated in
the check's docstring.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.codebook.generators import (
    ITEM_MARKER,
    RULES_HEADING,
    VALUE_MARKER,
    GeneratedFile,
    generate_all,
)
from g3o.codebook.loader import NONE, REPO_ROOT, Codebook, sha256_bytes

SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
ID_RE = re.compile(r"^(?P<ns>[a-z]+)\.(?P<name>[a-z0-9_]+)$")
LABEL_RE = re.compile(r"^\d+\.\d+$")
FROZEN_RE = re.compile(r"^CX-\d+\.\d+:CX-\d+[a-z]?(\.\.CX-\d+[a-z]?)?$")

TEMPLATE_FIELDS = (
    "id", "family", "name", "level", "pipelines", "linkage", "coder", "pass", "round",
    "gate", "answer_type", "instruction", "values", "rules", "order_tie_rule",
    "long_page_rule", "support_required", "downgrade_target", "threshold",
    "missing_tokens", "input_text", "visibility", "frozen_signature",
    "version_introduced", "translation_v25", "refs", "status",
)
LINKAGE = {"jev_choice", "deterministic", "extractor", "pipeline"}
CODER = {"classifier", "mechanical", "quote_step", "derived"}
PASS = {1, 2, "stage6", NONE}
ANSWER = {"single", "multi", "yes_no", "text", "number", "date", "list"}
#: ``values: none`` is allowed for these answer types (field 13; ``list`` added
#: by item-template amendment A1: a list of extracted strings has no codes) ...
NO_VALUES_OK = {"text", "number", "date", "list"}
#: ... and for every mechanical or derived item (amendment A1, F1 a), whose
#: codes, if any, come from ``value_codes``, ``value_vocabulary`` or yes_no.
NO_VALUES_CODERS = {"mechanical", "derived"}
#: The "any value" gate form (amendment A3, F6 a): any real value opens it.
ANY_VALUE = "any"
ORDER_TIE = {"first_in_order", "single_best", "all_that_apply", NONE}
LONG_PAGE = {"first_section", "any_yes", "priority_order", "earliest_year", "combined_list",
             "highest_probability", NONE}
INPUT_TEXT = {"main", "main_plus_chrome", "links", "quote_source", "metadata"}
VISIBILITY = {"public", "internal", "public_derived"}
STATUS = {"slot", "pi_edited", "signed"}
RELEASE_STATUS = {"draft", "signed"}
THRESHOLD = {"metric": "chosen_answer_probability", "bar": 0.8}


@dataclass
class CheckResult:
    number: int
    name: str
    status: str = "pass"
    findings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, finding: str) -> None:
        self.status = "fail"
        self.findings.append(finding)

    def line(self) -> str:
        head = f"check {self.number:>2} {self.name}: {self.status.upper()}"
        if self.findings:
            head += f" ({len(self.findings)} findings)"
        return head


@dataclass
class Context:
    """Inputs the checks need besides the codebook."""

    generated: list[GeneratedFile]
    repo_root: Path = REPO_ROOT
    signature_record: str | None = None
    previous: Codebook | None = None
    v25_columns: tuple[str, ...] | None = None

    def file(self, name: str) -> GeneratedFile | None:
        return next((f for f in self.generated if f.name == name), None)


def _scoped(cb: Codebook, res: CheckResult, item_id: str, finding: str) -> None:
    if cb.in_build_scope(item_id):
        res.fail(f"{item_id}: {finding}")
    else:
        res.notes.append(f"(outside build scope) {item_id}: {finding}")


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _short(value: Any, n: int = 90) -> str:
    s = json.dumps(value, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[: n - 3] + "..."


def _value_codes(cb: Codebook, item_id: str) -> list[str] | None:
    values = cb.value_list(item_id)
    return None if values is None else [str(v["code"]) for v in values]


def _tokens(item: dict[str, Any]) -> list[str]:
    """``missing_tokens`` as a list (``none`` is the empty set, amendment A4)."""
    mt = item.get("missing_tokens")
    return [str(t) for t in mt] if isinstance(mt, list) else []


# ---------------------------------------------------------------------------
# check 1
# ---------------------------------------------------------------------------


def check_01_template_complete(cb: Codebook, ctx: Context) -> CheckResult:
    """Every item has all 27 fields, each in an allowed form of item-template §2,
    with no blanks. ``family`` must come from a fixed list in ``vocabularies``;
    ``gate`` is ``none`` or ``{item, values}`` (extra keys allowed);
    ``values`` may be ``none`` only for text / number / date items; ``status``
    is one of slot / pi_edited / signed; the release block's ``status`` is
    draft / signed (§1)."""
    res = CheckResult(1, "template complete")
    status = cb.release.get("status")
    if status not in RELEASE_STATUS:
        res.fail(f"release.status: {_short(status)} is not one of draft / signed (§1)")
    for key in ("label", "signature_record", "hash_rule"):
        if _blank(cb.release.get(key)):
            res.fail(f"release.{key}: missing")
    families = cb.vocab_values("family")
    if not families:
        res.fail("vocabularies: no `family` list; field 2 requires family labels from a fixed list in vocabularies")
    levels, pipelines = set(cb.vocab_values("level")), set(cb.vocab_values("pipeline"))
    missing_vocab = set(cb.vocab_values("missing"))
    namespaces = {str(n) for n in cb.release.get("namespaces") or []}

    for item_id, item in cb.items.items():
        def bad(f: str, msg: str, _id: str = item_id) -> None:
            _scoped(cb, res, _id, f"field {f}: {msg}")

        for f in TEMPLATE_FIELDS:
            if f not in item:
                bad(f, "missing")
            elif _blank(item[f]):
                bad(f, "blank")
        m = ID_RE.match(str(item.get("id")))
        if item.get("id") != item_id:
            bad("id", f"{item.get('id')!r} differs from its key")
        if not m or m.group("ns") not in namespaces:
            bad("id", f"{item.get('id')!r} is not <namespace>.<name> with a declared namespace")
        if families and item.get("family") not in families:
            bad("family", f"{item.get('family')!r} not in vocabularies.family")
        if not SNAKE.match(str(item.get("name"))):
            bad("name", f"{item.get('name')!r} is not snake_case")
        for f, allowed in (("level", levels), ("pipelines", pipelines)):
            v = item.get(f)
            if not isinstance(v, list) or not v or not set(map(str, v)) <= allowed:
                bad(f, f"{_short(v)} is not a non-empty subset of vocabularies.{'level' if f == 'level' else 'pipeline'}")
        for f, allowed in (("linkage", LINKAGE), ("coder", CODER), ("answer_type", ANSWER),
                           ("order_tie_rule", ORDER_TIE), ("input_text", INPUT_TEXT),
                           ("visibility", VISIBILITY), ("status", STATUS)):
            if item.get(f) not in allowed:
                bad(f, f"{_short(item.get(f))} not in {sorted(allowed)}")
        if item.get("pass") not in PASS:
            bad("pass", f"{_short(item.get('pass'))} not in 1 / 2 / stage6 / none")
        rnd = item.get("round")
        if not (rnd == NONE or (isinstance(rnd, int) and not isinstance(rnd, bool) and rnd >= 1)):
            bad("round", f"{_short(rnd)} is not an integer >= 1 or none")
        gate = item.get("gate")
        if gate != NONE and not (isinstance(gate, dict) and isinstance(gate.get("item"), str)
                                 and (isinstance(gate.get("values"), list) or gate.get("values") == ANY_VALUE)):
            bad("gate", f"{_short(gate)} is not none or an item id + list of values (or `any`, amendment A3)")
        ins = item.get("instruction")
        if ins != NONE and cb.slot_text(ins) is None:
            bad("instruction", f"{_short(ins)} is not a text slot or none")
        values = item.get("values")
        if values == NONE:
            if item.get("answer_type") not in NO_VALUES_OK and item.get("coder") not in NO_VALUES_CODERS:
                bad("values", f"none, but answer_type {item.get('answer_type')!r} is not text / number / date / list "
                              f"and coder {item.get('coder')!r} is not mechanical / derived (amendment A1)")
            if "value_vocabulary" in item and not cb.vocab_values(str(item["value_vocabulary"])):
                bad("value_vocabulary", f"{_short(item['value_vocabulary'])} names no vocabulary with values")
            vc = item.get("value_codes")
            if vc is not None and not (isinstance(vc, list) and vc and all(SNAKE.match(str(c)) for c in vc)):
                bad("value_codes", f"{_short(vc)} is not a non-empty list of snake_case codes")
        elif cb.parts(item_id) is not None:
            for name, part in cb.parts(item_id) or []:
                for n, v in enumerate(part):
                    if cb.slot_text(v.get("definition")) is None:
                        bad("values", f"part {name!r} value {n} ({v.get('code')!r}) definition is not a text slot")
        elif cb.computed_values(item_id) is not None:
            if item.get("coder") != "classifier" or item.get("answer_type") != "single":
                bad("values", "computed value list (amendment A2) on an item that is not a single-answer classifier")
        elif cb.value_list(item_id) is None:
            bad("values", f"not an ordered list of {{code, definition}}, a parts form or a computed list: {_short(values)}")
        else:
            for n, v in enumerate(values):
                if cb.slot_text(v.get("definition")) is None:
                    bad("values", f"value {n} ({v.get('code')!r}) definition is not a text slot")
        rules = item.get("rules")
        if rules != NONE:
            if not isinstance(rules, list):
                bad("rules", f"{_short(rules)} is not a list or none")
            else:
                for n, r in enumerate(rules):
                    if isinstance(r, str):
                        if r not in cb.shared_rules:
                            bad("rules", f"rule {n} references unknown shared rule {r!r}")
                    elif cb.slot_text(r) is None:
                        bad("rules", f"rule {n} is not a text slot (keys {sorted(r) if isinstance(r, dict) else type(r).__name__})")
        lpr = item.get("long_page_rule")
        rule_name = lpr.get("rule") if isinstance(lpr, dict) else lpr
        if rule_name not in LONG_PAGE:
            bad("long_page_rule", f"rule {_short(rule_name)} not in {sorted(LONG_PAGE)}")
        if not isinstance(item.get("support_required"), bool):
            bad("support_required", f"{_short(item.get('support_required'))} is not true / false")
        codes = _value_codes(cb, item_id) or []
        dt = item.get("downgrade_target")
        if dt not in {"unknown", "tag_only", NONE} and dt not in codes:
            bad("downgrade_target", f"{_short(dt)} is not a value code, unknown, tag_only or none")
        thr = item.get("threshold")
        if thr != NONE and thr != THRESHOLD:
            bad("threshold", f"{_short(thr)} is not {THRESHOLD} or none")
        mt = item.get("missing_tokens")
        if mt != NONE and (not isinstance(mt, list) or not set(map(str, mt)) <= missing_vocab):
            bad("missing_tokens", f"{_short(mt)} is not none or a subset of vocabularies.missing (amendment A4)")
        jm = item.get("jev_missing_choice")
        if jm is not None:
            offered = jm.get("offered") if isinstance(jm, dict) else None
            if not isinstance(offered, list) or not set(map(str, offered)) <= set(_tokens(item)):
                bad("jev_missing_choice", f"offered {_short(offered)} is not a subset of the item's missing_tokens")
            elif offered and not (isinstance(jm.get("rule"), list) and jm["rule"]
                                  and all(cb.resolve_text(str(p)) is not None for p in jm["rule"])):
                bad("jev_missing_choice", f"offers {offered} without rule slots giving the meaning: {_short(jm.get('rule'))}")
        fs = item.get("frozen_signature")
        if fs != NONE and not (isinstance(fs, str) and FROZEN_RE.match(fs)):
            bad("frozen_signature", f"{_short(fs)} is not none or a signed questionnaire row id")
        vi = item.get("version_introduced")
        if not (isinstance(vi, str) and LABEL_RE.match(vi)):
            bad("version_introduced", f"{_short(vi)} is not a release label")
        tr = item.get("translation_v25")
        if tr != "new" and not (isinstance(tr, dict) and "column" in tr
                                and (isinstance(tr.get("map"), dict) or tr.get("map") == "identity")):
            bad("translation_v25", f"{_short(tr)} is not new or {{column, map}}")
        refs = item.get("refs")
        if not (isinstance(refs, list) and refs and all(isinstance(r, str) and r for r in refs)):
            bad("refs", f"{_short(refs)} is not a non-empty list of ids")
    return res


# ---------------------------------------------------------------------------
# checks 2-4
# ---------------------------------------------------------------------------


def check_02_ids_stable(cb: Codebook, ctx: Context) -> CheckResult:
    """IDs are unique; against the previous signed release (when given), no ID
    disappears without a retirement entry and no ID changes meaning (same id,
    different name or value codes) silently."""
    res = CheckResult(2, "IDs stable")
    ids = [str(it.get("id")) for it in cb.items.values()]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        res.fail(f"duplicate ids: {dupes}")
    names = [str(it.get("name")) for k, it in cb.items.items() if cb.in_build_scope(k)]
    dn = sorted({n for n in names if names.count(n) > 1})
    if dn:
        res.fail(f"duplicate column names in build scope: {dn}")
    if ctx.previous is None:
        res.notes.append("no previous codebook release supplied: first codebook release; "
                         "the disappearance / meaning comparison has nothing to compare against")
        return res
    retired = {str(r.get("id") or r.get("name")) for r in cb.retired if isinstance(r, dict)}
    for item_id, old in ctx.previous.items.items():
        new = cb.items.get(item_id)
        if new is None:
            if item_id not in retired:
                res.fail(f"{item_id}: in the previous release, gone without a retirement entry")
            continue
        if old.get("name") != new.get("name"):
            res.fail(f"{item_id}: column name changed {old.get('name')!r} -> {new.get('name')!r}")
    return res


def _record_hash(record: str) -> str | None:
    m = re.search(r"\|\s*sha256\s*\|\s*`([0-9a-f]{64})`", record)
    return m.group(1) if m else None


def _record_items(record: str, item_ids: list[str]) -> set[str]:
    """Items listed in the record's CX table. Cells may abbreviate a run of ids
    with a shared prefix (`core.evaluation_type_x`, `_y`)."""
    listed: set[str] = set()
    for line in record.splitlines():
        if not line.startswith("| CX-"):
            continue
        cell = line.rstrip("|").split("|")[-1]
        tokens = re.findall(r"`([^`]+)`", cell)
        full = [t for t in tokens if "." in t]
        for t in tokens:
            if "." in t:
                listed.add(t)
            elif t.startswith("_"):
                for base in full:
                    for cut in range(len(base), 0, -1):
                        if base[cut - 1] == "_" and base[: cut - 1] + t in item_ids:
                            listed.add(base[: cut - 1] + t)
                            break
    return listed


def check_03_verbatim(cb: Codebook, ctx: Context) -> CheckResult:
    """Every slot text a generated file uses appears byte-identical in it. For
    ``.json`` files the declared escaping step is JSON string escaping, so the
    text is compared against the decoded strings."""
    res = CheckResult(3, "verbatim only")
    for f in ctx.generated:
        if not f.used_slots:
            continue
        if f.is_json:
            haystack = "\x00".join(_json_strings(json.loads(f.content)))
        else:
            haystack = f.content
        for path, text in f.used_slots:
            if text not in haystack:
                res.fail(f"{f.name}: slot {path} not byte-identical in output")
        res.notes.append(f"{f.name}: {len(f.used_slots)} slot uses verified")
    # every slot text in the outputs is the codebook's: compare against the source slot
    for f in ctx.generated:
        for path, text in f.used_slots:
            src = _resolve_slot(cb, path)
            if src is not None and src != text:
                res.fail(f"{f.name}: slot {path} text differs from the codebook")
    return res


def _json_strings(x: Any) -> list[str]:
    """Every string in a decoded JSON document (undoes the declared escaping step)."""
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _json_strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in _json_strings(v)]
    return []


def _resolve_slot(cb: Codebook, path: str) -> str | None:
    node: Any = cb.data
    for part in path.split("/"):
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            if part not in node:
                return None
            node = node[part]
        else:
            return None
    return cb.slot_text(node)


def check_04_frozen(cb: Codebook, ctx: Context) -> CheckResult:
    """Each item with a ``frozen_signature`` is covered by its signature record:
    the record's sha256 equals this file's sha256 (the record signs the file
    hash, A-001) and the record lists the item. Any change to the file, and so
    to a frozen text, fails until the record is updated by a re-signature."""
    res = CheckResult(4, "frozen items")
    frozen = [k for k, it in cb.items.items() if it.get("frozen_signature") not in (None, NONE)]
    if not frozen:
        res.status = "n/a"
        return res
    if ctx.signature_record is None:
        res.fail(f"no signature record found for {len(frozen)} frozen items")
        return res
    h = _record_hash(ctx.signature_record)
    if h != cb.sha256:
        res.fail(f"signature record sha256 {h} != codebook sha256 {cb.sha256}; all {len(frozen)} frozen items unsigned")
    listed = _record_items(ctx.signature_record, list(cb.items))
    for item_id in frozen:
        if item_id not in listed:
            _scoped(cb, res, item_id, f"frozen ({cb.items[item_id]['frozen_signature']}) but not listed in the signature record")
    extra = sorted(listed - set(frozen))
    if extra:
        res.fail(f"signature record lists items with no frozen_signature: {extra}")
    res.notes.append(f"{len(frozen)} frozen items; record hash {'matches' if h == cb.sha256 else 'differs'}; "
                     f"{len(listed & set(frozen))} listed")
    return res


# ---------------------------------------------------------------------------
# check 5
# ---------------------------------------------------------------------------


def check_05_no_drift(cb: Codebook, ctx: Context) -> CheckResult:
    """Regenerating reproduces every committed generated file byte for byte."""
    res = CheckResult(5, "no drift")
    for f in ctx.generated:
        committed = ctx.repo_root / f.relpath
        if not committed.exists():
            res.fail(f"{f.relpath}: not committed")
        elif committed.read_bytes() != f.bytes():
            res.fail(f"{f.relpath}: differs from regeneration")
    gen_dir = ctx.repo_root / "g3o" / "codebook" / "generated"
    expected = {f.name for f in ctx.generated} | {"__init__.py", ".gitattributes"}
    if gen_dir.exists():
        for p in sorted(gen_dir.iterdir()):
            if p.is_file() and p.name not in expected:
                res.fail(f"{p.relative_to(ctx.repo_root).as_posix()}: no generator produces it")
    return res


# ---------------------------------------------------------------------------
# check 6
# ---------------------------------------------------------------------------


def check_06_linkage(cb: Codebook, ctx: Context) -> CheckResult:
    """A-001 linkage: every generated question, prompt section and enum names an
    existing item and that item's current hash; each ``jev_choice`` item yields
    exactly one question and each ``extractor`` item exactly one prompt section."""
    res = CheckResult(6, "linkage (A-001)")
    build = cb.build_items()

    def verify(unit: str, item_id: str, item_hash: str) -> None:
        if item_id not in cb.items:
            res.fail(f"{unit}: names no item ({item_id})")
        elif item_hash != cb.item_hash(item_id):
            res.fail(f"{unit}: {item_id} hash {item_hash[:12]} is not the item's hash")

    jev = ctx.file("jev_questions.json")
    if jev is None:
        res.fail("jev_questions.json not generated")
    else:
        doc = json.loads(jev.content)
        seen = [q["item_id"] for q in doc["questions"]]
        qids = [q.get("question_id") for q in doc["questions"]]
        for d in sorted({x for x in qids if qids.count(x) > 1}):
            res.fail(f"question id {d!r} is not unique")
        for q in doc["questions"]:
            verify(f"question {q.get('question_id')}", q.get("item_id", ""), q.get("item_hash", ""))
        for item_id, item in build.items():
            want = len(cb.parts(item_id) or [None])      # one question per part (amendment A6)
            if item.get("linkage") == "jev_choice" and seen.count(item_id) != want:
                why = next((x["reason"] for x in doc.get("not_generated", []) if x["item_id"] == item_id), "")
                res.fail(f"{item_id}: jev_choice item yields {seen.count(item_id)} questions (expected {want})"
                         + (f" ({why})" if why else ""))
        for item_id in seen:
            if item_id in cb.items and cb.items[item_id].get("linkage") != "jev_choice":
                res.fail(f"{item_id}: question generated for a non-jev_choice item")

    ext = ctx.file("extractor_prompt_sections.md")
    if ext is None:
        res.fail("extractor_prompt_sections.md not generated")
    else:
        marks = re.findall(r"<!-- item: (\S+) sha256: ([0-9a-f]{64}) -->", ext.content)
        seen = [m[0] for m in marks]
        for item_id, h in marks:
            verify(f"prompt section {item_id}", item_id, h)
        for item_id, item in build.items():
            if item.get("linkage") == "extractor" and seen.count(item_id) != 1:
                res.fail(f"{item_id}: extractor item yields {seen.count(item_id)} prompt sections")

    enums = ctx.file("enums.py")
    if enums is None:
        res.fail("enums.py not generated")
    else:
        for item_id, h in re.findall(r"^    '([^']+)': \('([0-9a-f]{64})',", enums.content, re.M):
            verify(f"enum {item_id}", item_id, h)
    schemas = ctx.file("item_schemas.json")
    if schemas is not None:
        for col, s in json.loads(schemas.content)["$defs"].items():
            verify(f"schema {col}", s.get("x-item-id", ""), s.get("x-item-hash", ""))
    return res


# ---------------------------------------------------------------------------
# checks 7-11
# ---------------------------------------------------------------------------


def _pass_rank(p: Any) -> int | None:
    return {1: 1, 2: 2, "stage6": 3}.get(p)


def check_07_gates(cb: Codebook, ctx: Context) -> CheckResult:
    """A gate names an existing item and existing values (the gate item's codes
    in any template form, or its missing tokens; ``values: any`` names no
    value, amendment A3); gates have no cycles; when the gated item has a
    classifier round, its round is later than its gate's round in the same pass,
    or its pass is later. The round comparison needs a classifier round on both
    sides: a gate item that is not a classifier (a quote step or mechanical
    item, e.g. the scale number gating the unit under F6 a) has no round, and
    its order before the items it gates is the signed combining rule
    (``combining_conventions.gate_items_first``: "activity_type and action_type
    (and the scale number) are combined before the items they gate"), so it is
    noted, not failed (amendment A5, round 2). A classifier gate item with no
    round still fails. Applicability-table gates (``key`` + ``cells``) are
    checked the same way on their key item and cell keys."""
    res = CheckResult(7, "gates")
    edges: dict[str, str] = {}
    for item_id, item in cb.items.items():
        gate = item.get("gate")
        if gate == NONE:
            continue
        if not isinstance(gate, dict):
            _scoped(cb, res, item_id, f"gate {_short(gate)} is not a mapping")
            continue
        target = gate.get("item") or gate.get("key")
        if not isinstance(target, str):
            _scoped(cb, res, item_id, f"gate names no item: {_short(gate)}")
            continue
        if target not in cb.items:
            _scoped(cb, res, item_id, f"gate item {target!r} does not exist")
            continue
        edges[item_id] = target
        allowed = set(cb.codes(target) or []) | set(_tokens(cb.items[target]))
        named = gate.get("values") if "item" in gate else list((gate.get("cells") or {}).keys())
        target_values = cb.items[target].get("values")
        if named == ANY_VALUE:
            named = []                                   # amendment A3: any real value of an existing item
        for v in named or []:
            if str(v) not in allowed:
                why = " (it has no value list: values none)" if target_values == NONE else ""
                _scoped(cb, res, item_id, f"gate value {v!r} is not a value or missing token of {target}{why}; "
                                          f"allowed: {sorted(allowed)}")
        p_gate_raw, r_gate = cb.items[target].get("pass"), cb.items[target].get("round")
        r_gated = item.get("round")
        p_gated, p_gate = _pass_rank(item.get("pass")), _pass_rank(p_gate_raw)
        if isinstance(r_gated, int):
            if (p_gate is None or not isinstance(r_gate, int)) and cb.items[target].get("coder") != "classifier":
                res.notes.append(f"{item_id}: gated on {target} ({cb.items[target].get('coder')}, no round); order by "
                                 "combining_conventions.gate_items_first, no round comparison (amendment A5)")
            elif p_gate is None or not isinstance(r_gate, int):
                _scoped(cb, res, item_id, f"round {r_gated} (pass {item.get('pass')}) gated on {target}, a classifier "
                                          f"with no pass/round (pass {p_gate_raw}, round {r_gate})")
            elif p_gated is not None and (p_gated < p_gate or (p_gated == p_gate and r_gated <= r_gate)):
                _scoped(cb, res, item_id, f"pass {item.get('pass')} round {r_gated} is not after gate {target} "
                                          f"pass {p_gate_raw} round {r_gate}")
    for start in edges:
        seen, node = {start}, edges[start]
        while node in edges:
            if node in seen:
                res.fail(f"gate cycle through {start}")
                break
            seen.add(node)
            node = edges[node]
    return res


def check_08_values(cb: Codebook, ctx: Context) -> CheckResult:
    """Codes are unique and snake_case within an item and never equal a missing
    token (frozen items exempt through ``missing_map``)."""
    res = CheckResult(8, "values")
    missing = set(cb.vocab_values("missing"))
    for item_id, item in cb.items.items():
        lists = [("", _value_codes(cb, item_id))]
        if cb.parts(item_id) is not None:             # amendment A6: codes checked per part
            lists = [(f"part {name!r}: ", [str(v["code"]) for v in part]) for name, part in cb.parts(item_id) or []]
        exempt = set((item.get("missing_map") or {}).keys()) if isinstance(item.get("missing_map"), dict) else set()
        for label, codes in lists:
            if codes is None:
                continue
            for c in sorted({c for c in codes if codes.count(c) > 1}):
                _scoped(cb, res, item_id, f"{label}duplicate code {c!r}")
            for c in codes:
                if not SNAKE.match(c):
                    _scoped(cb, res, item_id, f"{label}code {c!r} is not snake_case")
                if c in missing and c not in exempt:
                    _scoped(cb, res, item_id, f"{label}code {c!r} equals a missing token")
    return res


def check_09_coder_fits(cb: Codebook, ctx: Context) -> CheckResult:
    """classifier: instruction, value definitions and a threshold; mechanical and
    derived: rules and no threshold; quote_step: ``support_required`` set."""
    res = CheckResult(9, "coder fits fields")
    for item_id, item in cb.items.items():
        coder = item.get("coder")
        if coder == "classifier":
            if cb.instruction(item_id) is None:
                _scoped(cb, res, item_id, "classifier without an instruction slot")
            values = cb.value_list(item_id)
            parts = cb.parts(item_id)
            if parts is not None:                     # amendment A6
                for n, (name, part) in enumerate(parts):
                    if n and cb.part_instruction(item_id, n) is None:
                        _scoped(cb, res, item_id, f"classifier part {name!r} without an instruction slot")
                    if any(cb.part_definition(item_id, name, i) is None for i in range(len(part))):
                        _scoped(cb, res, item_id, f"classifier part {name!r} without value definitions")
            elif cb.computed_values(item_id) is not None:
                pass                                  # amendment A2: choices computed per row
            elif values is None or any(cb.definition(item_id, n) is None for n in range(len(values))):
                _scoped(cb, res, item_id, f"classifier without value definitions (values: {_short(item.get('values'), 60)})")
            if item.get("threshold") == NONE:
                _scoped(cb, res, item_id, "classifier without a threshold")
        elif coder in ("mechanical", "derived"):
            if item.get("rules") in (NONE, None, []):
                _scoped(cb, res, item_id, f"{coder} item without rules")
            if item.get("threshold") != NONE:
                _scoped(cb, res, item_id, f"{coder} item with a threshold")
        elif coder == "quote_step":
            if not isinstance(item.get("support_required"), bool):
                _scoped(cb, res, item_id, "quote_step item without support_required")
    return res


def _order_listed(lpr: dict[str, Any]) -> bool:
    if isinstance(lpr.get("order"), list) and lpr["order"]:
        return True
    tiers = lpr.get("tiers")
    return isinstance(tiers, list) and bool(tiers) and all(isinstance(t, list) for t in tiers)


def check_10_long_pages(cb: Codebook, ctx: Context) -> CheckResult:
    """Every page-level classifier item declares a long-page rule other than
    ``none``; every ``priority_order`` rule lists its order (a list, or tiers
    of lists)."""
    res = CheckResult(10, "long pages")
    for item_id, item in cb.items.items():
        lpr = item.get("long_page_rule")
        name = lpr.get("rule") if isinstance(lpr, dict) else lpr
        if item.get("coder") == "classifier" and "page" in (item.get("level") or []) and name in (NONE, None):
            _scoped(cb, res, item_id, "page-level classifier item with long_page_rule none")
        if name == "priority_order" and not (isinstance(lpr, dict) and _order_listed(lpr)):
            _scoped(cb, res, item_id, f"priority_order does not list its order (order: {_short(lpr.get('order') if isinstance(lpr, dict) else None)})")
    return res


#: How check 11 recognises the r2#54 item kinds (template §4 check 11).
def _r2_54_kind(item: dict[str, Any]) -> str | None:
    name = str(item.get("name"))
    if item.get("family") == "completeness" or name.endswith("_complete"):
        return "completeness"
    if item.get("input_text") == "main_plus_chrome":
        return "chrome text"
    if item.get("input_text") == "links" or "link" in name or "follow" in name:
        return "link-following"
    if name == "page_review_state":
        return "link review state"
    return None


def check_11_coverage(cb: Codebook, ctx: Context) -> CheckResult:
    """Each item names at least one pipeline; link-following, completeness, link
    review state and chrome-text items exclude ``procurement`` (r2#54). Kinds
    are recognised by: family ``completeness`` or a ``*_complete`` name;
    ``input_text`` ``main_plus_chrome``; ``input_text`` ``links`` or a name with
    ``link`` / ``follow``; the ``page_review_state`` item (which records links
    not followed)."""
    res = CheckResult(11, "coverage")
    for item_id, item in cb.items.items():
        pipes = item.get("pipelines")
        if not isinstance(pipes, list) or not pipes:
            _scoped(cb, res, item_id, "names no pipeline")
            continue
        kind = _r2_54_kind(item)
        if kind:
            res.notes.append(f"{item_id}: r2#54 kind '{kind}', pipelines {pipes}")
            if "procurement" in pipes:
                _scoped(cb, res, item_id, f"{kind} item includes procurement (pipelines {pipes})")
    return res


# ---------------------------------------------------------------------------
# checks 12-16
# ---------------------------------------------------------------------------


def _label_steps(old: str, new: str) -> int | None:
    try:
        o, n = [int(x) for x in old.split(".")], [int(x) for x in new.split(".")]
    except ValueError:
        return None
    if o[0] != n[0]:
        return None
    return n[1] - o[1]


def check_12_version_steps(cb: Codebook, ctx: Context) -> CheckResult:
    """A value list changed against the previous release requires the label to
    rise by two steps (C-007, counted per release, r2#5)."""
    res = CheckResult(12, "version steps")
    if ctx.previous is None:
        res.status = "n/a"
        res.notes.append("no previous codebook release supplied: 2.7 is the first codebook release; "
                         "v2.5 had no codebook file to diff against")
        return res
    changed = [i for i in cb.items if i in ctx.previous.items
               and _value_codes(cb, i) != _value_codes(ctx.previous, i)]
    if changed:
        steps = _label_steps(ctx.previous.label, cb.label)
        if steps is None or steps < 2:
            res.fail(f"value lists changed ({changed[:5]}{'...' if len(changed) > 5 else ''}) but label "
                     f"{ctx.previous.label} -> {cb.label} is {steps} steps")
    return res


def check_13_signoff_gate(cb: Codebook, ctx: Context) -> CheckResult:
    """A signed release build fails if any slot still carries a marker or any
    item's ``status`` is not ``signed``. The build counts as signed when its
    signature record holds this file's sha256 (``release.status`` says so too)."""
    res = CheckResult(13, "sign-off gate")
    signed = ctx.signature_record is not None and _record_hash(ctx.signature_record) == cb.sha256
    if not signed and cb.release.get("status") != "signed":
        res.status = "n/a"
        res.notes.append("not a signed build")
        return res
    res.notes.append("signed build: signature record holds this file's sha256")

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "marker" in node:
                res.fail(f"{path}: slot carries a marker {_short(node['marker'], 60)}")
            text = node.get("text")
            if isinstance(text, str) and "[wording: PI" in text:
                res.fail(f"{path}: slot text carries a '[wording: PI' marker")
            for k, v in node.items():
                if not k.endswith("_before_r4"):
                    walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for n, v in enumerate(node):
                walk(v, f"{path}/{n}")

    walk(cb.data, "")
    bad: dict[str, list[str]] = {}
    for item_id, item in cb.items.items():
        if item.get("status") != "signed":
            if cb.in_build_scope(item_id):
                bad.setdefault(str(item.get("status")), []).append(item_id)
            else:
                res.notes.append(f"(outside build scope) {item_id}: status {item.get('status')!r}")
    for status, ids in bad.items():
        res.fail(f"{len(ids)} build-scope items have status {status!r}, not 'signed' (e.g. {ids[:3]})")
    return res


def check_14_translation(cb: Codebook, ctx: Context) -> CheckResult:
    """Every item whose column exists in v2.5 (``g3o.common.schema.DATA_COLUMNS``)
    has a ``translation_v25`` map; in a map, every v2.7 code is mapped or listed
    as unmappable."""
    res = CheckResult(14, "translation")
    cols = set(ctx.v25_columns or ())
    if not cols:
        res.notes.append("no v2.5 column list supplied; only map completeness is checked")
    for item_id, item in cb.items.items():
        tr = item.get("translation_v25")
        if item.get("name") in cols and tr == "new":
            _scoped(cb, res, item_id, f"column {item.get('name')!r} exists in v2.5 but translation_v25 is 'new'")
        if isinstance(tr, dict) and isinstance(tr.get("map"), dict):
            codes = _value_codes(cb, item_id) or []
            unm = {str(u) for u in tr.get("unmappable") or []} if isinstance(tr.get("unmappable"), list) else set()
            mapped = {str(k) for k in tr["map"]}
            via = {str(k) for k in tr["via"]} if isinstance(tr.get("via"), dict) else set()
            if via:
                res.notes.append(f"{item_id}: codes {sorted(via)} translate via another item (`via`, not a template key)")
            for c in codes:
                if c not in mapped and c not in unm and c not in via:
                    _scoped(cb, res, item_id, f"code {c!r} neither mapped nor listed as unmappable")
    return res


def check_15_hash(cb: Codebook, ctx: Context) -> CheckResult:
    """The release hash is sha256 of the file bytes; every generated file records
    it in its header (first 1 KB)."""
    res = CheckResult(15, "hash")
    if cb.path is not None and cb.path.exists() and cb.sha256 != sha256_bytes(cb.path.read_bytes()):
        res.fail("release hash differs from the sha256 of the file bytes")
    for f in ctx.generated:
        if cb.sha256 not in f.content[:1024]:
            res.fail(f"{f.name}: header does not record the codebook sha256")
    if ctx.signature_record is not None:
        h = _record_hash(ctx.signature_record)
        res.notes.append(f"codebook sha256 {cb.sha256}; signature record {h}; {'match' if h == cb.sha256 else 'MISMATCH'}")
    return res


def _follows(block: str, definition: str, rules: list[str]) -> bool:
    pos = block.find(definition)
    if pos < 0:
        return False
    pos += len(definition)
    for r in rules:
        nxt = block.find(r, pos)
        if nxt < 0:
            return False
        pos = nxt + len(r)
    return True


def check_16_full_rules(cb: Codebook, ctx: Context) -> CheckResult:
    """In every generated question and prompt section, each value's definition is
    followed by the item's full rule set (own slots and expanded shared rules),
    repeated per value. Part prompts for long pages also carry the part sentence
    and the temporary answer; no part prompt is generated (see BLOCKED_TARGETS),
    so that clause is reported as a note."""
    res = CheckResult(16, "full rules beside every value")
    jev = ctx.file("jev_questions.json")
    part_sentence = cb.shared_slot("part_prompt/sentence")
    part_label = cb.shared_slot("part_prompt/temporary_answer/label")
    if jev is not None:
        doc = json.loads(jev.content)
        if part_sentence is not None and part_label is not None:
            pp = doc.get("part_prompt") or {}
            if pp.get("sentence") != part_sentence.text:
                res.fail("jev_questions.json: part prompt does not carry the part-prompt sentence (all-03 a)")
        for q in doc["questions"]:
            item_id = q["item_id"]
            rules = [r.text for r in cb.rule_texts(item_id)]
            for crit in q["criteria"]:
                d = cb.resolve_text(str(crit.get("definition_slot", "")))
                if d is None or not _follows(crit["text"], d, rules):
                    res.fail(f"jev question {item_id} value {crit['code']!r}: definition not followed by all {len(rules)} rules")
            if "computed_values" in q and not _follows(q.get("rules_text", ""), "", rules):
                res.fail(f"jev question {item_id}: computed-value question does not carry all {len(rules)} rules")
            # every offered value, and only those, is a criterion (jev_choice: false, missing choices; A6, A7)
            part = q.get("part")
            if part is not None:
                values = dict(cb.parts(item_id) or []).get(part) or []
            else:
                values = cb.value_list(item_id) or []
            want = [str(v["code"]) for v in values if v.get("jev_choice") is not False]
            want += [code for code, slots in cb.missing_choices(item_id) if slots]
            got = [str(c["code"]) for c in q["criteria"]]
            if got != want:
                res.fail(f"jev question {q.get('question_id')}: choices {got} are not the offered values {want}")
            if part_label is not None and (q.get("part_prompt_answer") or {}).get("label") != part_label.text:
                res.fail(f"jev question {q.get('question_id')}: no temporary answer {part_label.text!r} (all-03 a)")
    ext = ctx.file("extractor_prompt_sections.md")
    if ext is not None:
        for item_id in re.findall(r"<!-- item: (\S+) sha256: ", ext.content):
            start = ext.content.find(ITEM_MARKER.split("{")[0] + item_id + " ")
            end = ext.content.find("<!-- item: ", start + 1)
            section = ext.content[start: end if end > 0 else None]
            rules = [r.text for r in cb.rule_texts(item_id)]
            for n, value in enumerate(cb.value_list(item_id) or []):
                vm = VALUE_MARKER.format(code=value["code"])
                vs = section.find(vm)
                ve = section.find("<!-- value: ", vs + 1)
                block = section[vs: ve if ve > 0 else None] if vs >= 0 else ""
                d = cb.definition(item_id, n)
                if d is None or not _follows(block, d.text, rules):
                    res.fail(f"prompt section {item_id} value {value['code']!r}: definition not followed by all rules")
    if part_sentence is None or part_label is None:
        res.notes.append("part-prompt clause (all-03 a): no part prompt generated; the codebook holds no signed "
                         "part-prompt sentence (generator blocked, see manifest blocked_targets)")
    else:
        res.notes.append("part-prompt clause (all-03 a): jev_questions.json carries the part sentence, and every "
                         "question the temporary answer, from the codebook's shared slots")
    res.notes.append(f"rule list heading used as scaffolding: {RULES_HEADING!r}")
    return res


CHECKS: tuple[Callable[[Codebook, Context], CheckResult], ...] = (
    check_01_template_complete, check_02_ids_stable, check_03_verbatim, check_04_frozen,
    check_05_no_drift, check_06_linkage, check_07_gates, check_08_values,
    check_09_coder_fits, check_10_long_pages, check_11_coverage, check_12_version_steps,
    check_13_signoff_gate, check_14_translation, check_15_hash, check_16_full_rules,
)


def default_context(cb: Codebook, repo_root: Path = REPO_ROOT) -> Context:
    record = None
    rel = cb.release.get("signature_record")
    if isinstance(rel, str) and (repo_root / rel).exists():
        record = (repo_root / rel).read_text(encoding="utf-8")
    try:
        from g3o.common.schema import DATA_COLUMNS

        cols: tuple[str, ...] | None = tuple(DATA_COLUMNS)
    except Exception:  # noqa: BLE001 - the check reports the missing list
        cols = None
    return Context(generated=generate_all(cb), repo_root=repo_root, signature_record=record, v25_columns=cols)


def run_checks(cb: Codebook, ctx: Context | None = None) -> list[CheckResult]:
    ctx = ctx or default_context(cb)
    return [check(cb, ctx) for check in CHECKS]
