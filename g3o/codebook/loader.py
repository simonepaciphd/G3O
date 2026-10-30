"""Load the codebook of record and expose its parts (T-013).

The loader is read-only. It hashes the file bytes exactly as stored (the signed
file is CRLF and ``-text`` in git, so the bytes on disk are the signed bytes),
parses the YAML, and gives the generators and checks one place to resolve
items, slots and shared-rule references.

Hash conventions (A-001):

- **Release hash**: sha256 of the codebook file bytes (item-template §1, check 15).
- **Item hash**: sha256 of the item's canonical JSON form (keys sorted, UTF-8,
  no insignificant whitespace). It changes whenever any field of the item
  changes, wording included, and it does not depend on YAML layout. Every
  generated question, prompt section and enum carries it (check 6).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CODEBOOK = REPO_ROOT / "codebook" / "codebook.yaml"

#: The template's explicit "does not apply" value (item-template §2).
NONE = "none"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """The canonical JSON form used for item hashes."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class Slot:
    """One signed text slot, addressed by its path in the codebook."""

    path: str
    text: str


@dataclass(frozen=True)
class RuleText:
    """One rule text applied to an item: its own slot or an expanded shared rule."""

    path: str
    text: str
    shared_rule: str | None = None


class Codebook:
    """A parsed codebook file plus its hashes."""

    def __init__(self, raw: bytes, path: Path | None = None) -> None:
        self.raw = raw
        self.path = path
        self.sha256 = sha256_bytes(raw)
        self.data: dict[str, Any] = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(self.data, dict):
            raise ValueError("codebook root must be a mapping")

    # -- top-level parts -------------------------------------------------
    @property
    def release(self) -> dict[str, Any]:
        return self.data.get("release") or {}

    @property
    def label(self) -> str:
        return str(self.release.get("label"))

    @property
    def vocabularies(self) -> dict[str, Any]:
        return self.data.get("vocabularies") or {}

    @property
    def shared_rules(self) -> dict[str, Any]:
        return self.data.get("shared_rules") or {}

    @property
    def combining_conventions(self) -> dict[str, Any]:
        return self.data.get("combining_conventions") or {}

    @property
    def items(self) -> dict[str, dict[str, Any]]:
        return self.data.get("items") or {}

    @property
    def retired(self) -> list[Any]:
        return self.data.get("retired") or []

    def vocab_values(self, name: str) -> list[str]:
        vocab = self.vocabularies.get(name) or {}
        values = vocab.get("values") if isinstance(vocab, dict) else None
        return [str(v) for v in values] if isinstance(values, list) else []

    # -- scope -----------------------------------------------------------
    @property
    def build_scope(self) -> list[str]:
        """Namespaces in this release's build (release.build_scope_v<label>)."""
        key = "build_scope_v" + self.label.replace(".", "_")
        scope = self.release.get(key)
        if scope is None:
            return [str(n) for n in self.release.get("namespaces") or []]
        return [str(scope)] if isinstance(scope, str) else [str(s) for s in scope]

    def in_build_scope(self, item_id: str) -> bool:
        return item_id.split(".", 1)[0] in self.build_scope

    def build_items(self) -> dict[str, dict[str, Any]]:
        return {k: v for k, v in self.items.items() if self.in_build_scope(k)}

    # -- hashes ----------------------------------------------------------
    def item_hash(self, item_id: str) -> str:
        return sha256_bytes(canonical_json(self.items[item_id]).encode("utf-8"))

    # -- slots -----------------------------------------------------------
    @staticmethod
    def slot_text(slot: Any) -> str | None:
        """The ``text`` of a slot mapping, or None when the value is not a slot."""
        if isinstance(slot, dict) and isinstance(slot.get("text"), str):
            return slot["text"]
        return None

    def instruction(self, item_id: str) -> Slot | None:
        text = self.slot_text(self.items[item_id].get("instruction"))
        return None if text is None else Slot(f"items/{item_id}/instruction", text)

    def value_list(self, item_id: str) -> list[dict[str, Any]] | None:
        """The item's values when they are the template's ordered list of
        ``{code, definition}`` mappings; None otherwise."""
        values = self.items[item_id].get("values")
        if not isinstance(values, list):
            return None
        if not all(isinstance(v, dict) and "code" in v for v in values):
            return None
        return values

    def definition(self, item_id: str, index: int) -> Slot | None:
        values = self.value_list(item_id) or []
        text = self.slot_text(values[index].get("definition"))
        return None if text is None else Slot(f"items/{item_id}/values/{index}/definition", text)

    def shared_rule_texts(self, rule_id: str) -> list[RuleText]:
        entry = self.shared_rules.get(rule_id)
        slots = entry if isinstance(entry, list) else [entry]
        out: list[RuleText] = []
        for n, slot in enumerate(slots):
            text = self.slot_text(slot)
            if text is not None:
                out.append(RuleText(f"shared_rules/{rule_id}/{n}", text, rule_id))
        return out

    def rule_texts(self, item_id: str) -> list[RuleText]:
        """The item's full rule set, in file order: own rule slots and every
        shared rule it references, expanded verbatim (check 16)."""
        rules = self.items[item_id].get("rules")
        if not isinstance(rules, list):
            return []
        out: list[RuleText] = []
        for n, rule in enumerate(rules):
            if isinstance(rule, str):
                out.extend(self.shared_rule_texts(rule))
                continue
            text = self.slot_text(rule)
            if text is not None:
                out.append(RuleText(f"items/{item_id}/rules/{n}", text))
        return out

    def rule_slots_without_text(self, item_id: str) -> list[str]:
        """Paths of rule entries that are neither a shared-rule id nor a slot
        with ``text`` (they cannot be assembled verbatim)."""
        rules = self.items[item_id].get("rules")
        if not isinstance(rules, list):
            return []
        return [
            f"items/{item_id}/rules/{n}"
            for n, rule in enumerate(rules)
            if not isinstance(rule, str) and self.slot_text(rule) is None
        ]


def load_codebook(path: Path | str | None = None) -> Codebook:
    """Read and parse the codebook file (bytes as stored; no newline conversion)."""
    p = Path(path) if path is not None else DEFAULT_CODEBOOK
    return Codebook(p.read_bytes(), p)
