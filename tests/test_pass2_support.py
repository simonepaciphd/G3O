"""T-032 self-checks: the v2.7 pass-2 supporting-text call.

Multi-activity and chunked synthetic pages; all extractor calls mocked.
"""

from __future__ import annotations

import ast
import inspect
import json

import pytest

from g3o.codebook.loader import load_codebook
from g3o.common.page_chunks import chunk_page
from g3o.extract import pass2_support as p2
from g3o.extract.anthropic_client import ExtractorResult
from g3o.extract.parser_v27 import ExtractContractError
from g3o.extract.pass2_support import (
    ActivityCode,
    Pass2Activity,
    Pass2Page,
    build_jobs,
    build_system_prompt,
    build_user_message,
    marked_part_text,
    output_schema,
    parse_pass2_result,
    select_requests,
)
from g3o.extract.request_v27 import Pass1Page

TEXT = (
    "Town of Example. The council launched the CivicBot chatbot for residents in March 2024. "
    "CivicBot answered 12,000 questions in its first month and cut waiting times by half. "
    "Separately, the council adopted a policy on staff use of generative AI tools."
)
A1 = (TEXT.index("The council launched"), TEXT.index(" Separately"))
A2 = (TEXT.index("Separately"), len(TEXT))


def base_page(text=TEXT, limit=None, page_id="P1") -> Pass1Page:
    chunks = tuple(chunk_page(page_id, text, limit_tokens=limit) if limit else chunk_page(page_id, text))
    return Pass1Page(
        page_id=page_id, institution_id="inst-1", institution_name="Town of Example",
        url=f"https://example.gov/{page_id}", title="CivicBot", text=text, chunks=chunks,
        codes=(), verdict="confirms_activity", page_complete=None,
    )


def two_activity_page(extra1=(), extra2=()) -> Pass2Page:
    part = "P1#p001"
    a1 = Pass2Activity("P1#a001", *A1, codes=(
        ActivityCode("core.activity_type", part, "public_facing_service"),
        ActivityCode("core.function_drafting_writing", part, "no"),
        ActivityCode("core.adoption_stage", part, "production"),
        ActivityCode("core.procurement_status", part, "not_documented"),
        ActivityCode("core.outcome_kind", part, "quantified"),
        ActivityCode("core.incident_kind", part, "none_reported"),
        *extra1,
    ))
    a2 = Pass2Activity("P1#a002", *A2, codes=(
        ActivityCode("core.action_type", part, "governance"),
        ActivityCode("core.model_origin", part, "not_asked"),
        ActivityCode("core.governance_form", part, "dedicated_genai_or_ai_policy_or_guideline"),
        ActivityCode("core.outcome_kind", part, "unknown"),
        *extra2,
    ))
    return Pass2Page(base_page(), (a1, a2))


def ok(payload: dict, cid="x27s-test") -> ExtractorResult:
    return ExtractorResult(cid, True, json.dumps(payload), None, response_model="claude-haiku-5-5")


# ---------------------------------------------------------------------------
# Codebook-derived rules
# ---------------------------------------------------------------------------


def test_rules_follow_codebook_pass_and_gate():
    rules = p2.default_rules()
    items = load_codebook().build_items()
    expected = {k for k, v in items.items() if v["pass"] == 2 and v["coder"] == "classifier"
                and v["support_required"] is True}
    assert set(rules.support_items) == expected and "core.outcome_kind" in expected
    assert rules.gated_fields == {
        "core.reported_outcomes": ("core.outcome_kind", frozenset({"quantified", "qualitative"})),
        "core.reported_incidents": ("core.incident_kind",
                                    frozenset({"quantified", "qualitative",
                                               "discontinuation_uncertain"})),
    }
    assert {"no", "unknown", "not_documented", "not_asked", "_NA_"} <= rules.no_support_values


# ---------------------------------------------------------------------------
# Request selection
# ---------------------------------------------------------------------------


def test_multi_activity_page_gets_one_plan_with_quotes_per_activity_code():
    plan = select_requests(two_activity_page())
    rules = p2.default_rules()
    # none_reported needs a quote under r12 and none once RC-D-019 (r13) lands (PI "D1b");
    # the expectation follows whichever codebook is installed.
    assert [(t.label, t.item_id, t.answer) for t in plan.quote_tasks] == [x for x in [
        ("A1", "core.activity_type", "public_facing_service"),
        ("A1", "core.adoption_stage", "production"),
        ("A1", "core.outcome_kind", "quantified"),
        ("A1", "core.incident_kind", "none_reported"),
        ("A2", "core.action_type", "governance"),
        ("A2", "core.governance_form", "dedicated_genai_or_ai_policy_or_guideline"),
    ] if rules.needs_quote(x[2])]
    assert len({t.task_id for t in plan.quote_tasks}) == len(plan.quote_tasks)


