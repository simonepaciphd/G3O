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
#: lookup sentence moved to ``release.r16_dropped``; then (2026-11-16 late evening) the rules/0 trim ("from lookup
#: or page" -> "stated on the page" in core.contracting_party, core.developer, core.developer_basis), Q185 a (new
#: core.developer_basis rules/2 and rules/3, core.stage_as_of_basis rules/1), Q186 a and Q187 a (the "same five
#: values" sentence of core.developer_basis rules/1 and of vocabularies.provenance text moved to r16_dropped).
R16_CANDIDATE_SHA256 = "381e41f8144bb68066c50fcf0241327943a9840f90a6239b9d8eabc0de881b8a"

#: Codebook r17 (calibration rulings 2026-11-21: the construct is AI adoption; byte edits to the signed
#: r16 file, ``planning/t010/r17-provenance.json``). It keeps every r16 field, so the r16 producers stay on under
#: it. Signed when ``planning/t010/signoff-record.md`` holds this SHA256; the name keeps the word candidate.
R17_CANDIDATE_SHA256 = "02ece40474bc78708df1451dad7e3c624549bfbafb5c1871afea8ac0bdec861b"

#: The releases that carry the r16 fields: r16 and the revisions built on it.
R16_FIELD_RELEASES = (R16_CANDIDATE_SHA256, R17_CANDIDATE_SHA256)

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
    """True only when the codebook in use carries the r16 fields (:data:`R16_FIELD_RELEASES`: r16 or the r17
    candidate built on it). False under r15."""
    return active_codebook_sha256() in R16_FIELD_RELEASES


__all__ = ["DEVELOPER_BASIS_STATED", "R16_CANDIDATE_SHA256", "R16_FIELD_RELEASES", "R17_CANDIDATE_SHA256",
           "STAGE_AS_OF_BASIS_CODES", "active_codebook_sha256", "r16_active"]
