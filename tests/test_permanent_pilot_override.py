"""T-023 (RC-D-025 B2 a): the permanent_pilot override after combining.

Codebook r15 ``core.permanent_pilot`` rules/0: a supported ``yes`` sets the final
``adoption_stage`` to ``production`` only when the (combined) stage answer is
``pilot`` or ``production``; any other stage keeps the classifier's answer and the
flag is kept as coded.
"""

from __future__ import annotations

import pytest

from g3o.classify import jev_activity_code as jac
from tests.test_jev_activity_code import A1, BASE, TEXT, FakeJev, _support, config, make_page, span

PP = "core.permanent_pilot"
STAGE = "core.adoption_stage"


def _final(choices, overrides=None, cuts=None, combiner=None):
    inp = make_page(TEXT, cuts=cuts, spans=[span("x1", *A1)])
    cfg = config(combiner)
    res = jac.code_page(inp, FakeJev({**BASE, **choices}), cfg)
    return res, jac.finalize_activities(res, _support(res, overrides), cfg)[0]


def test_supported_yes_and_pilot_becomes_production():
    res, f = _final({STAGE: "pilot", PP: "yes"})
    assert res.activities[0].outcomes[STAGE].value == "pilot"  # provisional: no override yet
    o = f.outcomes[STAGE]
    assert (o.state, o.value, o.rule_reference) == ("combined", "production", jac.PERMANENT_PILOT_RULE)
    assert "RC-D-025 B2 a" in o.note
    assert f.outcomes[PP].value == "yes" and f.outcomes[PP].rule_reference is None  # flag as coded
    raw = [r.chosen_value for r in res.activities[0].records if r.question_id == STAGE]
    assert raw == ["pilot"]  # the classifier's raw answer stays in the records


def test_supported_yes_and_production_stays_production():
    _, f = _final({STAGE: "production", PP: "yes"})
    o = f.outcomes[STAGE]
    assert (o.value, o.rule_reference) == ("production", None)
    assert f.outcomes[PP].value == "yes"


@pytest.mark.parametrize("stage", ["proposed", "announced", "discontinued"])
def test_supported_yes_other_stage_unchanged(stage):
    _, f = _final({STAGE: stage, PP: "yes"})
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == (stage, None)
    assert f.outcomes[PP].value == "yes"


def test_supported_yes_unknown_stage_unchanged():
    _, f = _final({STAGE: "pilot", PP: "yes"}, {STAGE: "downgraded_no_quote"})
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == ("unknown", None)
    assert f.outcomes[PP].value == "yes"


@pytest.mark.parametrize("status", ["downgraded_no_quote", "downgraded_quote_not_stating_value",
                                    "downgraded_low_confidence"])
def test_unsupported_yes_leaves_stage(status):
    _, f = _final({STAGE: "pilot", PP: "yes"}, {PP: status})
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == ("pilot", None)
    assert f.outcomes[PP].value == "unknown"


def test_yes_below_bar_leaves_stage():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev({**BASE, STAGE: "pilot", PP: "yes"}, prob={PP: 0.5}), config())
    f = jac.finalize_activities(res, _support(res), config())[0]
    assert f.outcomes[STAGE].value == "pilot" and f.outcomes[PP].value == "unknown"


def test_yes_needs_the_supported_status_itself():
    _, f = _final({STAGE: "pilot", PP: "yes"}, {PP: "not_required"})
    assert f.outcomes[STAGE].value == "pilot"


def test_no_leaves_stage():
    _, f = _final({STAGE: "pilot", PP: "no"})
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == ("pilot", None)
    assert f.outcomes[PP].value == "no"


# --- multi-part, real R-044 combiner -----------------------------------------

CUT = TEXT.index("pilot")


def _by_part(p1, p2):
    return lambda state: p1 if state["page_part"].startswith("1 ") else p2


def test_multi_part_yes_in_one_part_overrides_combined_pilot():
    res, f = _final({STAGE: "pilot", PP: _by_part("no", "yes")}, cuts=[CUT, len(TEXT)],
                    combiner=jac.part_combine_adapter())
    assert res.activities[0].chunk_ids == ("p1:c0", "p1:c1")
    assert f.outcomes[PP].value == "yes" and f.outcomes[PP].part_id == "p1:c1"  # any_yes
    o = f.outcomes[STAGE]
    assert (o.value, o.rule_reference) == ("production", jac.PERMANENT_PILOT_RULE)
    assert "p1:c1" in o.note


def test_multi_part_combined_stage_discontinued_wins_and_is_kept():
    _, f = _final({STAGE: _by_part("pilot", "discontinued"), PP: _by_part("yes", "no")},
                  cuts=[CUT, len(TEXT)], combiner=jac.part_combine_adapter())
    assert f.outcomes[PP].value == "yes"
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == ("discontinued", None)


def test_multi_part_unsupported_yes_part_does_not_override():
    inp = make_page(TEXT, cuts=[CUT, len(TEXT)], spans=[span("x1", *A1)])
    cfg = config(jac.part_combine_adapter())
    res = jac.code_page(inp, FakeJev({**BASE, STAGE: "pilot", PP: _by_part("no", "yes")}), cfg)
    sup = [s if not (s.item_id == PP and s.chunk_id == "p1:c1") else
           type(s)(s.item_id, s.part, s.activity_id, s.chunk_id, "downgraded_no_quote")
           for s in _support(res)]
    f = jac.finalize_activities(res, sup, cfg)[0]
    assert f.outcomes[PP].value == "no"
    assert (f.outcomes[STAGE].value, f.outcomes[STAGE].rule_reference) == ("pilot", None)


def test_t023_and_t026_share_one_override_helper():
    from g3o.classify import permanent_pilot
    from g3o.validate import stage6_v27

    assert jac.PERMANENT_PILOT_RULE is permanent_pilot.PERMANENT_PILOT_RULE is stage6_v27.PERMANENT_PILOT_RULE
    assert jac.apply_permanent_pilot_override is stage6_v27.apply_permanent_pilot_override
    assert not hasattr(jac, "_permanent_pilot_override")
