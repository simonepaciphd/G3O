"""Wave frame construction — which institutions the next sweep will look at.

Before this module a frame was a one-off script written per wave and kept outside
the repository. The published wave's frame *is* reproducible — ``build_run_frame.py``
and ``subset_frame.py`` under ``agent-workspace/2026-08-24-pipeline-launch/`` built
``run-frame-n5000.csv`` at seed 22294 and split it into the n=1,000 pilot and its
n=4,000 complement, each with a sha256 report beside it — but the provenance lives
in a dated scratch folder on Drive rather than in the pipeline, it is untested, and
the complement's own report does not record the seed that produced it.

Everything here exists to make the frame a pipeline step instead: a pure function of
``(master csv, inspection snapshot, seed, size)``, tested, with the sidecar recording
all four alongside the sha256 of what came out.

The draw is two-tiered (PI ruling, 2026-08-26):

* **tier 1 — never inspected**, drawn uniformly, which makes the frame
  *proportional to the master* rather than stratified. That is the ruled
  composition and it is deliberately not comparable to the published wave.
* **tier 2 — previously inspected**, weighted by distance from the last
  inspection, and reached only when tier 1 cannot fill the request.

At the present ratio (715,977 never-inspected of 719,588) tier 1 alone supplies
every draw for roughly the next 71 waves at n=10,000, so tier 2 is written but
unexercised. See :func:`g3o.run.frame.sampler.draw_recency_weighted`.
"""

from __future__ import annotations

from g3o.run.frame.build import (
    FrameBuildResult,
    build_frame,
    build_stratified_frame,
    classify_master_cells,
    sidecar_path_for,
    subset_frame,
)
from g3o.run.frame.inspection import (
    InspectionSnapshot,
    last_inspected_at,
    read_snapshot_csv,
    read_sweeps_csv,
    snapshot_from_dsn,
    write_snapshot_csv,
)
from g3o.run.frame.quota import (
    StratumSpec,
    allocate_level,
    allocate_stratum,
    draw_plan,
    level_targets,
)
from g3o.run.frame.sampler import (
    FrameError,
    draw_recency_weighted,
    draw_uniform,
    has_colliding_name,
    is_eligible,
)

__all__ = [
    "FrameBuildResult",
    "FrameError",
    "InspectionSnapshot",
    "StratumSpec",
    "allocate_level",
    "allocate_stratum",
    "build_frame",
    "build_stratified_frame",
    "classify_master_cells",
    "draw_plan",
    "level_targets",
    "draw_recency_weighted",
    "draw_uniform",
    "has_colliding_name",
    "is_eligible",
    "last_inspected_at",
    "read_snapshot_csv",
    "read_sweeps_csv",
    "sidecar_path_for",
    "snapshot_from_dsn",
    "subset_frame",
    "write_snapshot_csv",
]