def test_negative_missing_and_not_asked_values_need_no_quote():
    plan = select_requests(two_activity_page())
    asked = {(t.activity_id, t.item_id) for t in plan.quote_tasks}
    for item in ("core.function_drafting_writing", "core.procurement_status"):
        assert ("P1#a001", item) not in asked
    assert ("P1#a002", "core.model_origin") not in asked
    assert ("P1#a002", "core.outcome_kind") not in asked


def test_gated_fields_only_when_cx61_gate_is_open():
    plan = select_requests(two_activity_page())
    assert [(t.label, t.item_id, t.chunk_ids) for t in plan.field_tasks] == [
        ("A1", "core.reported_outcomes", ("P1#p001",))]
    plan = select_requests(two_activity_page(
        extra2=(ActivityCode("core.incident_kind", "P1#p001", "discontinuation_uncertain"),)))
    assert [(t.label, t.item_id) for t in plan.field_tasks] == [
        ("A1", "core.reported_outcomes"), ("A2", "core.reported_incidents")]


def test_multi_select_gives_one_task_per_selected_value():
    plan = select_requests(two_activity_page(extra2=(
        ActivityCode("core.governance_form", "P1#p001", "approved_tool_list_or_endorsement"),
        ActivityCode("core.governance_form", "P1#p001", "approved_tool_list_or_endorsement"),
    )))
    forms = [t.answer for t in plan.quote_tasks if t.item_id == "core.governance_form"]
    assert forms == ["dedicated_genai_or_ai_policy_or_guideline",
                     "approved_tool_list_or_endorsement"]


def test_page_with_nothing_to_support_needs_no_request():
    page = Pass2Page(base_page(), (Pass2Activity("P1#a001", *A1, codes=(
        ActivityCode("core.function_code", "P1#p001", "no"),
        ActivityCode("core.outcome_kind", "P1#p001", "none_reported"),
    )),))
    plan = select_requests(page)
    expected = ["none_reported"] if p2.default_rules().needs_quote("none_reported") else []
    assert [t.answer for t in plan.quote_tasks] == expected
    page = Pass2Page(base_page(), (Pass2Activity("P1#a001", *A1, codes=(
        ActivityCode("core.function_code", "P1#p001", "no"),)),))
    assert not select_requests(page).needs_request
    jobs, plans = build_jobs([page])
    assert jobs == [] and not plans["P1"].needs_request


def test_unknown_item_value_or_span_fails_closed():
    with pytest.raises(ValueError, match="not a pass-2 item"):
        select_requests(two_activity_page(extra1=(ActivityCode("core.page_verdict", "P1#p001",
                                                               "confirms_activity"),)))
    with pytest.raises(ValueError, match="not in the codebook"):
        select_requests(two_activity_page(extra1=(ActivityCode("core.activity_type", "P1#p001",
                                                               "chatbot"),)))
    with pytest.raises(ValueError, match="not on the page"):
        Pass2Page(base_page(), (Pass2Activity("a", 5, 10_000, ()),))
    with pytest.raises(ValueError, match="unknown part"):
        Pass2Page(base_page(), (Pass2Activity("a", 0, 5, (ActivityCode(
            "core.activity_type", "P1#p009", "pilot_experiment"),)),))


# ---------------------------------------------------------------------------
# Chunked pages: part provenance and span marks
# ---------------------------------------------------------------------------

LONG = ("Alpha sentence about the council and its GenAI chatbot pilot. " * 30) + "\n\n" + (
    "Beta sentence on the GenAI policy for staff and its rules. " * 30)


def chunked_page() -> Pass2Page:
    bp = base_page(text=LONG, limit=150)
    assert len(bp.chunks) >= 2
    c1, c2 = bp.chunks[0], bp.chunks[1]
    span = (c1.end - 40, c2.start + 40)  # one activity crossing the part boundary
    act = Pass2Activity("P1#a001", *span, codes=(
        ActivityCode("core.activity_type", c1.chunk_id, "pilot_experiment"),
        ActivityCode("core.activity_type", c2.chunk_id, "pilot_experiment"),
        ActivityCode("core.outcome_kind", c2.chunk_id, "qualitative"),
    ))
    return Pass2Page(bp, (act,))


