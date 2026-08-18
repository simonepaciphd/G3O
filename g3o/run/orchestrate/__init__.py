"""The run orchestrator — one program around ``launch()`` (Item 3).

``g3o.run.api.launch()`` runs a sweep. This package is everything that has to
happen *around* one so that a run can be started on a rented machine by someone
who then closes their laptop, and so that what comes out of it can be trusted:

======================  ====================================================
:mod:`.submit`          start a run that survives the shell that started it
:mod:`.status`          what a run is doing, from what it leaves on disk
:mod:`.ingest`          load a completed run, and report the loader honestly
:mod:`.archive_leg`     tar, hash, inventory, upload, verify after upload
:mod:`.publish`         ask the public API what it can see. Read-only.
:mod:`.cli`             ``python -m g3o.run.orchestrate <verb>``
======================  ====================================================

The runbook is ``docs/runbook-orchestrator.md``: the submit, status, and resume
one-liners, and the decommission section.

**One design rule runs through all of it.** The orchestrator decides nothing
about the measurement. It does not touch stage logic, prompts, contracts,
sampling, or spend policy; it does not re-implement minting, key resolution, or
the manifest; and it does not paraphrase another program's verdict. Where a
component downstream already has an opinion — ``launch()`` on how a run starts,
``g3o.run.archive`` on when a tar may replace a tree, ``ingest.py`` on whether a
load is green — that opinion is passed through, with its exit code, and the
orchestrator's contribution is to *gate* on it rather than to *summarise* it.

That rule is what makes the two negative guarantees hold without anyone
remembering them:

* a run that failed or was killed reaches a **named** state
  (:attr:`~g3o.run.orchestrate.status.RunStatus.is_failed`, which includes
  ``interrupted`` — the state of a run whose process is gone and which therefore
  never got to write ``run_failed``), and
* the ingest leg refuses every state but ``completed``, so **an induced failure
  publishes nothing** as a property of the code rather than of the operator.
"""

from g3o.run.orchestrate.status import (
    ORCHESTRATOR_DIRNAME,
    RunStatus,
    read_events,
    record_leg,
    run_status,
)

__all__ = [
    "ORCHESTRATOR_DIRNAME",
    "RunStatus",
    "read_events",
    "record_leg",
    "run_status",
]
