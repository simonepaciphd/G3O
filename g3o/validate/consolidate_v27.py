"""Pure, evidence-preserving Stage 6 planning and reduction (T-026).

This is not the Stage 6 provider executor or a StorageEnvelope producer. Callers
must supply final, support-checked outcomes and real source metadata. In
particular, this module cannot invent source confidence, permanent-pilot proof,
missing support, or fresh pooled classifier answers. Relation and pooling plans
remain explicit until those upstream operations complete.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Any

from g3o.classify.questions.v27 import load_set
from g3o.common.storage_fields import FIELDS

VERDICTS = (
    "confirms_activity", "ambiguous_attribution", "ambiguous_genai", "other_body",
    "event_only", "background_only", "confirms_absence", "no_genai", "not_assessable",
)
NEGATIVE = frozenset({"other_body", "event_only", "background_only", "confirms_absence", "no_genai"})
RELATIONS = frozenset({"same_activity", "shared_participation", "component_of_program",
                       "has_component", "governs", "governed_by", "distinct_action", "unresolved",
                       "not_an_activity"})
MERGES = frozenset({"same_activity", "shared_participation"})
CHANNELS = frozenset({"web_extract", "procurement", "ai_text"})
MISSING = frozenset({"not_documented", "not_asked", "unknown", "_NA_"})
PASSED = frozenset({"supported", "not_required", "set_by_rule"})


class ConsolidationError(ValueError):
    """An input cannot be consolidated without inventing evidence or a rule."""


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConsolidationError(f"{name} must be an actual nonempty identifier")


def _probability(value: float | None) -> bool:
    if value is None:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 1:
        raise ConsolidationError("chosen-answer probability must be in [0, 1]")
    return value >= .8


@dataclass(frozen=True)
class ReviewedPage:
    """One actual attempted page, never one record per activity on that page.

    ``page_id`` is the caller's deduplicated actual page identity. A failed fetch
    or unfollowed link has ``reviewed=False`` and a real failure reason. An
    unreadable but reviewed page has ``not_assessable`` and its rule provenance.
    """
    page_id: str
    pipeline: str
    page_verdict: str
    chosen_probability: float | None
    support_status: str
    reviewed: bool
    failed: bool
    followed: bool
    source_ids: tuple[str, ...]
    raw_records: tuple[Any, ...]
    support_records: tuple[Any, ...]
    failure_reason: str | None = None


@dataclass(frozen=True)
class ActivityObservation:
    observation_id: str
    page_id: str
    final_outcomes: Mapping[str, Any]
    fields: Mapping[str, Any]
    supported: bool
    raw_records: tuple[Any, ...]
    support_records: tuple[Any, ...]


@dataclass(frozen=True)
class RelationDecision:
    lhs: str
    rhs: str
    relation: str
    chosen_probability: float | None
    support_status: str
    raw_records: tuple[Any, ...]
    support_ids: tuple[str, ...]
    scope: str  # within_page / cross_page

    @property
    def mergeable(self) -> bool:
        return (self.relation in MERGES and _probability(self.chosen_probability)
                and self.support_status == "supported")


@dataclass(frozen=True)
class SupportingQuote:
    """Actual support plus source metadata; missing publication dates stay absent."""
    observation_id: str
    support_id: str
    quote_text: str
    chunk_id: str
    source_type_label: str
    source_publication_date: str | None
    stage_as_of: str
    page_url: str
    page_order: int
    passage_order: int


@dataclass(frozen=True)
class PoolPlan:
    observation_ids: tuple[str, ...]
    quotes: tuple[SupportingQuote, ...]
    state: Mapping[str, Any]
    question_set_version: str


@dataclass(frozen=True)
class ConsolidationPlan:
    groups: tuple[tuple[str, ...], ...]
    relations: tuple[RelationDecision, ...]
    missing_pairs: tuple[tuple[str, str], ...]
    conflicting_groups: tuple[tuple[str, ...], ...]

    @property
    def ready(self) -> bool:
        return not self.missing_pairs and not self.conflicting_groups


def outcome_values(outcomes: Mapping[str, Any]) -> dict[str, Any]:
    """Project real FinalActivity/FinalPage outcomes, refusing unfinished gates.

    Multipart answers retain their part names. This deliberately does not fill
    any items absent from the finalized artifact.
    """
    values: dict[str, Any] = {}
    for outcome in outcomes.values():
        if getattr(outcome, "state", None) in {"pending", "stopped"} or outcome.value is None:
            raise ConsolidationError("unfinished final outcome; run the required extra round")
        item = outcome.item_id
        part = getattr(outcome, "part", None)
        if part is None:
            if item in values:
                raise ConsolidationError(f"duplicate outcome for {item}")
            values[item] = outcome.value
        else:
            parts = values.setdefault(item, {})
            if not isinstance(parts, dict) or part in parts:
                raise ConsolidationError(f"duplicate/conflicting multipart outcome for {item}")
            parts[part] = outcome.value
    return values


def relation_plan(observations: Sequence[ActivityObservation], pages: Sequence[ReviewedPage],
                  decisions: Sequence[RelationDecision]) -> ConsolidationPlan:
    """Group only explicit, supported relations; names are never a merge key.

    Every pair needs a decision before a plan is complete. An inconsistent
    transitive component is held as single observations, with the whole
    component exposed for resolution; no edge ordering silently wins.
    """
    page_map = _pages(pages)
    obs = {o.observation_id: o for o in observations}
    if len(obs) != len(observations):
        raise ConsolidationError("duplicate observation identity")
    for observation in observations:
        _identifier(observation.observation_id, "observation_id")
        if observation.page_id not in page_map:
            raise ConsolidationError("observation has no attempted page")
        outcome_values(observation.final_outcomes)
    edges: dict[frozenset[str], RelationDecision] = {}
    adjacent: dict[str, set[str]] = {key: set() for key in obs}
    for decision in decisions:
        if decision.lhs == decision.rhs or decision.lhs not in obs or decision.rhs not in obs:
            raise ConsolidationError("relation has invalid observation endpoints")
        if decision.relation not in RELATIONS:
            raise ConsolidationError("relation is outside the signed vocabulary")
        key = frozenset((decision.lhs, decision.rhs))
        if key in edges:
            raise ConsolidationError("duplicate relation pair; resolve direction before consolidation")
        same_page = obs[decision.lhs].page_id == obs[decision.rhs].page_id
        if decision.scope != ("within_page" if same_page else "cross_page"):
            raise ConsolidationError("relation scope disagrees with actual page identities")
        if decision.relation == "not_an_activity" and not same_page:
            raise ConsolidationError("not_an_activity is within-page only")
        _probability(decision.chosen_probability)
        if not decision.raw_records:
            raise ConsolidationError("relation lost its original coder records")
        if decision.support_status == "supported" and not decision.support_ids:
            raise ConsolidationError("supported relation has no support references")
        edges[key] = decision
        if decision.mergeable:
            adjacent[decision.lhs].add(decision.rhs)
            adjacent[decision.rhs].add(decision.lhs)
    missing = tuple((a, b) for a, b in combinations(obs, 2) if frozenset((a, b)) not in edges)
    seen: set[str] = set()
    groups: list[tuple[str, ...]] = []
    conflicts: list[tuple[str, ...]] = []
    for start in obs:
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacent[current] - component)
        seen.update(component)
        ordered = tuple(key for key in obs if key in component)
        if any(frozenset((a, b)) not in edges or not edges[frozenset((a, b))].mergeable
               for a, b in combinations(ordered, 2)):
            conflicts.append(ordered)
            groups.extend((key,) for key in ordered)
        else:
            groups.append(ordered)
    return ConsolidationPlan(tuple(groups), tuple(decisions), missing, tuple(conflicts))


def pool_plan(group: Sequence[str], observations: Sequence[ActivityObservation],
              pages: Sequence[ReviewedPage], quotes: Sequence[SupportingQuote]) -> PoolPlan:
    """Plan X31 input; non-confirmed observations contribute relations only.

    The executor still must apply T-020 token splitting and T-024 checks to each
    fresh pooled answer. This planner never reuses per-page codes as pooled codes.
    """
    page_map = _pages(pages)
    obs = {o.observation_id: o for o in observations}
    if not group or len(set(group)) != len(group) or any(key not in obs for key in group):
        raise ConsolidationError("pool must name existing unique observations")
    eligible = tuple(key for key in group if obs[key].supported and _positive(page_map[obs[key].page_id]))
    selected = tuple(q for q in quotes if q.observation_id in eligible)
    if any(not any(q.observation_id == key for q in selected) for key in eligible):
        raise ConsolidationError("eligible pooled observation has no actual support quote")
    if len({q.support_id for q in selected}) != len(selected):
        raise ConsolidationError("duplicate pooled support identity")
    for quote in selected:
        for name in ("support_id", "quote_text", "chunk_id", "source_type_label", "stage_as_of", "page_url"):
            _identifier(getattr(quote, name), name)
        if quote.source_publication_date in MISSING:
            raise ConsolidationError("missing publication date must be omitted")
        if quote.page_order < 0 or quote.passage_order < 0:
            raise ConsolidationError("pool order must be actual nonnegative page positions")
    ordered = tuple(sorted(selected, key=lambda q: (q.source_publication_date or q.stage_as_of,
                                                    q.page_order, q.passage_order)))
    qset = load_set("institution")
    quote_state = []
    for q in ordered:
        row = {"quote_text": q.quote_text, "source_type": q.source_type_label, "page_url": q.page_url}
        if q.source_publication_date is not None:
            row["source_publication_date"] = q.source_publication_date
        quote_state.append(row)
    return PoolPlan(eligible, ordered, {"pool_note": qset["pooled"]["instruction"],
                                      "supporting_quotes": quote_state}, qset["question_set_version"])


def _pages(pages: Sequence[ReviewedPage]) -> dict[str, ReviewedPage]:
    indexed = {p.page_id: p for p in pages}
    if len(indexed) != len(pages):
        raise ConsolidationError("duplicate actual page identity; do not count activity claims as pages")
    for page in pages:
        _identifier(page.page_id, "page_id")
        if page.pipeline not in CHANNELS or page.page_verdict not in VERDICTS:
            raise ConsolidationError("unknown evidence channel or page verdict")
        _probability(page.chosen_probability)
        if page.reviewed:
            if not page.source_ids or not page.raw_records or not page.support_records:
                raise ConsolidationError("reviewed page lost source/coder/support provenance")
        elif not page.failure_reason:
            raise ConsolidationError("unreviewed page must retain its attempted/unfollowed reason")
        if page.failed and not page.failure_reason:
            raise ConsolidationError("failed page must retain its failure reason")
    return indexed


def _positive(page: ReviewedPage) -> bool:
    return (page.pipeline != "ai_text" and page.reviewed and not page.failed
            and page.page_verdict == "confirms_activity" and page.support_status == "supported"
            and _probability(page.chosen_probability))


def summary_values(pages: Sequence[ReviewedPage], observations: Sequence[ActivityObservation],
                   *, published_activity_values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Reduce R-005/A-010 without estimating missing evidence or source scores.

    ``published_activity_values`` must be the final pooled values, one per
    published activity. This function's count is not the observation count.
    AI-text evidence never establishes an institution verdict.
    """
    page_map = _pages(pages)
    for o in observations:
        if o.page_id not in page_map:
            raise ConsolidationError("observation has no page")
        outcome_values(o.final_outcomes)
        if o.supported and (not o.raw_records or not o.support_records):
            raise ConsolidationError("supported observation lost coder/support records")
    positive = any(o.supported and _positive(page_map[o.page_id]) for o in observations)
    if positive != bool(published_activity_values):
        raise ConsolidationError("published activity presence disagrees with supported confirmed evidence")
    relevant = [p for p in pages if p.pipeline != "ai_text"]
    web_negative = [p for p in relevant if p.pipeline == "web_extract" and p.reviewed
                    and p.page_verdict in NEGATIVE]
    clear = all((p.reviewed and not p.failed and p.page_verdict == "not_assessable"
                 and p.support_status == "set_by_rule") or
                (p.reviewed and not p.failed and p.page_verdict in NEGATIVE
                 and p.support_status in PASSED and _probability(p.chosen_probability))
                for p in relevant)
    verdict = "yes" if positive else "no" if web_negative and clear else "unclear"
    depth: dict[str, Any] = {}
    for channel in dict.fromkeys(p.pipeline for p in pages):
        current = [p for p in pages if p.pipeline == channel]
        counts = Counter(p.page_verdict for p in current if p.reviewed)
        depth[channel] = {"n_pages_reviewed": sum(p.reviewed for p in current),
                          "n_pages_by_verdict": {v: counts[v] for v in VERDICTS},
                          "n_pages_failed": sum(p.failed for p in current),
                          "n_followed_links": sum(p.followed for p in current)}
    tiers = []
    for activity in published_activity_values:
        required = ("core.action_type", "core.adoption_stage", "core.procurement_status", "core.activity_type")
        if any(key not in activity for key in required):
            raise ConsolidationError("evidence tier requires actual finalized action/stage/procurement/type")
        for key in required:
            if activity[key] not in FIELDS[key]["schema"]["enum"]:
                raise ConsolidationError(f"evidence tier received an unsigned value for {key}")
        action, stage, purchase = (activity[key] for key in required[:3])
        if action in {"deployment", "program"} and stage in {"pilot", "production", "discontinued"}:
            tiers.append((4, "documented_use"))
        elif stage == "announced" or purchase in {"tender_or_rfp", "award_or_contract", "payment_or_subscription"}:
            tiers.append((3, "documented_commitment"))
        elif action in {"governance", "staff_training"}:
            tiers.append((2, "governance_or_training_only"))
        elif stage == "proposed":
            tiers.append((1, "proposal_only"))
        else:
            tiers.append((0, "unclear"))
    tier = max(tiers)[1] if tiers else "none_found" if verdict == "no" else "unclear"
    types = sorted({str(a["core.activity_type"]) for a in published_activity_values})
    stages = sorted({str(a["core.adoption_stage"]) for a in published_activity_values})
    reviewed = sum(p.reviewed for p in pages)
    failed = sum(p.failed for p in pages)
    # X33 specifies these facts, not fixed prose. These labels are mechanical
    # presentation of the codes/counts, not a quoted or newly interpreted rule.
    summary = (f"GenAI activity: {verdict}. Activities: {len(published_activity_values)}. "
               f"Types: {', '.join(types) or 'none'}. Stages: {', '.join(stages) or 'none'}. "
               f"Pages reviewed: {reviewed}; failed: {failed}.")
    return {"core.has_genai_activity": verdict, "core.verdict_rule": load_set("institution")["codebook_release"],
            "core.evidence_tier": tier, "core.review_depth": depth, "core.institution_summary": summary}


def activity_confidence(source_confidences: Mapping[str, str], independence_groups: Mapping[str, str]) -> str:
    """Combine already-coded source confidence; do not invent the T-015 map.

    Inputs must be supporting sources that agree for this activity. A duplicate
    or syndicated copy has the same independence-group identity as its source.
    """
    if not source_confidences or set(source_confidences) != set(independence_groups):
        raise ConsolidationError("confidence requires actual sources and their independence groups")
    rank = {"low": 0, "medium": 1, "high": 2}
    if any(value not in rank for value in source_confidences.values()):
        raise ConsolidationError("source confidence is absent or unruled")
    for group in independence_groups.values():
        _identifier(group, "source independence group")
    medium_groups = {independence_groups[sid] for sid, value in source_confidences.items() if value == "medium"}
    if "high" in source_confidences.values() or len(medium_groups) >= 2:
        return "high"
    return max(source_confidences.values(), key=rank.__getitem__)
