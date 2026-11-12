"""P15 near-duplicate (syndication) grouping within one institution (PI rulings A4.1 a, A4.2 a, 2026-11-11).

Signed rule: codebook ``items/core.syndication_group/rules/0`` -- "Deterministic
near-duplicate hash (e.g. shingled MinHash on normalised text) per page;
``syndication_group`` id; QC flag when codes differ within a group."

PI rulings (2026-11-11):

- A4.1 a: in-house seeded MinHash; 5-word shingles on lower-cased,
  whitespace-collapsed main text; Jaccard >= 0.8; connected components.
- A4.2 a: scope is one institution; stable on resume.
- A4 ruling 7 (procedural): pair edges by exact shingle-set Jaccard >= 0.8;
  the MinHash signature is stored per page.

Build parameters (not ruled; pinned here, all in :data:`SYNDICATION_VERSION`):

- **Main text only.** The input is ``RenderedPage.text``; ``chrome_text`` is never read.
- **Normalisation.** ``str.lower()`` then ``str.split()`` (any run of whitespace is
  one separator; leading/trailing whitespace dropped). Nothing else (no Unicode
  normalisation, no punctuation stripping): the ruling names only these two steps.
- **Shingles.** Every window of :data:`SHINGLE_WORDS` consecutive words, joined
  by one space; a page's shingle *set* (duplicates collapse).
- **Edge decision: exact Jaccard on shingle sets**, not the MinHash estimate.
  Pages per institution are few (preflight assumes ~12 kept URLs), so exact
  pairwise set Jaccard is cheap and has no estimation error at the threshold.
  The comparison is integer-only: ``|A & B| * DEN >= |A | B| * NUM`` with
  ``NUM/DEN`` = :data:`JACCARD_NUM` / :data:`JACCARD_DEN` = 4/5, so the result
  is byte-stable (no float rounding). Pairs whose set sizes alone rule out
  J >= 0.8 (``min/max < 0.8``, an exact bound) are skipped without intersecting.
- **The per-page hash** is a seeded MinHash signature (:data:`NUM_PERM`
  permutations ``(a*h + b) mod (2**61 - 1)`` over a keyed 64-bit BLAKE2b of each
  shingle; ``a``/``b`` derived from :data:`SEED` by BLAKE2b). It is the
  codebook's "near-duplicate hash per page". The full signature (all
  :data:`NUM_PERM` values) is stored per page (A4 ruling 7) in
  :attr:`PageFingerprint.signature` and in :meth:`SyndicationGrouping.detail`,
  with ``signature_sha`` (BLAKE2b of the signature) as a short digest; it does
  not decide edges.
  Python's built-in ``hash()`` is never used.
- **Short pages.** A page with fewer than :data:`SHINGLE_WORDS` words has no
  shingle, so its Jaccard with any page is undefined. Policy
  :data:`SHORT_PAGE_POLICY`: it links to no page, gets its own singleton group,
  and is listed in :attr:`SyndicationGrouping.short_pages` (never silent).
- **Group id.** ``"sg-" + BLAKE2b-80`` of canonical JSON
  ``[SYNDICATION_VERSION, institution_id, sorted member page keys]``: independent
  of input and iteration order, so a resume over the same page set gives the same
  ids; the institution id (required, A4.2 a: one grouping per institution) keeps
  two institutions from ever sharing an ``sg-`` id, even for equal page keys.
  Singletons get their own id the same way. If the page set of a group changes
  (a page added or dropped), its id changes; that is by construction.

Portability note: ``str.lower`` / ``str.split`` follow the interpreter's Unicode
database; :func:`group_pages` records ``unicodedata.unidata_version`` so a
cross-version difference (only for characters whose case or whitespace class
changed between Unicode releases) is visible.

Not built here: the rule's "QC flag when codes differ within a group" (needs the
coded values; a follow-up) and source independence groups (A7).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SYNDICATION_VERSION = "g3o.common.syndication.v2"
RULING = "PI A4.1 a + A4.2 a + A4 ruling 7 (2026-11-11); codebook items/core.syndication_group/rules/0"

SHINGLE_WORDS = 5
JACCARD_NUM = 4  # threshold 0.8 = 4/5, compared in integers
JACCARD_DEN = 5
JACCARD_THRESHOLD = "0.8"  # display only; the decision uses JACCARD_NUM / JACCARD_DEN
EDGE_DECISION = "exact_shingle_set_jaccard"
NUM_PERM = 128
SEED = "g3o-syndication-minhash-v1"
MERSENNE_61 = (1 << 61) - 1
SHORT_PAGE_POLICY = "singleton_flagged"
GROUP_ID_PREFIX = "sg-"
GROUP_ID_DIGEST_BYTES = 10

_SEED_KEY = hashlib.blake2b(SEED.encode("utf-8"), digest_size=32).digest()


def _u64(data: bytes, key: bytes = _SEED_KEY) -> int:
    return int.from_bytes(hashlib.blake2b(data, digest_size=8, key=key).digest(), "big")


def _perm_coeffs() -> tuple[tuple[int, int], ...]:
    out = []
    for i in range(NUM_PERM):
        a = _u64(f"a:{i}".encode("ascii")) % (MERSENNE_61 - 1) + 1  # a in [1, p-1]
        b = _u64(f"b:{i}".encode("ascii")) % MERSENNE_61
        out.append((a, b))
    return tuple(out)


_PERMS = _perm_coeffs()


def normalised_words(text: str) -> list[str]:
    """Lower-cased, whitespace-collapsed words of a page's main text."""
    return text.lower().split()


