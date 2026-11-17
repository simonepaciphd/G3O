"""The UNSIGNED codebook r16 candidate pin (RC-D-034; QUESTIONS-overnight A8.1 a, A8.5 a; PI ruling 140).

PI ruling 140 (2026-11-16, "all as rec"): code that unblocks the r16 fields is built against the
draft. The active, signed codebook stays r15 (``ca1bf616...``): this module is the one switch. The
r16 producers (``core.developer`` as a quote-step item, ``core.developer_basis``,
``core.stage_as_of_basis`` with three step codes) run only when the codebook the generated files
were built from (:data:`g3o.codebook.generated.enums.CODEBOOK_SHA256`, and the same pin in
:mod:`g3o.common.storage_fields`, whose FIELDS the producers validate against) is the candidate
below. Under r15 :func:`r16_active` is False and every refusal list keeps its r15 contents.

The candidate is built against, not signed. Signing r16 means regenerating every generated file
from the signed bytes; if the PI amends the candidate, its SHA256 changes and this pin must follow.
"""
from __future__ import annotations

#: UNSIGNED r16 candidate (RC-D-034 A8.1 a / A8.5 a): built against, not signed. SHA256 of
#: ``agent-workspace/2026-11-16-overnight/governance/codebook-r16-candidate/codebook.yaml`` (CRLF bytes, as r15;
#: the test fixture copy is committed ``-text``), amended for PI Q167 a (2026-11-16): core.developer rules/1's
#: lookup sentence moved to ``release.r16_dropped``.
R16_CANDIDATE_SHA256 = "e049d1a2d96ae786cf1f9adac2a023e2a3b318fdccbcd8541b214b7e67cfac9a"

#: The three ``core.stage_as_of_basis`` step codes of the candidate (``items/core.stage_as_of_basis/values``,
#: A8.5 a), in candidate order. Equal to the step names of :mod:`g3o.validate.merged_activity_v27`.
STAGE_AS_OF_BASIS_CODES = ("publication", "stated", "access")
#: ``items/core.developer/rules/3`` of the candidate (A8.1 a): a page-stated developer has ``developer_basis`` =
#: ``stated``. A8.2 a: no lookup table in the first run, so ``looked_up`` is never set.
DEVELOPER_BASIS_STATED = "stated"


def active_codebook_sha256() -> str:
    """The SHA256 of the codebook the generated files in use were built from.

    The generated enums and the generated storage FIELDS must carry the same pin; a mismatch is a
    half-regenerated tree (a wiring error), never an r16 switch.
    """
    from g3o.codebook.generated import enums
    from g3o.common import storage_fields

    if enums.CODEBOOK_SHA256 != storage_fields.CODEBOOK_SHA256:  # pragma: no cover - regeneration drift
        raise RuntimeError(f"generated enums pin {enums.CODEBOOK_SHA256} differs from storage_fields pin "
                           f"{storage_fields.CODEBOOK_SHA256}: regenerate both from one codebook")
    return enums.CODEBOOK_SHA256


def r16_active() -> bool:
    """True only when the codebook in use is the r16 candidate (:data:`R16_CANDIDATE_SHA256`). False under r15."""
    return active_codebook_sha256() == R16_CANDIDATE_SHA256


__all__ = ["DEVELOPER_BASIS_STATED", "R16_CANDIDATE_SHA256", "STAGE_AS_OF_BASIS_CODES", "active_codebook_sha256",
           "r16_active"]
