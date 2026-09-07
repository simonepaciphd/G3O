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

#: ``g3o-api`` ``main`` as of 2026-09-06 — "Merge pull request #38: the roster
#: check accepts the four-leg sub-steps by name". The first loader that can
#: ingest a four-leg run: ``r20260903T120740Z-362c`` (20,293 institutions,
#: COMPLETED 2026-09-05T20:12Z) was refused by the previous pin, ``14e37cc``,
#: on the three sub-step stage names its ``events.jsonl`` carries
#: (``discovery_general_fallback``, ``classify_official_site_fallback``,
#: ``discovery_evidence_open``). Nothing older than this sha can publish a
#: four-leg run; everything ``14e37cc`` carried (the #17 search-verdict fix,
#: without which ``(no, PROCESSING_FAILED)`` institutions republish as earned
#: negatives) is still in it. Re-pinned on the PI's "fix and publish".
EXPECTED_LOADER_SHA = "b39cc9fdeb545743e7710c1cc5f412e8b6e4a47f"

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