def test_quote_tasks_name_the_part_that_produced_each_code():
    page = chunked_page()
    plan = select_requests(page)
    c1, c2 = (c.chunk_id for c in page.page.chunks[:2])
    assert [(t.item_id, t.chunk_id) for t in plan.quote_tasks] == [
        ("core.activity_type", c1), ("core.activity_type", c2), ("core.outcome_kind", c2)]
    assert plan.field_tasks[0].chunk_ids == (c2,)


def test_span_marks_follow_full_page_offsets_across_parts():
    page = chunked_page()
    plan = select_requests(page)
    c1, c2 = page.page.chunks[:2]
    m1, m2 = marked_part_text(page, plan, c1.chunk_id), marked_part_text(page, plan, c2.chunk_id)
    act = page.activities[0]
    assert "[[A1]]" in m1 and "[[/A1]]" not in m1
    assert "[[/A1]]" in m2 and "[[A1]]" not in m2
    assert m1.replace("[[A1]]", "") == c1.text and m2.replace("[[/A1]]", "") == c2.text
    assert m1.index("[[A1]]") == act.start - c1.start
    assert m2.index("[[/A1]]") == act.end - c2.start


def test_overlapping_spans_both_marked():
    bp = base_page()
    page = Pass2Page(bp, (
        Pass2Activity("x", 0, len(TEXT), ()), Pass2Activity("y", *A2, ()),
    ))
    plan = select_requests(page)
    m = marked_part_text(page, plan, "P1#p001")
    assert m.startswith("[[A1]]") and m.endswith(("[[/A1]][[/A2]]", "[[/A2]][[/A1]]"))
    assert m.count("[[A2]]") == 1


def test_parser_quotes_carry_part_ids_and_reject_other_parts():
    page = chunked_page()
    plan = select_requests(page)
    c1, c2 = (c.chunk_id for c in page.page.chunks[:2])
    out = parse_pass2_result(ok({"quotes": [
        {"task_id": "q001", "part_id": c1, "quote": "Alpha sentence about the council"},
        {"task_id": "q002", "part_id": c1, "quote": "Alpha sentence"},  # code came from c2
    ], "fields": []}), page, plan)
    assert [(q.task_id, q.chunk_id, q.status) for q in out.quotes] == [
        ("q001", c1, "quoted"), ("q002", c2, "wrong_part"), ("q003", c2, "no_entry")]
    assert [r.reason for r in out.rejected] == ["wrong_part"]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_fields_need_supporting_text_from_gate_parts():
    page = two_activity_page(
        extra2=(ActivityCode("core.incident_kind", "P1#p001", "qualitative"),))
    plan = select_requests(page)
    out = parse_pass2_result(ok({"quotes": [], "fields": [
        {"task_id": "f001", "value": "cut waiting times by half", "part_id": "P1#p001",
         "supporting_text": "CivicBot answered 12,000 questions in its first month and cut "
                            "waiting times by half."},
        {"task_id": "f002", "value": "a complaint", "part_id": "P1#p001", "supporting_text": None},
    ]}), page, plan)
    f1, f2 = out.fields
    assert (f1.status, f1.item_id, f1.activity_id) == ("stated", "core.reported_outcomes", "P1#a001")
    assert f1.chunk_id == "P1#p001" and f1.supporting_text.startswith("CivicBot answered")
    assert (f2.status, f2.value) == ("no_supporting_text", None)
    out = parse_pass2_result(ok({"quotes": [], "fields": [
        {"task_id": "f001", "value": None, "part_id": None, "supporting_text": None}]}), page, plan)
    assert [f.status for f in out.fields] == ["not_stated", "no_entry"]


def test_marks_removed_from_quotes_and_flagged():
    page = two_activity_page()
    plan = select_requests(page)
    out = parse_pass2_result(ok({"quotes": [
        {"task_id": "q001", "part_id": "P1#p001", "quote": "[[A1]]The council launched the CivicBot"},
        {"task_id": "q002", "part_id": "P1#p001", "quote": "[[/A1]]"},
    ], "fields": []}), page, plan)
    q1, q2 = out.quotes[:2]
    assert q1.quote == "The council launched the CivicBot" and p2.MARKS_REMOVED_FLAG in q1.flags
    assert (q2.quote, q2.status) == (None, "empty")


