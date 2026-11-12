"""T-022 self-checks: v2.7 pass-1 extraction request selection, client, parser.

All API calls are mocked; no network.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from g3o.codebook.loader import load_codebook
from g3o.common.page_chunks import chunk_page
from g3o.extract import anthropic_client as ac
from g3o.extract import parser_v27, request_v27
from g3o.extract.anthropic_client import (
    AnthropicExtractorClient,
    ExtractorJob,
    ExtractorResult,
    make_custom_id,
    split_for_batches,
)
from g3o.extract.parser_v27 import ExtractContractError, parse_pass1_result
from g3o.extract.request_v27 import (
    DEFERRED_FIELDS,
    R003_VERDICTS,
    PageCode,
    Pass1Page,
    build_job,
    build_jobs,
    build_system_prompt,
    build_user_message,
    default_rules,
    output_schema,
    select_requests,
)

TEXT = (
    "Town of Example. The council launched the CivicBot chatbot, built on GPT-4o, "
    "for residents in March 2024. It answered 12,000 questions in its first month.\n\n"
    "Read more about CivicBot on the project page. Published 3 April 2024."
)


def make_page(*, page_id="P1", verdict="confirms_activity", codes=(), page_complete=None, links=None,
              chrome=None, text=TEXT, limit=None, has_date=False) -> Pass1Page:
    chunks = tuple(chunk_page(page_id, text, limit_tokens=limit) if limit else chunk_page(page_id, text))
    return Pass1Page(
        page_id=page_id, institution_id="inst-1", institution_name="Town of Example",
        url="https://example.gov/civicbot", title="CivicBot", text=text, chunks=chunks,
        codes=tuple(codes), verdict=verdict, page_complete=page_complete,
        chrome_text=chrome, links=links, has_metadata_date=has_date,
    )


def ok(payload: dict, cid="x27-test") -> ExtractorResult:
    return ExtractorResult(cid, True, json.dumps(payload), None, response_model="claude-haiku-5-5")


def empty_answer(**kw) -> dict:
    base = {"quotes": [], "links": [], "activities": [], "publication_date": None}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Codebook-derived rules
# ---------------------------------------------------------------------------


def test_r003_verdicts_match_codebook_gate():
    cb = load_codebook()
    gate = cb.items["core.page_complete"]["gate"]["values"]
    assert tuple(gate) == R003_VERDICTS


def test_pass1_fields_follow_codebook_coder_column():
    rules = default_rules()
    assert rules.activity_fields == (
        "core.activity_name", "core.observed_actor_name", "core.tool_name",
        "core.model_name", "core.contracting_party", "core.deployment_scale_number",
    )
    cb = load_codebook()
    quote_step_activity = {k for k, v in cb.build_items().items()
                           if v["coder"] == "quote_step" and "activity" in v["level"]}
    assert quote_step_activity - set(rules.activity_fields) == set(DEFERRED_FIELDS)
    # r2#28: scope_notes gone, vendor split (contracting party here; developer is derived)
    assert "core.scope_notes" not in cb.items and "core.vendor" not in cb.items


def test_no_support_values_from_codebook():
    rules = default_rules()
    assert rules.no_support_values == {"no", "unknown", "not_documented", "not_asked", "_NA_", "none_reported",
                                       "none_documented", "none", "unclear", "unresolved", "not_an_activity"}
    assert rules.negative_verdicts == {"confirms_absence", "no_genai", "background_only",
                                       "event_only", "other_body"}


# ---------------------------------------------------------------------------
# Request selection (card self-checks)
# ---------------------------------------------------------------------------


def test_background_only_page_with_positive_cx_code_gets_quote_request():
    page = make_page(verdict="background_only", codes=[
        PageCode("core.page_verdict", "P1#p001", "background_only"),
        PageCode("core.disclosure_form", "P1#p001", "register_single_institution"),
    ])
    plan = select_requests(page)
    assert plan.needs_request
    assert [t.item_id for t in plan.quote_tasks] == ["core.disclosure_form"]
    assert not plan.activity_task and not plan.link_task


def test_incomplete_no_genai_page_gets_links_request():
    links = ({"url": "https://example.gov/more", "anchor_text": "More", "context": "Read more"},)
    page = make_page(verdict="no_genai", page_complete="yes", links=links,
                     codes=[PageCode("core.page_verdict", "P1#p001", "no_genai")])
    plan = select_requests(page)
    assert plan.link_task and plan.needs_request
    assert [ln.link_id for ln in plan.links] == ["L001"]
    assert plan.quote_tasks == () and not plan.activity_task


@pytest.mark.parametrize("verdict", [
    "confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only",
    "background_only", "confirms_absence", "no_genai", "not_assessable",
])
def test_spans_only_for_r003_verdicts(verdict):
    plan = select_requests(make_page(verdict=verdict,
                                     codes=[PageCode("core.source_type", "P1#p001", "vendor")]))
    assert plan.activity_task is (verdict in R003_VERDICTS)
    assert bool(plan.activity_fields) is (verdict in R003_VERDICTS)


def test_negative_and_missing_values_need_no_quote():
    page = make_page(verdict="no_genai", codes=[
        PageCode("core.page_verdict", "P1#p001", "no_genai"),
        PageCode("core.disclosure_form", "P1#p001", "unknown"),
        PageCode("core.source_type", "P1#p001", "not_documented"),
    ])
    plan = select_requests(page)
    assert not plan.needs_request
    with pytest.raises(ValueError):
        build_job(page, plan, system="s")


def test_positive_verdict_and_yes_answers_get_quotes_per_part():
    text = ("Alpha sentence about the council. " * 40) + "\n\n" + ("Beta sentence on GenAI. " * 40)
    page = make_page(text=text, limit=150, verdict="confirms_activity", page_complete="no", codes=[
        PageCode("core.page_verdict", "P1#p001", "confirms_activity"),
        PageCode("core.page_verdict", "P1#p002", "confirms_activity"),
        PageCode("core.content_data", "P1#p002", "yes"),
        PageCode("core.content_data", "P1#p001", "no"),
        PageCode("core.page_complete", "P1#p001", "no"),
    ])
    assert len(page.chunks) >= 2
    plan = select_requests(page)
    assert [(t.item_id, t.chunk_id) for t in plan.quote_tasks] == [
        ("core.page_verdict", "P1#p001"), ("core.page_verdict", "P1#p002"),
        ("core.content_data", "P1#p002"),
    ]
    assert not plan.link_task


def test_quote_task_shows_the_chosen_answer():
    """RC-D-017 (PI 2026-11-04): the quote task shows jev's chosen answer (input only)."""
    page = make_page(verdict="background_only", codes=[
        PageCode("core.disclosure_form", "P1#p001", "register_single_institution")])
    plan = select_requests(page)
    (task,) = plan.quote_tasks
    assert task.answer == "register_single_institution"
    assert task.question == load_codebook().instruction("core.disclosure_form").text
    tasks = json.loads(build_user_message(page, plan).split("TASKS:\n", 1)[1])
    assert tasks["quote_tasks"][0]["answer"] == "register_single_institution"
    assert tasks["quote_tasks"][0]["part_id"] == "P1#p001"


