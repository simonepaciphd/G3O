"""The contract pin surface — one computation, two consumers.

``tests/goldens/contract_version_pin.json`` is the authority on which contract
version a run used (PI, 2026-08-11: "that file is the authority, not the prose").
Until now the *computation* behind it lived only in
``tests/test_contract_version_pin.py``, which was fine while the CI gate was its
only consumer.

The run manifest (Run API spec §4.1) has to record "the same pin PR #29 enforces",
and that phrase only stays true if there is one implementation. Two would drift —
and drift in this exact surface is what the pin exists to catch, so a second copy
of it is a self-defeating kind of duplication.

It also has to work from an installed wheel. Reading the golden JSON would not:
``tests/`` is not packaged, so a wheel-installed run would write a manifest with
no contract block and no error — provenance lost silently, which is the failure
mode this whole telemetry lane exists to remove. Everything hashed below is
either package code or packaged prompt assets, so this function works wherever the
pipeline runs.

The values are byte-identical to the golden by construction; the pin test asserts
exactly that by importing this module rather than re-deriving the surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal, get_args, get_origin

from g3o.common import contract as _contract
from g3o.common import schema as _schema
from g3o.common.contract import BatchResponse, ConsolidatedInstitutionResponse

#: Repo-relative paths, used verbatim as the manifest's ``contract.<name>.path``
#: so a reader can find the document without knowing this machine's layout.
EXTRACT_CONTRACT_REL = "g3o/extract/prompts/output_contract.md"
VALIDATE_CONTRACT_REL = "g3o/validate/prompts/output_contract.md"

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_CONTRACT = _PACKAGE_ROOT / "extract" / "prompts" / "output_contract.md"
VALIDATE_CONTRACT = _PACKAGE_ROOT / "validate" / "prompts" / "output_contract.md"

#: Column lists whose contents are part of the gated surface: a silent change to
#: any of them changes what a contract-conformant row may contain.
GATED_COLUMN_LISTS = (
    "DATA_COLUMNS",
    "ACTIVITY_COLUMNS",
    "ACTIVITY_SOURCE_COLUMNS",
    "SUMMARY_COLUMNS",
)


def parse_version(path: Path) -> str:
    """The version token out of a contract document's H1, e.g. ``v2.3``."""
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    match = re.search(r"\bv(\d+(?:\.\d+)*)\b", first_line)
    if not match:
        raise ValueError(
            f"no version token in the H1 of {path.name}: {first_line!r}"
        )
    return f"v{match.group(1)}"


def literal_enums() -> dict[str, list[str]]:
    """Every ``Literal`` alias in :mod:`g3o.common.contract`, discovered not listed.

    Discovery rather than enumeration on purpose: a new enum joins the pinned
    surface automatically, so adding one cannot slip past the gate by being
    forgotten in a list.
    """
    out: dict[str, list[str]] = {}
    for name, obj in vars(_contract).items():
        if name.startswith("_"):
            continue
        if get_origin(obj) is Literal:
            out[name] = [str(v) for v in get_args(obj)]
    if not out:
        raise RuntimeError("no Literal enum aliases found in g3o.common.contract")
    return dict(sorted(out.items()))


def gated_column_lists() -> dict[str, list[str]]:
    return {name: list(getattr(_schema, name)) for name in GATED_COLUMN_LISTS}


def _sha256_canonical(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def contract_surface() -> dict[str, dict[str, str]]:
    """``{extract, validate} -> {path, version, sha256}`` — the pinned surface.

    ``sha256`` covers the *machine-readable* surface (the schema actually sent as
    ``response_format``, the ``Literal`` enums, and — for extract — the gated
    column lists), **not** the document's own bytes. That distinction is load
    bearing in the manifest: a prose-only edit moves the ``prompts.*`` file hashes
    and leaves these hashes fixed, so a reader can tell a contract change from a
    wording change without diffing anything.
    """
    return {
        "extract": {
            "path": EXTRACT_CONTRACT_REL,
            "version": parse_version(EXTRACT_CONTRACT),
            "sha256": _sha256_canonical(
                {
                    "model_json_schema": BatchResponse.model_json_schema(),
                    "enums": literal_enums(),
                    "columns": gated_column_lists(),
                }
            ),
        },
        "validate": {
            "path": VALIDATE_CONTRACT_REL,
            "version": parse_version(VALIDATE_CONTRACT),
            "sha256": _sha256_canonical(
                {
                    "model_json_schema": ConsolidatedInstitutionResponse.model_json_schema(),
                    "enums": literal_enums(),
                }
            ),
        },
    }


__all__ = [
    "EXTRACT_CONTRACT",
    "EXTRACT_CONTRACT_REL",
    "GATED_COLUMN_LISTS",
    "VALIDATE_CONTRACT",
    "VALIDATE_CONTRACT_REL",
    "contract_surface",
    "gated_column_lists",
    "literal_enums",
    "parse_version",
]