def shingles(text: str) -> frozenset[str]:
    """The set of 5-word shingles; empty for a page with fewer than 5 words."""
    w = normalised_words(text)
    return frozenset(" ".join(w[i:i + SHINGLE_WORDS]) for i in range(len(w) - SHINGLE_WORDS + 1))


def minhash_signature(shingle_set: frozenset[str]) -> tuple[int, ...] | None:
    """Seeded MinHash signature (NUM_PERM values); ``None`` for an empty shingle set."""
    if not shingle_set:
        return None
    hs = [_u64(s.encode("utf-8")) for s in shingle_set]
    return tuple(min((a * h + b) % MERSENNE_61 for h in hs) for a, b in _PERMS)


def signature_sha(sig: tuple[int, ...] | None) -> str | None:
    if sig is None:
        return None
    raw = b"".join(v.to_bytes(8, "big") for v in sig)
    return hashlib.blake2b(raw, digest_size=16).hexdigest()


def jaccard_at_least_threshold(a: frozenset[str], b: frozenset[str]) -> bool:
    """Exact ``J(a, b) >= 0.8`` in integers; False when either set is empty."""
    if not a or not b:
        return False
    small, large = sorted((len(a), len(b)))
    if small * JACCARD_DEN < large * JACCARD_NUM:  # J <= small/large < 0.8
        return False
    inter = len(a & b)
    union = len(a) + len(b) - inter
    return inter * JACCARD_DEN >= union * JACCARD_NUM


def _check_institution_id(institution_id: Any) -> str:
    if not isinstance(institution_id, str) or not institution_id.strip():
        raise ValueError(f"institution_id must be a non-empty string: {institution_id!r}")
    return institution_id