def test_shown_answer_never_comes_back_as_a_code():
    """C-001 still holds with the answer shown: a code-like key in the output is refused."""
    page = make_page(verdict="background_only", codes=[
        PageCode("core.disclosure_form", "P1#p001", "register_single_institution")])
    plan = select_requests(page)
    for raw in ({"task_id": "q001", "part_id": "P1#p001", "quote": "x",
                 "answer": "register_single_institution"},
                {"task_id": "q001", "part_id": "P1#p001", "quote": "x",
                 "disclosure_form": "register_single_institution"}):
        with pytest.raises(ExtractContractError):
            parse_pass1_result(ok(empty_answer(quotes=[raw])), page, plan)
    out = parse_pass1_result(ok(empty_answer(quotes=[
        {"task_id": "q001", "part_id": "P1#p001", "quote": "The council launched"}])), page, plan)
    assert not any("register_single_institution" in repr(v) for v in out.quotes)


def test_quote_cap_in_prompt_and_over_cap_flagged_not_truncated():
    assert request_v27.QUOTE_MAX_CHARS == 200
    system = build_system_prompt()
    assert "at most 200 characters" in system
    page = _activity_page()
    plan = select_requests(page)
    long_quote = "The council launched the CivicBot chatbot " * 6  # > 200 chars
    assert len(long_quote) > 200
    out = parse_pass1_result(ok(empty_answer(
        quotes=[{"task_id": "q001", "part_id": "P1#p001", "quote": long_quote},
                {"task_id": "q002", "part_id": "P1#p001", "quote": "Read more"}],
        links=[{"link_id": "L001", "part_id": "P1#p001", "quote": long_quote}],
        activities=[{"part_id": "P1#p001", "start_text": "The council", "end_text": "first month.",
                     "fields": [{"field": "activity_name", "value": "CivicBot", "part_id": "P1#p001",
                                 "supporting_text": long_quote}]}],
    )), page, plan)
    q1, q2 = out.quotes
    assert q1.quote == long_quote and q1.flags == (parser_v27.OVER_CAP_FLAG,)
    assert q2.flags == ()
    assert out.links[0].quote == long_quote and out.links[0].flags == ("quote_over_cap",)
    f = out.activities[0].fields[0]
    assert f.supporting_text == long_quote and f.flags == ("quote_over_cap",)


