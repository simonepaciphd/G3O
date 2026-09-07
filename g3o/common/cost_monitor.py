"""Continuous cost monitoring for live presweep runs.

Tracks actual API spend as batches complete during execution, accumulating
token usage across stages and aborting mid-run if the running total exceeds
the configured budget. Complements (does not replace) the pre-flight cost
gate from :mod:`g3o.run.preflight`.

Architecture:
  1. ``run_chunked_stage()`` (in :mod:`g3o.common.run_state`) writes per-chunk
     token usage to the state file after each batch completes.
  2. After each LLM stage completes, the orchestrator calls
     :meth:`CostMonitor.record_stage`, which reads the ``.done/<stage>.json``
     state file, sums usage across chunks, computes USD cost, and accumulates
     it into a running total.
  3. The orchestrator calls :meth:`CostMonitor.check_budget` after each stage.
     If the running total exceeds the budget, it raises
     :class:`BudgetExceededError` and aborts the run cleanly.
  4. The orchestrator persists ``_cost_report.json`` in the run directory
     (even on abort) for post-mortem analysis.

Pricing:
  Rates come from :mod:`g3o.common.pricing`, looked up by the run's ``model``
  (review F2, 2026-08-24) — the same registry :mod:`g3o.run.preflight` uses, so
  the projection and the actual are always priced off one table. Cached tokens
  are priced at ``batch_cached_input_per_1m_usd``, which is an estimate
  (standard cached rate × batch discount). Like the batch discount itself, this
  should be reconciled against the first live invoice.

  A model with no rate row is refused when a budget is set and reported with
  null USD when one is not; see :class:`UnpricedModelError` and
  :meth:`CostMonitor._pricing_block`.

Edge cases:
  - State files without ``usage`` (pre-existing runs) are handled gracefully
    (treated as 0 tokens).
  - Failed jobs have no usage; only successful results are summed.

Limitations:
  - **Check-after-stage only**: Budget is checked after each LLM stage completes.
    A single stage (e.g. a large extract batch) may spend significantly more
    than the remaining budget before the check triggers. The budget ceiling
    should therefore be set with enough headroom for one full stage's cost.
  - **Serper cost not tracked**: Serper API calls (Stages 1a and 1b) have a
    separate billing model (per-query credits, not token-based) and are not
    included in the running total. Only OpenAI Batch API spend is monitored.
    Factor Serper credits into your budget separately.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.common.batch_client import DEFAULT_MODEL
from g3o.common.pricing import pricing_for, usd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class BudgetExceededError(RuntimeError):
    """Raised when actual spend exceeds the configured budget limit.

    The orchestrator catches this and aborts the run cleanly, persisting the
    cost report and any already-completed stages.
    """

    def __init__(self, spent: float, budget: float, stage: str) -> None:
        self.spent = spent
        self.budget = budget
        self.stage = stage
        super().__init__(
            f"Budget exceeded after stage {stage}: "
            f"${spent:.4f} spent of ${budget:.4f} limit "
            f"(overrun: ${spent - budget:.4f})"
        )


def _round_usd(value: float | None) -> float | None:
    """Round a USD figure for serialization, preserving ``None`` as ``None``.

    ``None`` means "this model has no rate row", which must reach the JSON as
    ``null`` rather than becoming ``0.0`` at the last step (review F2).
    """
    return None if value is None else round(value, 6)


class UnpricedModelError(RuntimeError):
    """A budget was set for a model this pipeline has no rate row for.

    Review F2 (2026-08-24), PI ruling half 1. A ceiling is a promise to stop at a
    number, and that promise cannot be kept for a model whose price is unknown —
    the alternative, pricing it as ``gpt-5-nano``, is exactly the silent
    mispricing the rate registry exists to remove.

    Raised from :meth:`CostMonitor.__post_init__` and, earlier and more cheaply,
    from :func:`g3o.run.preflight.run_preflight`. A run with no ceiling does not
    raise: it proceeds and reports null USD (ruling half 2).
    """

    def __init__(self, model: str, *, budget_usd: float) -> None:
        self.model = model
        self.budget_usd = budget_usd
        super().__init__(
            f"no pricing is registered for model {model!r}, so a budget of "
            f"${budget_usd:.4f} cannot be enforced. Refusing to start: an "
            f"unpriceable model cannot be gated, and pricing it as gpt-5-nano "
            f"would under-report real spend without anyone noticing. Add a rate "
            f"row for {model!r} to g3o.common.pricing.PRICING, or run without a "
            f"budget ceiling (spend is then reported in tokens, with null USD)."
        )


class ProjectedBudgetExceededError(BudgetExceededError):
    """Raised when *projected* total spend (scaled by actual/preflight ratio)
    exceeds the budget before all stages have run.

    Unlike :class:`BudgetExceededError` (which fires when actual spend has
    already breached the limit), this fires when the run is on track to
    overshoot based on mid-run cost trends — aborting *before* the spend
    materialises.
    """

    def __init__(
        self,
        spent: float,
        budget: float,
        stage: str,
        *,
        projected_total: float,
        safety_factor: float,
    ) -> None:
        self.projected_total = projected_total
        self.safety_factor = safety_factor
        super().__init__(spent, budget, stage)

    def __str__(self) -> str:
        return (
            f"Projected budget exceeded: "
            f"projected total ${self.projected_total:.4f} "
            f"(threshold: ${self.budget:.4f} × {self.safety_factor} = "
            f"${self.budget * self.safety_factor:.4f}) — "
            f"${self.spent:.4f} spent of ${self.budget:.4f} limit after stage {self.stage}"
        )


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StageCost:
    """Cost breakdown for one LLM stage.

    ``n_jobs`` is the total number of jobs (LLM calls) in the stage.
    ``n_chunks`` is the number of chunks the jobs were split into.
    ``data_missing`` indicates the .done file was not found, meaning the cost
    is unknown (not zero). When True, ``total_usd`` should not be trusted.

    The three USD fields are ``None`` when the run's model has no rate row
    (review F2, 2026-08-24). That is a *different* unknown from
    ``data_missing``: the token counts beside them are exact and measured, and
    only the conversion to dollars is unavailable. Reporting ``0.0`` there would
    assert a spend of zero, which is the fabrication this distinction removes.
    """

    stage: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    input_usd: float | None
    output_usd: float | None
    total_usd: float | None
    n_jobs: int
    n_chunks: int
    # Total planned chunks for partial stages (diagnostic only).
    # For completed stages this equals n_chunks. For partial stages read
    # from an active state file, this records how many chunks were planned
    # so the report can show "3 of 8 completed".
    n_chunks_planned: int | None = None
    # True when the .done file was missing — the stage's cost is unknown,
    # not zero. Budget checks treat this conservatively.
    data_missing: bool = False


@dataclass
class CostMonitor:
    """Tracks actual API spend across stages and enforces budget limits.

    Instantiate once at the start of a live run. After each LLM stage completes,
    call :meth:`record_stage` to accumulate its cost, then :meth:`check_budget`
    to see if the run should abort.

    ``model`` is the model the run actually submits, and it selects the rate row
    (review F2, 2026-08-24). Passing ``pricing`` explicitly still wins, for tests
    that want to pin rates without registering a model.

    A model with no row is refused **here** when a budget is set, as well as in
    :func:`g3o.run.preflight.run_preflight`. That is not redundant: both cost
    gates only run a preflight when a ceiling is set, so a library caller
    invoking :func:`g3o.run.api.launch` directly with ``budget_usd`` set reaches
    this constructor without having passed either gate. Without a ceiling an
    unpriced model is allowed through and every USD figure it produces is
    ``None`` — see :class:`StageCost`.
    """

    budget_usd: float | None
    model: str = DEFAULT_MODEL
    # Resolved from ``model`` in __post_init__ when not given. It cannot be a
    # default_factory: a dataclass factory takes no arguments and so cannot see
    # a sibling field. ``None`` after resolution means "this model has no rate
    # row", which is a state the report renders rather than an error.
    pricing: dict[str, Any] | None = None
    stages: list[StageCost] = field(default_factory=list)
    partial_stages: list[StageCost] = field(default_factory=list)
    # Preflight per-stage cost estimates (USD), for projection-based abort.
    # Set by the orchestrator from preflight output; None means no projection
    # checking (backward compatible).
    preflight_stage_estimates: dict[str, float] | None = None
    # Running partial-stage token accumulation for within-stage budget checks.
    # Keyed by stage name. Cleared when the stage completes and record_stage
    # replaces the partial tracking with final numbers.
    _partial_stage_usage: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.pricing is None:
            self.pricing = pricing_for(self.model)
        if self.pricing is None and self.budget_usd is not None:
            raise UnpricedModelError(self.model, budget_usd=self.budget_usd)

    @property
    def is_priced(self) -> bool:
        """True when this run's model has a rate row and USD figures are real."""
        return self.pricing is not None

    def _usd_for(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        *,
        label: str,
    ) -> tuple[float | None, float | None, float | None]:
        """``(input_usd, output_usd, total_usd)`` for one bundle of tokens.

        The single owner of this arithmetic (review F14, 2026-08-24). It was
        previously written out three times — in ``record_stage``,
        ``record_partial_stage`` and ``check_budget_with_partial`` — identically
        except that the third silently omitted the ``cached > prompt`` warning.
        Once the rates became model-keyed, three copies meant three chances for
        the unpriced branch to diverge, so the duplication stopped being cosmetic.

        ``label`` names the caller in the corruption warning, which is the only
        thing that legitimately differed between the three.

        Returns ``(None, None, None)`` when the model has no rate row: the token
        counts are still exact, and only the conversion is unavailable.
        """
        if self.pricing is None:
            return (None, None, None)
        # cached_tokens should never exceed prompt_tokens, but if it does (API
        # inconsistency or a hand-edited state file), clamp rather than emit a
        # negative cost.
        if cached_tokens > prompt_tokens:
            logger.warning(
                "%s: cached_tokens (%d) > prompt_tokens (%d); clamping non-cached "
                "prompt to 0. Check state file for corruption.",
                label, cached_tokens, prompt_tokens,
            )
        non_cached_prompt = max(0, prompt_tokens - cached_tokens)
        input_usd = (
            usd(non_cached_prompt, self.pricing["batch_input_per_1m_usd"])
            + usd(cached_tokens, self.pricing["batch_cached_input_per_1m_usd"])
        )
        output_usd = usd(completion_tokens, self.pricing["batch_output_per_1m_usd"])
        return (input_usd, output_usd, input_usd + output_usd)

    def record_stage(self, run_dir: Path, stage: str) -> StageCost:
        """Read the stage's .done file, sum usage across chunks, compute cost.

        The stage must have completed (``.done/<stage>.json`` must exist). If
        the state file lacks usage data (pre-existing run, backward compat),
        all token counts are treated as 0.

        Returns the :class:`StageCost` for this stage, which is also appended
        to ``self.stages`` for the running total.
        """
        # Clear partial tracking for this stage to prevent double-counting
        # when check_budget_with_partial() is called after record_stage().
        # The .done file now owns the truth for this stage; partial usage
        # accumulated via accumulate_chunk_usage() is superseded.
        self._partial_stage_usage.pop(stage, None)
        done_file = run_dir / "_state" / ".done" / f"{stage}.json"
        if not done_file.exists():
            logger.error(
                "Stage %s: .done file not found at %s; this is an accounting "
                "failure, not a $0 stage. Marking data_missing=True so budget "
                "checks treat it conservatively.",
                stage, done_file,
            )
            # Record a sentinel entry with data_missing=True so the cost report
            # surfaces this as an accounting failure, and budget checks treat
            # it conservatively (assume over budget).
            cost = StageCost(
                stage=stage,
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=0,
                input_usd=0.0,
                output_usd=0.0,
                total_usd=0.0,
                n_jobs=0,
                n_chunks=0,
                data_missing=True,
            )
            self.stages.append(cost)
            return cost

        state = json.loads(done_file.read_text(encoding="utf-8"))
        chunks = state.get("chunks", {})

        # Sum usage across all chunks
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        for _chunk_key, chunk_entry in chunks.items():
            usage = chunk_entry.get("usage")
            if usage:
                prompt_tokens += int(usage.get("prompt_tokens", 0))
                completion_tokens += int(usage.get("completion_tokens", 0))
                cached_tokens += int(usage.get("cached_tokens", 0))

        # Cached tokens are priced at the cached rate, not the full input rate.
        input_usd, output_usd, total_usd = self._usd_for(
            prompt_tokens, completion_tokens, cached_tokens, label=f"Stage {stage}"
        )

        n_jobs = state.get("n_jobs", 0)
        n_chunks = state.get("n_chunks", len(chunks))

        cost = StageCost(
            stage=stage,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            input_usd=input_usd,
            output_usd=output_usd,
            total_usd=total_usd,
            n_jobs=n_jobs,
            n_chunks=n_chunks,
        )
        self.stages.append(cost)
        return cost

    def accumulate_chunk_usage(self, stage: str, chunk_usage: dict[str, int]) -> None:
        """Incrementally track token usage from a single completed chunk.

        Called by the within-stage budget callback (Gap 1) after each chunk
        completes. Accumulates into ``_partial_stage_usage`` so the monitor
        can check the running budget mid-stage without waiting for the full
        stage to finish. When the stage completes normally, ``record_stage``
        takes over (replacing this partial tracking with the final numbers).
        """
        if stage not in self._partial_stage_usage:
            self._partial_stage_usage[stage] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
            }
        acc = self._partial_stage_usage[stage]
        # Validate for negative values to prevent incorrect totals
        acc["prompt_tokens"] += max(0, chunk_usage.get("prompt_tokens", 0))
        acc["completion_tokens"] += max(0, chunk_usage.get("completion_tokens", 0))
        acc["cached_tokens"] += max(0, chunk_usage.get("cached_tokens", 0))

    def check_budget_with_partial(self, stage: str) -> bool:
        """Check budget including in-progress stage costs.

        Like :meth:`check_budget`, but also folds in the accumulated partial
        usage for ``stage`` (from :meth:`accumulate_chunk_usage`). Returns
        True if within budget, False if the combined total exceeds the limit.
        """
        if self.budget_usd is None:
            return True
        running = self.running_total_usd or 0.0
        # Add partial stage cost if we have accumulated usage for it
        if stage in self._partial_stage_usage:
            acc = self._partial_stage_usage[stage]
            _, _, partial_cost = self._usd_for(
                acc["prompt_tokens"],
                acc["completion_tokens"],
                acc["cached_tokens"],
                label=f"Partial stage {stage}",
            )
            running += partial_cost or 0.0
        return running <= self.budget_usd

    def check_projection(
        self,
        safety_factor: float | None = None,
    ) -> tuple[bool, float, float]:
        """Check whether projected total spend exceeds budget × safety_factor.

        Uses the preflight per-stage estimates (if set) and the actual spend
        so far to project the total run cost. The projection scales remaining
        stage estimates by the ratio of actual-to-estimated spend observed
        for completed stages.

        Returns ``(within_projection, projected_total, threshold)``.
        - ``within_projection``: True if projected total ≤ threshold
        - ``projected_total``: the projected total USD
        - ``threshold``: the abort threshold (budget × safety_factor)

        If ``safety_factor`` is None, projection checking is disabled (returns
        a no-op: True, 0.0, inf). This is the default behavior — projection
        checking must be explicitly opted into via G3O_PROJECTION_SAFETY_FACTOR
        or --projection-safety-factor, because the default factor of 3.0 applied
        to the dominant extract estimate can trigger false aborts on on-track runs.

        If no preflight estimates are set, returns ``(True, 0.0, inf)`` — a
        no-op that allows the run to proceed without projection checking.

        Edge cases:
          - If fewer than 2 stages have completed, the ratio is unreliable
            (a single cheap stage could inflate it dramatically), so we return
            a no-op until more data is available.
          - The ratio is clamped to [0.5, 3.0] to prevent wild swings from
            triggering premature aborts or allowing runaway spend.
        """
        if safety_factor is None:
            return (True, 0.0, float("inf"))
        if self.budget_usd is None or not self.preflight_stage_estimates:
            return (True, 0.0, float("inf"))

        threshold = self.budget_usd * safety_factor

        # Compute actual vs estimated for completed stages
        # `or 0.0` is unreachable in practice: this returns above when
        # budget_usd is None, and a budget with no rate row cannot be
        # constructed. It is here so the arithmetic below is total.
        actual_so_far = self.running_total_usd or 0.0
        estimated_so_far = 0.0
        remaining_estimate = 0.0
        recorded_stage_names = {s.stage for s in self.stages}

        for stage_name, estimate in self.preflight_stage_estimates.items():
            if stage_name in recorded_stage_names:
                estimated_so_far += estimate
            else:
                remaining_estimate += estimate

        # Require at least 2 completed stages before projection is meaningful.
        # A single stage (especially a cheap classify stage) could produce a
        # misleading ratio if the actual cost diverges from the estimate.
        if len(recorded_stage_names) < 2:
            logger.debug(
                "Projection check skipped: only %d stage(s) completed, need >= 2",
                len(recorded_stage_names),
            )
            return (True, actual_so_far, threshold)

        # Compute scaling ratio with bounds clamping to prevent wild swings
        if estimated_so_far > 0:
            raw_ratio = actual_so_far / estimated_so_far
            # Clamp to [0.5, 3.0]: allows reasonable variation but prevents
            # a single outlier stage from triggering premature abort (high ratio)
            # or masking runaway spend (low ratio).
            ratio = max(0.5, min(3.0, raw_ratio))
            if ratio != raw_ratio:
                logger.debug(
                    "Projection ratio clamped: raw=%.2f → clamped=%.2f",
                    raw_ratio, ratio,
                )
        else:
            ratio = 1.0

        projected_remaining = remaining_estimate * ratio
        projected_total = actual_so_far + projected_remaining

        within = projected_total <= threshold
        return (within, projected_total, threshold)

    @property
    def running_total_usd(self) -> float | None:
        """Sum of all recorded stage costs, or ``None`` when unpriced.

        ``None`` propagates rather than degrading to ``0.0``: a run on a model
        with no rate row has a real, measured token spend and an unknown dollar
        spend, and summing the unknowns to zero is the fabrication review F2
        removed. Only reachable without a budget — see :meth:`__post_init__`.
        """
        if not self.is_priced:
            return None
        return sum(s.total_usd or 0.0 for s in self.stages)

    @property
    def has_missing_data(self) -> bool:
        """True if any recorded stage has missing data (unknown cost)."""
        return any(s.data_missing for s in self.stages)

    def check_budget(self) -> bool:
        """Return True if within budget (or no budget set).

        Call this after :meth:`record_stage` to decide whether to abort.
        If any stage has missing data (data_missing=True), returns False
        conservatively — an unknown cost cannot be confirmed as within budget.
        """
        if self.budget_usd is None:
            return True
        if self.has_missing_data:
            return False
        # A budget with no rate row is refused at construction, so a priced
        # monitor is the only kind that reaches here with a budget set.
        return (self.running_total_usd or 0.0) <= self.budget_usd

    def record_and_check(self, run_dir: Path, stage: str) -> tuple[StageCost, bool]:
        """Record a stage's cost and check budget in one call.

        Convenience method that combines :meth:`record_stage` and
        :meth:`check_budget`. Returns a tuple of (stage_cost, within_budget).
        If within_budget is False, the caller should abort.
        """
        stage_cost = self.record_stage(run_dir, stage)
        within_budget = self.check_budget()
        return stage_cost, within_budget

    def record_partial_stage(self, run_dir: Path, stage: str) -> StageCost | None:
        """Read the active state file for an in-progress stage and compute partial cost.

        Unlike :meth:`record_stage`, this reads the **active** state file (not
        ``.done``) and does NOT add the result to ``self.stages`` — partial
        costs are diagnostic only and not counted in the running total. The
        result is appended to ``self.partial_stages`` instead.

        Returns None if no active state file exists (stage never started, or
        already completed and moved to .done).
        """
        from g3o.common.run_state import state_path
        active_file = state_path(run_dir, stage)
        if not active_file.exists():
            return None

        state = json.loads(active_file.read_text(encoding="utf-8"))
        chunks = state.get("chunks", {})

        # Sum usage across completed chunks only (those with usage data)
        prompt_tokens = 0
        completion_tokens = 0
        cached_tokens = 0
        n_completed_chunks = 0
        for _chunk_key, chunk_entry in chunks.items():
            usage = chunk_entry.get("usage")
            if usage:
                prompt_tokens += int(usage.get("prompt_tokens", 0))
                completion_tokens += int(usage.get("completion_tokens", 0))
                cached_tokens += int(usage.get("cached_tokens", 0))
                n_completed_chunks += 1

        input_usd, output_usd, total_usd = self._usd_for(
            prompt_tokens,
            completion_tokens,
            cached_tokens,
            label=f"Partial stage {stage}",
        )

        n_jobs = state.get("n_jobs", 0)
        n_chunks = state.get("n_chunks", len(chunks))

        cost = StageCost(
            stage=stage,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            input_usd=input_usd,
            output_usd=output_usd,
            total_usd=total_usd,
            n_jobs=n_jobs,
            n_chunks=n_completed_chunks,
            n_chunks_planned=n_chunks,
        )
        self.partial_stages.append(cost)
        return cost

    def _pricing_block(self) -> dict[str, Any]:
        """The report's ``pricing`` block — the model that ran, and its rates.

        Before review F2 this read ``self.pricing["model"]`` off a table hard-wired
        to ``gpt-5-nano``, so the report asserted that model regardless of what had
        actually been submitted. It now names :attr:`model`, which is the id the
        run's batches carried.

        For an unpriced model the rate keys are ``None`` and ``priced`` is False.
        Omitting them instead would let a consumer's ``.get(key, 0)`` read a
        missing rate as a free one.
        """
        if self.pricing is None:
            return {
                "model": self.model,
                "priced": False,
                "batch_input_per_1m_usd": None,
                "batch_output_per_1m_usd": None,
                "batch_cached_input_per_1m_usd": None,
                "batch_line_is_estimate": None,
                "note": (
                    f"no rate row is registered for {self.model!r}; token counts "
                    f"are exact and every USD figure in this report is null. "
                    f"Add a row to g3o.common.pricing.PRICING to price this run."
                ),
            }
        return {
            "model": self.model,
            "priced": True,
            "batch_input_per_1m_usd": self.pricing["batch_input_per_1m_usd"],
            "batch_output_per_1m_usd": self.pricing["batch_output_per_1m_usd"],
            "batch_cached_input_per_1m_usd": self.pricing[
                "batch_cached_input_per_1m_usd"
            ],
            "batch_line_is_estimate": self.pricing["batch_line_is_estimate"],
        }

    def cost_report(self) -> dict[str, Any]:
        """Structured cost report for persistence and CLI output.

        Returns a dict with per-stage breakdowns and running totals. Suitable
        for JSON serialization and writing to ``_cost_report.json``.
        """
        total_prompt = sum(s.prompt_tokens for s in self.stages)
        total_completion = sum(s.completion_tokens for s in self.stages)
        total_cached = sum(s.cached_tokens for s in self.stages)
        # Compute totals from unrounded per-stage values, then round at
        # serialization time. This avoids the inconsistency where summing
        # rounded per-stage total_usd could diverge from
        # total_input_usd + total_output_usd.
        # Unpriced runs carry None through every USD slot rather than 0.0, so a
        # reader cannot mistake "we could not convert this to dollars" for "this
        # cost nothing" (review F2). The token totals above stay exact either way.
        raw_total_input = (
            sum(s.input_usd or 0.0 for s in self.stages) if self.is_priced else None
        )
        raw_total_output = (
            sum(s.output_usd or 0.0 for s in self.stages) if self.is_priced else None
        )
        raw_total_usd = (
            raw_total_input + raw_total_output
            if raw_total_input is not None and raw_total_output is not None
            else None
        )

        # Surface missing data as an accounting failure in the report.
        # If any stage has data_missing=True, the report flags it and
        # budget_exceeded is True (conservative: unknown cost is not safe).
        missing_stages = [s.stage for s in self.stages if s.data_missing]
        report: dict[str, Any] = {
            "budget_usd": self.budget_usd,
            "budget_exceeded": bool(
                self.budget_usd is not None
                and (
                    (raw_total_usd is not None and raw_total_usd > self.budget_usd)
                    or missing_stages
                )
            ),
            "data_missing_stages": missing_stages,
            "stages": [
                {
                    "stage": s.stage,
                    "prompt_tokens": s.prompt_tokens,
                    "completion_tokens": s.completion_tokens,
                    "cached_tokens": s.cached_tokens,
                    "input_usd": _round_usd(s.input_usd),
                    "output_usd": _round_usd(s.output_usd),
                    "total_usd": _round_usd(s.total_usd),
                    "n_jobs": s.n_jobs,
                    "n_chunks": s.n_chunks,
                    **({"data_missing": True} if s.data_missing else {}),
                }
                for s in self.stages
            ],
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_cached_tokens": total_cached,
            "total_input_usd": _round_usd(raw_total_input),
            "total_output_usd": _round_usd(raw_total_output),
            "total_usd": _round_usd(raw_total_usd),
            "pricing": self._pricing_block(),
        }
        # Include partial stages if any (diagnostic — not counted in totals)
        if self.partial_stages:
            report["partial_stages"] = [
                {
                    "stage": s.stage,
                    "prompt_tokens": s.prompt_tokens,
                    "completion_tokens": s.completion_tokens,
                    "cached_tokens": s.cached_tokens,
                    "input_usd": _round_usd(s.input_usd),
                    "output_usd": _round_usd(s.output_usd),
                    "total_usd": _round_usd(s.total_usd),
                    "n_jobs": s.n_jobs,
                    "n_chunks_completed": s.n_chunks,
                    "n_chunks_total": s.n_chunks_planned if s.n_chunks_planned is not None else s.n_chunks,
                }
                for s in self.partial_stages
            ]
        else:
            report["partial_stages"] = []
        return report


__all__ = [
    "BudgetExceededError",
    "CostMonitor",
    "ProjectedBudgetExceededError",
    "StageCost",
    "UnpricedModelError",
]
