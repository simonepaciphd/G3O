"""Versioning *enforcement*: no machine-readable contract change ships under an
unchanged version header.

The failure this exists for is on the record. Commit ``25e544e`` (2026-07-04)
added ``proposed`` to the ``adoption_stage`` enum — a change to a controlled
vocabulary, which ``CONTRIBUTING.md`` says is versioned and needs maintainer
sign-off — and shipped it under an unchanged "v2.0" header. The frozen-goldens
suite did notice the contract text moved, but its remedy is *regenerate*, so a
regen commit carried the change through with the header untouched. Nothing tied
the content to the version.

This pins both together. ``tests/goldens/contract_version_pin.json`` records,
per contract, ``(version, sha256 of the machine-readable surface)``. A content
change with an unchanged version fails CI, and — the part that closes the
``25e544e`` hole — the regeneration path **refuses to write** in that case
rather than laundering it into the golden.

What "machine-readable surface" means here, deliberately narrower than the
whole document (prose edits to an edge-case narrative should not demand a
version bump; the frozen-goldens suite already catches those as instrument
changes):

- **Stage 5** — ``BatchResponse.model_json_schema()``, which is the schema
  generated into ``response_format`` and therefore the one the model is actually
  held to; every ``Literal`` enum alias as ``g3o.common.contract`` actually loads
  them; and the four sign-off-gated column lists named in ``CONTRIBUTING.md``.
  (Before v2.3 this was the §5 JSON Schema block parsed out of the markdown. §5
  was a second copy of the same schema, it drifted, and v2.3 deleted it.)
- **Stage 6** — ``ConsolidatedInstitutionResponse.model_json_schema()``, which
  the Validation Contract itself names as its source of truth, plus the same
  enum aliases.

Enum aliases are *discovered* (any ``Literal`` in the module), not listed, so a
new one is covered the day it is written rather than the day someone remembers
to add it here.

Deliberately **not** in scope: what the versioning rule should be — semver
semantics, a changelog, where the schema of record lives. Those are open
decisions. This test is compatible with any of them; it only requires that the
version string differ.

Regenerating, after the change is confirmed intended and recorded::

    G3O_REGEN_GOLDENS=1 python -m pytest tests/test_contract_version_pin.py

and commit ``tests/goldens/contract_version_pin.json`` alongside the change.
No network, no API keys.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

import pytest

from g3o.common import contract as _contract
from g3o.common import schema as _schema
from g3o.common.contract_pin import (
    EXTRACT_CONTRACT,
    VALIDATE_CONTRACT,
    contract_surface,
    gated_column_lists,
    literal_enums,
    parse_version,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PIN_PATH = Path(__file__).parent / "goldens" / "contract_version_pin.json"
REGEN_ENV = "G3O_REGEN_GOLDENS"

# Column lists CONTRIBUTING.md names as versioned + sign-off-gated alongside
# the contract itself.
_GATED_COLUMN_LISTS = (
    "DATA_COLUMNS",
    "ACTIVITY_COLUMNS",
    "ACTIVITY_SOURCE_COLUMNS",
    "SUMMARY_COLUMNS",
)

_SIGNOFF_POINTER = (
    "Changes to output_contract.md and the g3o.common.schema column lists are "
    "versioned and require maintainer sign-off (CONTRIBUTING.md, 'Schema "
    "stability'). Bump the version in the contract's H1 header in the same "
    "change, then regenerate this pin with G3O_REGEN_GOLDENS=1."
)


# ---------------------------------------------------------------------------
# Surface extraction
# ---------------------------------------------------------------------------


# The surface computation now lives in ``g3o.common.contract_pin`` so the run
# manifest (Run API spec §4.1) records the same pin this gate enforces. Two
# implementations of it would drift, and drift in this exact surface is what
# the pin exists to catch — so the test delegates rather than re-deriving.
_current = contract_surface
_parse_version = parse_version
_literal_enums = literal_enums
_gated_column_lists = gated_column_lists


def _no_embedded_json_schema(path: Path) -> None:
    """The extract contract must not regrow an embedded copy of the schema.

    Until v2.3 the Stage-5 surface was the document's own ```json block (§5). That
    block was a *second* definition of a schema the API already enforces, and it
    drifted: it self-titled "v2.0" until ``84d4493``, having survived the
    v2.0 → v2.1 bump unchanged. v2.3 deleted it and moved this pin onto
    ``BatchResponse.model_json_schema()`` — the schema actually sent — which makes
    the pin strictly harder to evade. This guard keeps the old failure mode from
    coming back by the same door.
    """
    blocks = re.findall(
        r"^```json\n(.*?)^```", path.read_text(encoding="utf-8"), re.S | re.M
    )
    assert not blocks, (
        f"{path.name} has regrown {len(blocks)} embedded ```json schema block(s). "
        "The schema of record is g3o.common.contract.BatchResponse, generated into "
        "response_format at request time; a prose copy can only drift from it "
        "(it already did once — see 84d4493)."
    )


# ---------------------------------------------------------------------------
# The pin, and the refusal that makes it enforcement rather than a golden
# ---------------------------------------------------------------------------


def _refusal(name: str, pinned: dict[str, str], current: dict[str, str]) -> str:
    return (
        f"{current['path']}: its machine-readable surface changed "
        f"({pinned['sha256'][:12]}… → {current['sha256'][:12]}…) but the version "
        f"header is still {current['version']}. {_SIGNOFF_POINTER}\n"
        f"(This is the {name} contract; the failure mode is commit 25e544e, "
        "which shipped an enum change under an unchanged v2.0.)"
    )


def _pin() -> dict[str, dict[str, str]]:
    if os.environ.get(REGEN_ENV):
        current = _current()
        if PIN_PATH.exists():
            previous = json.loads(PIN_PATH.read_text(encoding="utf-8"))
            blocked = [
                _refusal(name, previous[name], cur)
                for name, cur in current.items()
                if name in previous
                and previous[name]["sha256"] != cur["sha256"]
                and previous[name]["version"] == cur["version"]
            ]
            if blocked:
                raise AssertionError(
                    "refusing to regenerate the contract version pin:\n\n"
                    + "\n\n".join(blocked)
                )
        PIN_PATH.parent.mkdir(exist_ok=True)
        PIN_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pytest.skip(
            "contract version pin regenerated; review and commit "
            "tests/goldens/contract_version_pin.json alongside the change"
        )
    assert PIN_PATH.exists(), (
        f"pin file missing at {PIN_PATH}; regenerate deliberately with {REGEN_ENV}=1"
    )
    return json.loads(PIN_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


CONTRACTS = ("extract", "validate")


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_change_carries_a_version_bump(name: str):
    """The gate. Content moved + header did not ⇒ the sign-off gate was bypassed."""
    pinned, current = _pin()[name], _current()[name]
    if pinned["sha256"] == current["sha256"]:
        return
    assert pinned["version"] != current["version"], _refusal(name, pinned, current)
    pytest.fail(
        f"{current['path']} moved to {current['version']} — an intended change. "
        f"Regenerate the pin with {REGEN_ENV}=1 and commit it with the change."
    )


@pytest.mark.parametrize("name", CONTRACTS)
def test_contract_version_matches_its_pin(name: str):
    """A version bump with no content change is still a deliberate act and must
    be recorded, so the pin does not quietly fall behind the header."""
    pinned, current = _pin()[name], _current()[name]
    assert pinned["version"] == current["version"], (
        f"{current['path']} header is {current['version']}, pin says "
        f"{pinned['version']}. Regenerate with {REGEN_ENV}=1."
    )


def test_both_contracts_carry_a_parseable_version_header():
    assert _parse_version(EXTRACT_CONTRACT).startswith("v")
    assert _parse_version(VALIDATE_CONTRACT).startswith("v")


def test_extract_contract_has_no_embedded_json_schema():
    """v2.3 deleted §5. A prose copy of the schema can only drift from the
    generated one, and this one already did (`84d4493`)."""
    _no_embedded_json_schema(EXTRACT_CONTRACT)


def test_surface_is_stable_across_invocations():
    assert _current() == _current()


def test_the_pinned_surface_covers_the_enum_that_slipped_through():
    """``adoption_stage``'s ``proposed`` is the concrete value ``25e544e``
    shipped unversioned. If it ever stops being inside the hashed surface, this
    test is guarding nothing."""
    enums = _literal_enums()
    assert "proposed" in enums["AdoptionStage"]
    assert "AdoptionStage" in enums


def test_a_changed_enum_moves_the_hash(monkeypatch: pytest.MonkeyPatch):
    """Proves the hash is actually sensitive to the thing it claims to pin,
    rather than being a constant that happens to match."""
    before = _current()["extract"]["sha256"]
    monkeypatch.setattr(
        _contract,
        "AdoptionStage",
        Literal["proposed", "announced", "pilot", "production", "sunsetting"],
    )
    assert _current()["extract"]["sha256"] != before


def test_a_changed_column_list_moves_the_hash(monkeypatch: pytest.MonkeyPatch):
    before = _current()["extract"]["sha256"]
    monkeypatch.setattr(
        _schema, "ACTIVITY_SOURCE_COLUMNS", [*_schema.ACTIVITY_SOURCE_COLUMNS, "x"]
    )
    assert _current()["extract"]["sha256"] != before