def test_incomplete_page_without_stored_links_records_why():
    base = dict(verdict="confirms_activity", page_complete="yes",
                codes=[PageCode("core.page_verdict", "P1#p001", "confirms_activity")])
    assert select_requests(make_page(links=None, **base)).link_status == "not_measured"
    assert select_requests(make_page(links=(), **base)).link_status == "no_stored_links"


def test_chrome_allowed_only_for_main_plus_chrome_items():
    page = make_page(verdict="confirms_activity", chrome="Contact: ai@example.gov", codes=[
        PageCode("core.content_contact_details", "P1#p001", "yes"),
        PageCode("core.content_data", "P1#p001", "yes"),
    ])
    tasks = {t.item_id: t for t in select_requests(page).quote_tasks}
    assert tasks["core.content_contact_details"].allow_chrome
    assert not tasks["core.content_data"].allow_chrome


def test_date_task_only_without_metadata_date_and_only_on_requested_pages():
    codes = [PageCode("core.source_type", "P1#p001", "vendor")]
    assert select_requests(make_page(codes=codes)).date_task
    assert not select_requests(make_page(codes=codes, has_date=True)).date_task
    assert not select_requests(make_page(verdict="no_genai")).date_task


def test_unknown_item_or_value_is_skipped_and_recorded():
    # Lane B F6: one bad code leaves out that code only, with its reason; the page goes on.
    good = PageCode("core.page_verdict", "P1#p001", "confirms_activity")
    plan = select_requests(make_page(codes=[
        PageCode("core.activity_type", "P1#p001", "pilot_experiment"),
        PageCode("core.disclosure_form", "P1#p001", "made_up"),
        good,
    ]))
    assert [(c.item_id, c.value, c.reason) for c in plan.skipped_codes] == [
        ("core.activity_type", "pilot_experiment", "not_a_support_item"),
        ("core.disclosure_form", "made_up", "value_not_in_codebook"),
    ]
    assert [(t.item_id, t.answer) for t in plan.quote_tasks] == [("core.page_verdict",
                                                                 "confirms_activity")]
    # An unknown page verdict still refuses the page; build_jobs can collect it instead.
    with pytest.raises(ValueError):
        select_requests(make_page(verdict="made_up"))
    bad = make_page(page_id="P2", verdict="made_up")
    with pytest.raises(ValueError):
        build_jobs([bad])
    errors: dict[str, str] = {}
    jobs, plans = build_jobs([make_page(codes=[good]), bad], errors=errors)
    assert set(plans) == {"P1"} and len(jobs) == 1 and "made_up" in errors["P2"]


def test_no_head_tail_truncation_on_v27_path():
    long_text = "Words about the GenAI pilot. " * 5000  # ~145k chars, over the v2.5 60k cap
    page = make_page(text=long_text, codes=[PageCode("core.source_type", "P1#p001", "vendor")])
    plan = select_requests(page)
    job = build_job(page, plan, system="s", schema=output_schema())
    user = job.params["messages"][0]["content"]
    assert "".join(c.text for c in page.chunks) in user.replace(
        "</part>\n<part id=\"P1#p002\">\n", "")  or all(c.text in user for c in page.chunks)
    assert "omitted to fit" not in user
    src = Path(request_v27.__file__).read_text(encoding="utf-8")
    assert "cap_page_text" not in src