def test_over_cap_quote_kept_whole_and_flagged():
    page = two_activity_page()
    plan = select_requests(page)
    long_quote = TEXT[:250]
    out = parse_pass2_result(ok({"quotes": [
        {"task_id": "q001", "part_id": "P1#p001", "quote": long_quote}], "fields": []}), page, plan)
    assert out.quotes[0].quote == long_quote and "quote_over_cap" in out.quotes[0].flags


def test_answer_shown_but_never_parsed_back():
    """C-001: the task carries the answer as input; the output schema has no code field and
    a code-like key in the answer is a contract error."""
    page = two_activity_page()
    plan = select_requests(page)
    user = build_user_message(page, plan)
    tasks = json.loads(user.split("TASKS:\n", 1)[1])
    assert tasks["quote_tasks"][0]["answer"] == "public_facing_service"
    for raw in ({"task_id": "q001", "part_id": "P1#p001", "quote": "x",
                 "answer": "public_facing_service"},
                {"task_id": "q001", "part_id": "P1#p001", "quote": "x",
                 "activity_type": "public_facing_service"}):
        with pytest.raises(ExtractContractError):
            parse_pass2_result(ok({"quotes": [raw], "fields": []}), page, plan)
    with pytest.raises(ExtractContractError):
        parse_pass2_result(ok({"quotes": [], "fields": [], "activity_type": "x"}), page, plan)
    out = parse_pass2_result(ok({"quotes": [
        {"task_id": "q001", "part_id": "P1#p001", "quote": "The council launched"}],
        "fields": []}), page, plan)
    assert not any("public_facing_service" in repr(q) for q in out.quotes)


def _schema_keys(schema, acc):
    if isinstance(schema, dict):
        acc |= set(schema.get("properties", {}))
        for v in schema.values():
            _schema_keys(v, acc)
    elif isinstance(schema, list):
        for v in schema:
            _schema_keys(v, acc)
    return acc


def test_output_schema_has_no_code_field():
    keys = _schema_keys(output_schema(), set())
    assert not keys & {"code", "answer", "chosen_value", "verdict"}
    classifier = {v["name"] for v in load_codebook().build_items().values()
                  if v["coder"] == "classifier"}
    assert not keys & classifier


def test_parser_reads_no_code_values():
    """Grep check: the parser never reads item values, answers or the codebook."""
    tree = ast.parse(inspect.getsource(parse_pass2_result))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for banned in ("answer", "support_items", "value_list", "load_codebook", "codes",
                   "no_support_values", "questions"):
        assert banned not in names


def test_parser_refuses_failed_result_and_non_json():
    page = two_activity_page()
    plan = select_requests(page)
    with pytest.raises(RuntimeError):
        parse_pass2_result(ExtractorResult("x", False, None, {"type": "errored"}), page, plan)
    with pytest.raises(ExtractContractError):
        parse_pass2_result(ExtractorResult("x", True, "not json", None), page, plan)


# ---------------------------------------------------------------------------
# Prompt and jobs
# ---------------------------------------------------------------------------


def test_system_prompt_shared_text_cap_and_generated_field_sections():
    cb = load_codebook()
    system = build_system_prompt(cb)
    assert system.startswith(cb.shared_slot("system_prompt").text)
    assert "at most 200 characters" in system
    assert "## `core.reported_outcomes`" in system and "## `core.reported_incidents`" in system
    assert "{{" not in system


def test_one_job_per_page_covering_all_activities():
    pages = [two_activity_page(), chunked_page()]
    jobs, plans = build_jobs(pages)
    assert len(jobs) == 2
    job = jobs[0]
    assert job.custom_id.startswith("x27s-") and job.metadata["page_id"] == "P1"
    assert job.params["model"] == "claude-haiku-5-5"
    assert job.params["output_config"]["effort"] == "medium"
    user = job.params["messages"][0]["content"]
    assert "ACTIVITIES: A1, A2" in user and "[[A2]]Separately" in user
    questions = json.loads(user.split("QUESTIONS:\n", 1)[1].split("\n\nTASKS:", 1)[0])
    expected = {"activity_type", "adoption_stage", "outcome_kind", "action_type", "governance_form"}
    if p2.default_rules().needs_quote("none_reported"):
        expected.add("incident_kind")
    assert set(questions) == expected


# ---------------------------------------------------------------------------
# PI 2026-11-05 "D1b": exemptions come from the codebook only
# ---------------------------------------------------------------------------

