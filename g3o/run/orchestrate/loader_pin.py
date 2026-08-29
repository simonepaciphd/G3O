"""Which ``g3o-api`` commit is allowed to load a run. One line, one file.

``orchestrate ingest --expect-loader-sha`` is the only mechanical check that the
loader on the droplet is the loader we think it is, and until now it had no
source of truth: it is optional, so an omitted flag means the check silently does
not happen, and a *supplied* flag means whoever typed the command was the source
of truth. Neither survives being unattended.

So the expected sha lives here, in the repo, under review. ``--expect-loader-sha
pinned`` resolves to it, and the end-to-end runner always passes that. Changing
which loader may publish then requires a commit to this file, which is exactly
the visibility the check was supposed to provide.

Why a module constant rather than a data file: no package-data plumbing, it is
importable from anywhere the orchestrator runs, and a re-pin is a one-line diff
with a reviewable message.

**Re-pinning is a two-repo act.** The sha below and
:data:`g3o.run.orchestrate.ingest.LOADER_SUMMARY_RELPATH` describe the same
loader from two sides — which commit it is, and which artifact path it opens. A
re-pin that moves the loader's ``_SUMMARY_REL`` and not that constant produces a
checkout that passes this check and then reads a file Stage 7 never wrote. Move
them together.
"""

from __future__ import annotations

#: ``g3o-api`` ``main`` as of 2026-08-26 — "Merge sql/009: model the search
#: verdict (#17)". This is the checkout that loaded run
#: ``r20260824T215623Z-bb4e``, and the one the droplet at
#: ``/home/g3o/g3o-api`` was re-pinned to that morning (from ``9836a3d``). It is
#: the first loader that carries the #17 fix, so a run loaded by anything older
#: republishes ``(no, PROCESSING_FAILED)`` institutions as earned negatives —
#: 717 of them on that run alone.
EXPECTED_LOADER_SHA = "14e37cccf28b6afa29187f127d7ee12c5b8f0cd1"

#: What an operator types instead of the sha. Kept as a constant so the CLI help,
#: the resolver and the tests all name the same string.
PINNED_SENTINEL = "pinned"


def resolve_expected_sha(value: str | None) -> str | None:
    """``pinned`` → the sha above; anything else through unchanged.

    ``None`` stays ``None``: this function does not decide that the check is
    mandatory, it only gives the check somewhere to read its answer from. Which
    invocations must pass it is the caller's policy — the end-to-end runner
    requires it, a human running one leg by hand does not.
    """
    if value == PINNED_SENTINEL:
        return EXPECTED_LOADER_SHA
    return value


__all__ = ["EXPECTED_LOADER_SHA", "PINNED_SENTINEL", "resolve_expected_sha"]