# ---------------------------------------------------------------------------
# Prompt and request
# ---------------------------------------------------------------------------


def test_system_prompt_carries_generated_sections_and_shared_prompt():
    cb = load_codebook()
    system = build_system_prompt(cb)
    assert system.startswith(cb.shared_slot("system_prompt").text)
    for item in default_rules().activity_fields:
        assert f"<!-- item: {item} sha256: {cb.item_hash(item)} -->" in system
    assert "{{" not in system
    for item in DEFERRED_FIELDS:
        assert f"## `{item}`" not in system


def test_job_params_haiku_medium_effort_structured_output():
    page = make_page(codes=[PageCode("core.source_type", "P1#p001", "vendor")])
    job = build_job(page, select_requests(page), system="s")
    p = job.params
    assert p["model"] == "claude-haiku-5-5"
    assert p["output_config"]["effort"] == "medium"
    assert p["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in p and "temperature" not in p
    assert job.custom_id == make_custom_id("inst-1", "https://example.gov/civicbot")


def _schema_keys(node, out):
    if isinstance(node, dict):
        out.update(node.get("properties", {}).keys())
        for v in node.values():
            _schema_keys(v, out)
    elif isinstance(node, list):
        for v in node:
            _schema_keys(v, out)
    return out


def test_output_schema_has_no_code_field():
    keys = _schema_keys(output_schema(), set())
    forbidden = {"code", "value_code", "chosen_value", "verdict", "page_verdict", "answer"}
    assert not keys & forbidden
    cb = load_codebook()
    classifier_names = {v["name"] for v in cb.build_items().values() if v["coder"] == "classifier"}
    assert not keys & classifier_names


def test_parser_reads_no_code_values():
    """Grep check: the parser never touches item value lists or enums."""
    src = Path(parser_v27.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for banned in ("ITEM_ENUMS", "value_list", "chosen_value", "codes", "load_codebook"):
        assert banned not in names
    assert "g3o.codebook.generated" not in src


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _activity_page():
    links = ({"url": "https://example.gov/civicbot/project", "anchor_text": "project page",
              "context": "Read more about CivicBot on the project page."},)
    return make_page(verdict="confirms_activity", page_complete="yes", links=links, codes=[
        PageCode("core.page_verdict", "P1#p001", "confirms_activity"),
        PageCode("core.page_complete", "P1#p001", "yes"),
    ])


def test_parser_quotes_carry_chunk_ids_and_every_task_is_answered():
    page = _activity_page()
    plan = select_requests(page)
    answer = empty_answer(quotes=[
        {"task_id": "q001", "part_id": "P1#p001", "quote": "The council launched the CivicBot chatbot"},
    ])
    out = parse_pass1_result(ok(answer), page, plan)
    assert [(q.task_id, q.chunk_id, q.status) for q in out.quotes] == [
        ("q001", "P1#p001", "quoted"), ("q002", "P1#p001", "no_entry")]
    assert all(q.chunk_id for q in out.quotes)


def test_parser_rejects_quote_from_other_part():
    text = ("Alpha sentence about the council. " * 40) + "\n\n" + ("Beta sentence on GenAI. " * 40)
    page = make_page(text=text, limit=150, codes=[PageCode("core.source_type", "P1#p002", "vendor")])
    plan = select_requests(page)
    out = parse_pass1_result(ok(empty_answer(quotes=[
        {"task_id": "q001", "part_id": "P1#p001", "quote": "Alpha sentence"}])), page, plan)
    assert out.quotes[0].status == "wrong_part" and out.quotes[0].quote is None
    assert out.quotes[0].chunk_id == "P1#p002"
    assert out.rejected[0].reason == "wrong_part"


def test_parser_links_come_from_stored_list_only():
    page = _activity_page()
    plan = select_requests(page)
    out = parse_pass1_result(ok(empty_answer(links=[
        {"link_id": "L001", "part_id": "P1#p001", "quote": "Read more about CivicBot on the project page."},
        {"link_id": "L999", "part_id": "P1#p001", "quote": "x"},
        {"link_id": "L001", "part_id": "P1#p001", "quote": "dup"},
    ])), page, plan)
    assert [(ln.link_id, ln.url, ln.chunk_id) for ln in out.links] == [
        ("L001", "https://example.gov/civicbot/project", "P1#p001")]
    assert {r.reason for r in out.rejected} == {"unknown_link_id", "duplicate_link"}


def test_parser_spans_full_page_offsets_and_field_support():
    page = _activity_page()
    plan = select_requests(page)
    out = parse_pass1_result(ok(empty_answer(activities=[{
        "part_id": "P1#p001",
        "start_text": "The council launched the CivicBot",
        "end_text": "in its first month.",
        "fields": [
            {"field": "activity_name", "value": "CivicBot", "part_id": "P1#p001",
             "supporting_text": "The council launched the CivicBot chatbot"},
            {"field": "model_name", "value": "GPT-4o", "part_id": "P1#p001",
             "supporting_text": None},
            {"field": "contracting_party", "value": None, "part_id": None, "supporting_text": None},
            {"field": "adoption_stage", "value": "pilot", "part_id": "P1#p001", "supporting_text": "x"},
        ],
    }])), page, plan)
    (act,) = out.activities
    assert act.status == "resolved"
    assert TEXT[act.start:act.end].startswith("The council launched the CivicBot")
    assert TEXT[act.start:act.end].endswith("in its first month.")
    assert [(f.item_id, f.value) for f in act.fields] == [("core.activity_name", "CivicBot")]
    assert all(f.supporting_text for f in act.fields)
    assert {r.reason for r in out.rejected} == {"no_supporting_text", "not_requested"}


def test_span_offsets_are_from_the_whole_page_on_chunked_pages():
    text = ("Alpha sentence about the council. " * 40) + "\n\n" + (
        "The city launched a GenAI drafting pilot for staff. " * 1) + ("Beta sentence on GenAI. " * 40)
    page = make_page(text=text, limit=150, codes=[PageCode("core.page_verdict", "P1#p001", "confirms_activity")])
    part = next(c for c in page.chunks if "drafting pilot" in c.text)
    assert part.start > 0
    s, e, status = parser_v27.resolve_span(page, part.chunk_id, "The city launched a GenAI",
                                           "drafting pilot for staff.")
    assert status == "resolved" and s >= part.start
    assert text[s:e] == "The city launched a GenAI drafting pilot for staff."


def test_span_whitespace_insensitive_and_unresolved():
    page = make_page(codes=[])
    s, e, status = parser_v27.resolve_span(page, "P1#p001", "Read more   about\nCivicBot", "project page.")
    assert status == "resolved" and TEXT[s:e] == "Read more about CivicBot on the project page."
    assert parser_v27.resolve_span(page, "P1#p001", "not on the page", "x")[2] == "unresolved_start"


@pytest.mark.parametrize("start,end,status", [
    ("", "", "unresolved_start"), (" ", " ", "unresolved_start"), ("\n\t", "page.", "unresolved_start"),
    ("Read more", "", "unresolved_end"), ("Read more", "   ", "unresolved_end"),
])
def test_empty_or_whitespace_anchor_leaves_span_unresolved(start, end, status):
    # Lane B F3: no offset is guessed for an anchor that names no place (was (0, 0) / (4, 5)).
    assert parser_v27.resolve_span(make_page(codes=[]), "P1#p001", start, end) == (None, None, status)


def test_malformed_anchors_and_ids_are_contract_errors_not_type_errors():
    page = _activity_page()
    plan = select_requests(page)
    for bad in (
        empty_answer(activities=[{"part_id": "P1#p001", "start_text": None, "end_text": "2024.",
                                  "fields": []}]),
        empty_answer(activities=[{"part_id": "P1#p001", "start_text": "The", "end_text": ["x"],
                                  "fields": []}]),
        empty_answer(activities=[{"part_id": ["P1#p001"], "start_text": "The", "end_text": "2024.",
                                  "fields": []}]),
        empty_answer(quotes=[{"task_id": ["q001"], "part_id": "P1#p001", "quote": "council"}]),
        empty_answer(quotes=[{"task_id": "q001", "part_id": {"p": 1}, "quote": "council"}]),
        empty_answer(links=[{"link_id": ["L001"], "part_id": "P1#p001", "quote": "x"}]),
        empty_answer(activities=[{"part_id": "P1#p001", "start_text": "The", "end_text": "2024.",
                                  "fields": [{"field": ["activity_name"], "value": "x",
                                              "part_id": "P1#p001", "supporting_text": "x"}]}]),
    ):
        with pytest.raises(ExtractContractError):
            parse_pass1_result(ok(bad), page, plan)


@pytest.mark.parametrize("shape", [5, "x", {"k": 1}, True])
@pytest.mark.parametrize("where", ["quotes", "links", "activities", "activity fields"])
def test_array_field_of_the_wrong_shape_is_a_contract_error(where, shape):
    """Ruling 30 a: an array field that is not a list raises ExtractContractError (never a
    TypeError/KeyError/AttributeError); null still reads as empty."""
    page = _activity_page()
    plan = select_requests(page)
    activity = {"part_id": "P1#p001", "start_text": "The", "end_text": "2024.", "fields": []}
    if where == "activity fields":
        bad, null = (empty_answer(activities=[{**activity, "fields": v}]) for v in (shape, None))
    else:
        bad, null = empty_answer(**{where: shape}), empty_answer(**{where: None})
    with pytest.raises(ExtractContractError, match="must be an array"):
        parse_pass1_result(ok(bad), page, plan)
    parse_pass1_result(ok(null), page, plan)


def test_empty_anchor_activity_is_kept_unresolved_and_the_page_parses():
    page = _activity_page()
    out = parse_pass1_result(ok(empty_answer(activities=[
        {"part_id": "P1#p001", "start_text": "", "end_text": "", "fields": []},
        {"part_id": "P1#p001", "start_text": "The council launched", "end_text": "March 2024.",
         "fields": []},
    ])), page, select_requests(page))
    assert [(a.start is None, a.status) for a in out.activities] == [
        (True, "unresolved_start"), (False, "resolved")]


def test_parser_rejects_code_fields():
    page = _activity_page()
    plan = select_requests(page)
    bad = empty_answer()
    bad["page_verdict"] = "confirms_activity"
    with pytest.raises(ExtractContractError):
        parse_pass1_result(ok(bad), page, plan)
    bad2 = empty_answer(quotes=[{"task_id": "q001", "part_id": "P1#p001", "quote": "x",
                                 "code": "confirms_activity"}])
    with pytest.raises(ExtractContractError):
        parse_pass1_result(ok(bad2), page, plan)


def test_parser_date_and_unrequested_output():
    page = make_page(verdict="background_only",
                     codes=[PageCode("core.source_type", "P1#p001", "vendor")])
    plan = select_requests(page)
    out = parse_pass1_result(ok(empty_answer(
        publication_date={"value": "3 April 2024", "part_id": "P1#p001",
                          "supporting_text": "Published 3 April 2024."},
        activities=[{"part_id": "P1#p001", "start_text": "a", "end_text": "b", "fields": []}],
    )), page, plan)
    assert out.publication_date.value == "3 April 2024"
    assert out.publication_date.chunk_id == "P1#p001"
    assert out.activities == () and out.rejected[0].reason == "not_requested"


def test_fixture_free_text_values_all_have_support():
    """Every free-text value the parser emits in these fixtures has supporting text."""
    page = _activity_page()
    plan = select_requests(page)
    fields = [{"field": f, "value": "v", "part_id": "P1#p001", "supporting_text": None if i % 2 else "s"}
              for i, f in enumerate(["activity_name", "tool_name", "model_name", "observed_actor_name"])]
    out = parse_pass1_result(ok(empty_answer(activities=[{
        "part_id": "P1#p001", "start_text": "The council", "end_text": "first month.",
        "fields": fields}])), page, plan)
    emitted = [f for a in out.activities for f in a.fields]
    assert emitted and all(f.supporting_text for f in emitted)
    assert len(out.rejected) == 2


def test_parser_refuses_failed_result():
    page = _activity_page()
    with pytest.raises(RuntimeError):
        parse_pass1_result(ExtractorResult("c", False, None, {"type": "refusal"}), page,
                           select_requests(page))


# ---------------------------------------------------------------------------
# Anthropic client (mocked)
# ---------------------------------------------------------------------------


def _msg(text, stop="end_turn"):
    return SimpleNamespace(
        id="msg_1", model="claude-haiku-5-5", stop_reason=stop, stop_details=None,
        usage={"input_tokens": 10, "output_tokens": 5},
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        _request_id="req_1",
    )


class FakeBatches:
    def __init__(self):
        self.created = None

    def create(self, requests):
        self.created = requests
        return SimpleNamespace(id="msgbatch_1")

    def retrieve(self, batch_id):
        return SimpleNamespace(processing_status="ended")

    def results(self, batch_id):
        yield SimpleNamespace(custom_id="b", result=SimpleNamespace(
            type="errored", error=SimpleNamespace(error=SimpleNamespace(type="invalid_request", message="m"))))
        yield SimpleNamespace(custom_id="a", result=SimpleNamespace(type="succeeded", message=_msg("{}")))
        yield SimpleNamespace(custom_id="c", result=SimpleNamespace(type="expired"))


class FakeClient:
    def __init__(self):
        self.batches = FakeBatches()
        self.messages = SimpleNamespace(create=self._create, batches=self.batches)
        self.calls = []

    def _create(self, **params):
        self.calls.append(params)
        return _msg('{"quotes": []}')


def test_sync_create_reads_text_skips_thinking_and_records_ids():
    fake = FakeClient()
    client = AnthropicExtractorClient(fake)
    job = ExtractorJob("x27-a", ac.build_params(system="s", user="u", output_schema={"type": "object"}))
    res = client.create(job)
    assert res.success and res.text == '{"quotes": []}'
    assert (res.message_id, res.request_id, res.response_model) == ("msg_1", "req_1", "claude-haiku-5-5")
    assert res.usage == {"input_tokens": 10, "output_tokens": 5}
    assert fake.calls[0]["output_config"]["effort"] == "medium"


@pytest.mark.parametrize("stop,err", [("refusal", "refusal"), ("max_tokens", "max_tokens")])
def test_refusal_and_max_tokens_are_failures(stop, err):
    res = ac.result_from_message("x", _msg("{}", stop=stop))
    assert not res.success and res.error["type"] == err


def test_batch_submit_and_results_keyed_by_custom_id():
    fake = FakeClient()
    client = AnthropicExtractorClient(fake)
    jobs = [ExtractorJob(f"x27-{n}", ac.build_params(system="s", user="u", output_schema={}))
            for n in "ab"]
    assert client.submit_batch(jobs) == "msgbatch_1"
    assert [r["custom_id"] for r in fake.batches.created] == ["x27-a", "x27-b"]
    assert client.batch_status("msgbatch_1") == "ended"
    res = {r.custom_id: r for r in client.batch_results("msgbatch_1")}
    assert res["a"].success
    assert res["b"].error == {"type": "errored", "error_type": "invalid_request", "message": "m"}
    assert res["c"].error == {"type": "expired"}
    with pytest.raises(ValueError):
        client.submit_batch([jobs[0], jobs[0]])


def test_custom_id_is_batches_safe():
    cid = make_custom_id("inst::1", "https://example.gov/a?b=c")
    assert len(cid) <= 64 and cid.replace("-", "").replace("_", "").isalnum()
    with pytest.raises(ValueError):
        ExtractorJob("inst::1::abc", {})


def test_split_for_batches_refuses_oversize_never_truncates():
    small = ExtractorJob("x27-s", ac.build_params(system="s", user="u", output_schema={}))
    big = ExtractorJob("x27-b", ac.build_params(system="s", user="u" * 5000, output_schema={}))
    batches, refused = split_for_batches([small, big, small], max_requests=1, max_request_bytes=2000)
    assert [[j.custom_id for j in b] for b in batches] == [["x27-s"], ["x27-s"]]
    assert refused == [big]
    assert big.params["messages"][0]["content"] == "u" * 5000


def test_build_jobs_end_to_end_with_mocked_batch():
    pages = [_activity_page(), make_page(page_id="P2", verdict="no_genai")]
    jobs, plans = build_jobs(pages)
    assert len(jobs) == 1 and plans["P1"].needs_request and not plans["P2"].needs_request
    assert jobs[0].metadata["page_id"] == "P1"