D1B_VALUES = ("none_reported", "none_documented", "none", "unclear", "unresolved",
              "not_an_activity")


def synthetic_codebook(extra_exempt=D1B_VALUES):
    """The installed codebook, parsed afresh, with values added to
    ``support_status.status_by_answer`` (in memory only; the file is untouched)."""
    cb = load_codebook()
    sba = cb.data["vocabularies"]["support_status"]["status_by_answer"]
    for v in extra_exempt:
        sba[v] = "not_required"
    return cb


def test_value_added_to_status_by_answer_gets_no_quote_task():
    rules = p2.rules_from_codebook(synthetic_codebook())
    assert set(D1B_VALUES) <= rules.no_support_values
    part = "P1#p001"
    page = Pass2Page(base_page(), (
        Pass2Activity("P1#a001", *A1, codes=(
            ActivityCode("core.outcome_kind", part, "none_reported"),
            ActivityCode("core.incident_kind", part, "none_reported"),
            ActivityCode("core.procurement_status", part, "none_documented"),
            ActivityCode("core.deployment_scale_unit", part, "none"),
            ActivityCode("core.has_human_oversight", part, "unclear"),
            ActivityCode("core.evaluation_documented", part, "unclear"),
            ActivityCode("core.activity_segment", part, "unresolved"),
            ActivityCode("core.adoption_stage", part, "pilot"),
        )),
        Pass2Activity("P1#a002", *A2, codes=(
            ActivityCode("core.activity_segment", part, "not_an_activity"),)),
    ))
    plan = select_requests(page, rules)
    assert [(t.item_id, t.answer) for t in plan.quote_tasks] == [("core.adoption_stage", "pilot")]
    assert plan.field_tasks == ()  # none_reported never opens the CX-61 gate
    # Pass 1 reads the same codebook key (request_v27.rules_from_codebook).
    from g3o.extract import request_v27
    assert set(D1B_VALUES) <= request_v27.rules_from_codebook(synthetic_codebook()).no_support_values


def test_exemptions_are_not_hard_coded_in_the_selection_modules():
    for mod in (p2, __import__("g3o.extract.request_v27", fromlist=["x"])):
        tree = ast.parse(inspect.getsource(mod))
        literals = {n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        # "none" is excluded: request_v27 compares the codebook gate token ``gate == "none"``,
        # which is not an answer exemption.
        assert not literals & (set(D1B_VALUES) - {"none"}), mod.__name__


# ---------------------------------------------------------------------------
# PI 2026-11-05 "D2c": builder-side question slot for core.activity_segment
# ---------------------------------------------------------------------------


def test_activity_segment_quote_task_shows_override_not_method_note():
    cb = load_codebook()
    note = cb.instruction("core.activity_segment").text
    rules = p2.default_rules()
    assert rules.questions["core.activity_segment"] == p2.QUESTION_OVERRIDES["core.activity_segment"]
    assert rules.questions["core.activity_segment"] != note
    assert rules.overridden == {"core.activity_segment"}
    # every other question is the signed instruction
    for k, q in rules.questions.items():
        if k != "core.activity_segment":
            assert q == cb.instruction(k).text
    page = Pass2Page(base_page(), (Pass2Activity("P1#a001", *A1, codes=(
        ActivityCode("core.activity_segment", "P1#p001", "component_of_program"),)),))
    plan = select_requests(page)
    job = p2.build_job(page, plan, system="s")
    user = job.params["messages"][0]["content"]
    questions = json.loads(user.split("QUESTIONS:\n", 1)[1].split("\n\nTASKS:", 1)[0])
    assert questions == {"activity_segment": p2.QUESTION_OVERRIDES["core.activity_segment"]}
    assert note not in user
    assert job.metadata["question_overrides"] == ["core.activity_segment"]
    assert job.metadata["prompt_version"] == "pass2_support_v27-draft-2"


def test_override_does_not_edit_the_codebook_and_unknown_override_fails():
    cb = load_codebook()
    before = cb.sha256
    p2.rules_from_codebook(cb)
    assert cb.sha256 == before == load_codebook().sha256
    plain = p2.rules_from_codebook(cb, overrides={})
    assert plain.questions["core.activity_segment"] == cb.instruction("core.activity_segment").text
    assert plain.overridden == frozenset()
    with pytest.raises(ValueError, match="not pass-2 quote items"):
        p2.rules_from_codebook(cb, overrides={"core.page_verdict": "x"})
