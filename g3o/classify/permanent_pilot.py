"""The permanent_pilot override, shared by T-023 and T-026 (RC-D-025 B2 a).

Codebook r15 ``core.permanent_pilot`` rules/0: "A supported `yes` sets the final
`adoption_stage` to `production` only when the stage answer is `pilot` or
`production`; for any other stage the classifier's stage answer is kept and this
flag is kept as coded."

One helper, applied to final (support-checked, combined) outcomes:

- T-023 :func:`g3o.classify.jev_activity_code.finalize_activities`, per page
  activity after the support-checked re-combine;
- T-026 :func:`g3o.validate.stage6_v27.pool_activity`, re-applied after the
  cross-page (pooled) combination (PI 2026-11-10 item 6 a).

Rulings held here: B2 a (override to ``production`` only from ``pilot`` /
``production``); RC-D-027 4 a (the rule is recorded only when the value
changes, so a ``production`` stage is left untouched); 5 a (the overridden
stage keeps its original part and probability, only value, rule and note
change). "Supported" is the T-024 status of the part that produced the
combined ``yes``; the flag itself is never changed.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

PERMANENT_PILOT_ITEM = "core.permanent_pilot"
ADOPTION_STAGE_ITEM = "core.adoption_stage"
PERMANENT_PILOT_RULE = "permanent_pilot_override:" + PERMANENT_PILOT_ITEM
#: Combined stage answers the override applies to; any other stage is kept (B2 a).
PERMANENT_PILOT_STAGES = frozenset({"pilot", "production"})
PERMANENT_PILOT_TARGET = "production"
SUPPORTED = "supported"


def _whole_item_qid(by_id: Mapping[str, Mapping[str, Any]], item_id: str) -> str | None:
    return next((qid for qid, q in by_id.items() if q["item_id"] == item_id and q.get("part") is None), None)


def apply_permanent_pilot_override(final: dict[str, Any], by_id: Mapping[str, Mapping[str, Any]],
                                   part_status: Callable[[str, str], str | None], *, scope: str) -> None:
    """In place, on the final outcomes (``ItemOutcome`` by question id).

    ``part_status(question_id, part_id)`` returns the T-024 support status of
    that part's answer (``None`` when unchecked). ``scope`` names the
    combination in the note (``combined`` for T-023, ``pooled`` for T-026).
    """
    pp_qid = _whole_item_qid(by_id, PERMANENT_PILOT_ITEM)
    stage_qid = _whole_item_qid(by_id, ADOPTION_STAGE_ITEM)
    pp = final.get(pp_qid) if pp_qid is not None else None
    stage = final.get(stage_qid) if stage_qid is not None else None
    if pp is None or stage is None:
        return
    if pp.state != "combined" or pp.value != "yes" or pp.failed or pp.part_id is None:
        return
    if part_status(pp_qid, pp.part_id) != SUPPORTED:
        return
    if stage.state != "combined" or stage.failed or stage.value not in PERMANENT_PILOT_STAGES:
        return
    if stage.value == PERMANENT_PILOT_TARGET:
        return
    final[stage_qid] = replace(
        stage, value=PERMANENT_PILOT_TARGET, rule_reference=PERMANENT_PILOT_RULE,
        note=(f"RC-D-025 B2 a: {scope} stage {stage.value!r} -> {PERMANENT_PILOT_TARGET!r} by a "
              f"supported permanent_pilot 'yes' (part {pp.part_id}); codebook core.permanent_pilot rules/0"))


__all__ = [
    "ADOPTION_STAGE_ITEM", "PERMANENT_PILOT_ITEM", "PERMANENT_PILOT_RULE", "PERMANENT_PILOT_STAGES",
    "PERMANENT_PILOT_TARGET", "SUPPORTED", "apply_permanent_pilot_override",
]
