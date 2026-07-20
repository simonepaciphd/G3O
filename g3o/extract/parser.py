"""Stage 5 result parser.

Takes a single ``BatchResult`` for one (institution × page) extraction job and
returns a validated ``BatchResponse``. Validation errors from
``g3o.common.contract`` are the line of defense — they are NOT caught here.

Per Q1 (2026-05-09, decision (a)): the scrape access date is injected into
the user message and the LLM is instructed to copy it verbatim into every
row's ``source_access_date``. This parser enforces the contract: if any row
disagrees with the supplied ``scrape_access_date``, the parser raises (no
silent overwrite). A parser-side failure here surfaces an LLM contract drift
that would otherwise corrupt provenance.

Group-D ``_NA_`` salvage: before validation, ``salvage_group_d_na`` repairs
``confirms_activity`` rows whose Group-D fields carry the illegal literal
``_NA_``, substituting the contract's prescribed defaults so a real positive
finding is not dropped over a schema imperfection (see ``salvage.py``). When a
``salvage_sink`` list is supplied, the parser appends one ``GroupDSalvage`` per
affected row so the caller can write attrition telemetry — including on the
failure path, since salvage runs (and populates the sink) before validation.
"""

from __future__ import annotations

import json

from g3o.common.batch_client import BatchResult
from g3o.common.contract import BatchResponse
from g3o.extract.salvage import GroupDSalvage, salvage_group_d_na


def parse_extract_result(
    result: BatchResult,
    *,
    scrape_access_date: str,
    salvage_sink: list[GroupDSalvage] | None = None,
) -> BatchResponse:
    """Parse a Stage 5 ``BatchResult`` into a validated ``BatchResponse``.

    Args:
        salvage_sink: if provided, ``GroupDSalvage`` records for every
            ``confirms_activity`` row with Group-D ``_NA_`` are appended to it
            (both repaired rows and unsalvageable ones). Populated before
            validation, so it is available to the caller even when this call
            raises.

    Raises:
        RuntimeError: if the underlying API call failed or returned no content.
        pydantic.ValidationError: on schema / cross-row validation failure.
        ValueError: if the LLM did not copy ``scrape_access_date`` verbatim
            into every row's ``source_access_date`` (Q1=a contract).
    """
    if not result.success:
        raise RuntimeError(
            f"Stage 5 batch result {result.custom_id!r} failed: {result.error}"
        )
    content = result.parsed_content
    if not content:
        raise RuntimeError(
            f"Stage 5 batch result {result.custom_id!r}: empty assistant content"
        )
    payload = json.loads(content)
    events = salvage_group_d_na(payload)
    if salvage_sink is not None:
        salvage_sink.extend(events)
    response = BatchResponse.model_validate(payload)

    # Q1=a: trust-the-input plus a hard verification that the LLM honored the
    # contract. Any divergence is treated as a parse failure rather than
    # silently overwritten — the researcher can revisit Q1 if drift is
    # observed in practice.
    bad_rows = [
        r for r in response.data if r.source_access_date != scrape_access_date
    ]
    if bad_rows:
        offending_urls = sorted({r.source_url for r in bad_rows})
        offending_dates = sorted({r.source_access_date for r in bad_rows})
        raise ValueError(
            f"Stage 5 result {result.custom_id!r}: "
            f"{len(bad_rows)} row(s) emitted source_access_date "
            f"{offending_dates} but scrape supplied {scrape_access_date!r}; "
            f"affected source_url(s): {offending_urls}"
        )

    return response


__all__ = ["parse_extract_result", "GroupDSalvage", "salvage_group_d_na"]
