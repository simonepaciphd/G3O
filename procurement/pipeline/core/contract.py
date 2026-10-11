"""G3O output contract v2.0 — controlled vocabularies, copied verbatim.

**This module contains no decisions.** Every value below is transcribed from
`docs/reference/output_contract_v2.0.SNAPSHOT.md`, which is itself a snapshot of
the root instrument at `C:\\Users\\spaci\\repos\\G3O\\g3o\\extract\\prompts\\output_contract.md`.
Nothing here may be extended, renamed, or "improved" — the contract owns these
strings and says: "Every enum field uses ONLY values from the allowed set. No
variations, no capitalization changes, no synonyms" (§6, check 8).

It exists so the rest of the pipeline never retypes an enum from memory. When
the root instrument is revised: re-pin the snapshot, update this file from it,
and run the tests — `tests/test_core.py` asserts these constants still match the
snapshot on disk.

Field numbers in comments are the contract's own column numbers.
"""

from __future__ import annotations

CONTRACT_VERSION = "2.0"

# --------------------------------------------------------------------------- #
# Group C / D / E enums the procurement channel touches
# --------------------------------------------------------------------------- #

# Column 8 — INSTITUTION-LEVEL verdict. "Same value on every row for the same
# institution." It is therefore NOT derivable from a single procurement record.
HAS_GENAI_ACTIVITY = ("yes", "no", "unclear")

# Column 12 — the G3O activity typology. Per the PI ruling of 2026-07-28 this is
# what the procurement schema's `genai_category` takes; there is no
# procurement-specific taxonomy.
ACTIVITY_TYPE = (
    "policy_guidance",
    "pilot_experiment",
    "program_initiative",
    "internal_operational",
    "public_facing_service",
    "_NA_",
)

# Column 13 — an AWARD codes `announced`, dated by contract date (spec §6.1).
# A TENDER-only record codes `proposed`, dated by publication (ruling D2/D3,
# 2026-08-04, overriding the spec §6.2 default) — see pipeline/core/coding.py.
ADOPTION_STAGE = (
    "proposed",
    "announced",
    "pilot",
    "production",
    "discontinued",
    "unknown",
    "_NA_",
)

# Column 33 — the procurement channel's source category.
SOURCE_TYPE = (
    "official_gov",
    "procurement_tender",
    "news_major",
    "news_trade",
    "vendor",
    "academic",
    "policy_org",
    "social_media",
    "archive",
    "other",
)
PROCUREMENT_SOURCE_TYPE = "procurement_tender"

# Column 36 — PER-SOURCE evidence value. Unlike column 8 this IS assessable from
# one source: contract Edge Case A codes a supplied page with no GenAI mention
# as `confirms_absence` on that row.
GENAI_EVIDENCE = ("confirms_activity", "confirms_absence", "ambiguous", "background_only")

# Column 39 — closed vocabulary. "Use these exact strings."
UNCERTAINTY_FLAGS = (
    "stage_ambiguous",
    "genai_vs_traditional_ai",
    "institution_attribution",
    "date_uncertain",
    "source_language_barrier",
    "vendor_undisclosed",
    "discontinued_uncertain",
    "scope_unclear",
)

# --------------------------------------------------------------------------- #
# Missing-data discipline
# --------------------------------------------------------------------------- #

# §1: "Never emit null or an empty string." §6 check 2: on a `confirms_activity`
# row NO Group D column may be `_NA_` — use these instead.
NOT_APPLICABLE = "_NA_"
PRESCRIBED_DEFAULTS = ("unknown", "none", "none_reported", "not_documented")

# Columns 11–28. On any row whose `genai_evidence` is confirms_absence /
# ambiguous / background_only, every one of these is `_NA_`.
GROUP_D_FIELDS = (
    "activity_name", "activity_type", "adoption_stage", "access_type",
    "interaction_type", "tool_name", "vendor", "deployment_mode", "target_users",
    "year_announced", "year_deployed", "has_human_oversight",
    "has_transparency_notice", "has_data_classification", "has_risk_assessment",
    "reported_outcomes", "reported_incidents", "scope_notes",
)

SOURCE_SNIPPET_MAX_CHARS = 300      # Column 37