def group_id(institution_id: str, member_keys: Any) -> str:
    """``sg-`` id of one institution's group; the institution id is part of the hash."""
    inst = _check_institution_id(institution_id)
    keys = sorted(member_keys)
    doc = json.dumps([SYNDICATION_VERSION, inst, keys], ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.blake2b(doc.encode("ascii"), digest_size=GROUP_ID_DIGEST_BYTES).hexdigest()
    return GROUP_ID_PREFIX + digest


@dataclass(frozen=True)
class PageFingerprint:
    page_key: str
    n_words: int
    n_shingles: int
    short: bool
    signature: tuple[int, ...] | None  # full NUM_PERM-value MinHash signature (A4 ruling 7)
    signature_sha: str | None


@dataclass(frozen=True)
class SyndicationGrouping:
    """One institution's near-duplicate grouping."""

    version: str
    unidata_version: str
    institution_id: str
    groups: Mapping[str, str]  # page key -> group id
    members: Mapping[str, tuple[str, ...]]  # group id -> sorted page keys
    edges: tuple[tuple[str, str], ...]  # sorted pairs with J >= 0.8
    short_pages: tuple[str, ...]  # sorted keys under SHORT_PAGE_POLICY
    pages: Mapping[str, PageFingerprint]

    def group_of(self, page_key: str) -> str:
        if page_key not in self.groups:
            raise KeyError(f"page {page_key!r} was not grouped")
        return self.groups[page_key]

    def detail(self, page_key: str) -> dict[str, Any]:
        gid = self.group_of(page_key)
        fp = self.pages[page_key]
        return {"version": self.version, "unidata_version": self.unidata_version,
                "institution_id": self.institution_id, "edge_decision": EDGE_DECISION, "members": list(self.members[gid]),
                "short_page": fp.short, "short_page_policy": SHORT_PAGE_POLICY if fp.short else None,
                "signature": None if fp.signature is None else list(fp.signature),
                "signature_sha": fp.signature_sha, "n_shingles": fp.n_shingles}


def group_pages(texts: Mapping[str, str], *, institution_id: str) -> SyndicationGrouping:
    """Group one institution's pages (page key -> main text) into near-duplicate components.

    ``institution_id`` is required (A4.2 a: the scope is one institution) and is
    hashed into every group id.
    """
    inst = _check_institution_id(institution_id)
    keys = sorted(texts)
    for k in keys:
        if not isinstance(k, str) or not k:
            raise ValueError(f"page key must be a non-empty string: {k!r}")
        if not isinstance(texts[k], str):
            raise TypeError(f"page {k!r}: main text must be a string (RenderedPage.text)")
    sets = {k: shingles(texts[k]) for k in keys}
    pages = {}
    for k in keys:
        n_words = len(normalised_words(texts[k]))
        sig = minhash_signature(sets[k])
        pages[k] = PageFingerprint(k, n_words, len(sets[k]), n_words < SHINGLE_WORDS,
                                   sig, signature_sha(sig))
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if jaccard_at_least_threshold(sets[a], sets[b]):
                edges.append((a, b))
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    comps: dict[str, list[str]] = {}
    for k in keys:
        comps.setdefault(find(k), []).append(k)
    groups: dict[str, str] = {}
    members: dict[str, tuple[str, ...]] = {}
    for comp in comps.values():
        gid = group_id(inst, comp)
        members[gid] = tuple(sorted(comp))
        for k in comp:
            groups[k] = gid
    return SyndicationGrouping(SYNDICATION_VERSION, unicodedata.unidata_version, inst, groups, members,
                               tuple(edges), tuple(k for k in keys if pages[k].short), pages)


def group_rendered_pages(pages: Mapping[str, Any], *, institution_id: str) -> SyndicationGrouping:
    """:func:`group_pages` over ``RenderedPage``-like objects: reads ``.text`` only, never ``chrome_text``."""
    return group_pages({k: p.text for k, p in pages.items()}, institution_id=institution_id)


__all__ = [
    "EDGE_DECISION", "GROUP_ID_PREFIX", "JACCARD_DEN", "JACCARD_NUM", "JACCARD_THRESHOLD", "NUM_PERM",
    "RULING", "SEED", "SHINGLE_WORDS", "SHORT_PAGE_POLICY", "SYNDICATION_VERSION", "PageFingerprint",
    "SyndicationGrouping", "group_id", "group_pages", "group_rendered_pages", "jaccard_at_least_threshold",
    "minhash_signature", "normalised_words", "shingles", "signature_sha",
]
