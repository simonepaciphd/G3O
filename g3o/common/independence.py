"""Source independence groups for activity confidence (PI rulings A7.1 b, A7.2 a, 2026-11-11).

Signed rule: codebook ``items/core.confidence/rules/0`` (r2#27, codebook.yaml
L10917) -- "an activity is 'high' if one source is high or two medium sources
that are not copies of each other agree". The consumer is
:func:`g3o.validate.consolidate_v27.activity_confidence`, which counts distinct
independence-group ids among the medium sources.

PI rulings (``agent-workspace/2026-11-10-build/QUESTIONS-overnight.md`` A7):

- **A7.1 b: what counts as a copy.** Two sources are copies iff they share a
  ``core.syndication_group`` id (the P15 near-duplicate grouping,
  :mod:`g3o.common.syndication`, PI A4) **or** the same normalised URL.
- **A7.2 a: until A4 exists, keep refusing.** A source whose syndication group
  is not available (absent, empty, or a missing token) is refused with
  :class:`~g3o.common.source_fields.MissingUpstreamError`; there is no
  URL-only fallback.

Build choices (not ruled; pinned in :data:`INDEPENDENCE_VERSION`):

- **Transitive closure.** "Copy" is taken as an equivalence: the groups are the
  connected components of the graph whose edges are the two A7.1 b relations.
  So if S1 shares a syndication group with S2, and S2 shares a normalised URL
  with S3, then S1, S2 and S3 are one group even if S1 and S3 share neither key.
- **Normalised URL** is :func:`g3o.scrape.follow.same_url_key`, the repo's
  existing signed "same URL" key (RC-D-023 Q1 b = the discovery dedup key,
  Q3=c 2026-05-09: lower-case scheme and host, drop a leading ``www.``, strip a
  trailing slash, drop the fragment; query kept). Nothing new is invented here.
  The URL read is the source row's ``core.source_url`` (verbatim input URL).
  A source with no URL value is refused too (the rule's URL half cannot be
  evaluated; no default).
- **Scope** is the sources given (in Stage 6: all source rows of one
  institution, the injected seam's ``source id -> group`` shape; A4.2 a scopes
  syndication groups to one institution).
- **Group id.** ``"ig-" + BLAKE2b-80`` of canonical JSON
  ``[INDEPENDENCE_VERSION, sorted member source ids]``: independent of input
  and iteration order, so a resume over the same sources gives the same ids.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from g3o.common.source_fields import SYNDICATION, URL, MissingUpstreamError, SourceVocab, default_vocab

INDEPENDENCE_VERSION = "g3o.common.independence.v1"
RULING = "PI A7.1 b + A7.2 a (2026-11-11); codebook items/core.confidence/rules/0"
URL_KEY = "g3o.scrape.follow.same_url_key"
GROUP_ID_PREFIX = "ig-"
GROUP_ID_DIGEST_BYTES = 10
PRODUCER = ("source independence groups (A7.1 b) need each source's syndication group "
            "(P15 near-duplicate grouping, A4) and source URL")


def _url_key(url: str) -> str:
    from g3o.scrape.follow import same_url_key  # deferred: keeps this module import-light

    return same_url_key(url)


def group_id(member_ids: Any) -> str:
    doc = json.dumps([INDEPENDENCE_VERSION, sorted(member_ids)], ensure_ascii=True, separators=(",", ":"))
    return GROUP_ID_PREFIX + hashlib.blake2b(doc.encode("ascii"), digest_size=GROUP_ID_DIGEST_BYTES).hexdigest()


def _available(value: Any, missing: frozenset[str]) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value not in missing


def independence_groups(keys: Mapping[str, tuple[Any, Any]], *,
                        vocab: SourceVocab | None = None) -> dict[str, str]:
    """``source id -> independence group id`` from ``source id -> (syndication_group, source_url)``.

    Connected components of "shares a syndication group or a normalised URL"
    (A7.1 b, transitive closure). Refuses (A7.2 a) when any source lacks either key.
    """
    v = vocab or default_vocab()
    missing_tokens = frozenset(v.missing)
    ids = sorted(keys)
    absent = []
    for sid in ids:
        if not isinstance(sid, str) or not sid:
            raise ValueError(f"source id must be a non-empty string: {sid!r}")
        group, url = keys[sid]
        if not _available(group, missing_tokens):
            absent.append(f"{sid}.{SYNDICATION}")
        if not _available(url, missing_tokens):
            absent.append(f"{sid}.{URL}")
    if absent:
        raise MissingUpstreamError(PRODUCER, absent)
    parent = {s: s for s in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first_by_key: dict[tuple[str, str], str] = {}
    for sid in ids:
        group, url = keys[sid]
        for key in (("syndication", group), ("url", _url_key(url))):
            other = first_by_key.setdefault(key, sid)
            ra, rb = find(other), find(sid)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    comps: dict[str, list[str]] = {}
    for sid in ids:
        comps.setdefault(find(sid), []).append(sid)
    out: dict[str, str] = {}
    for members in comps.values():
        gid = group_id(members)
        for sid in members:
            out[sid] = gid
    return out


def independence_groups_for_sources(sources: Mapping[str, Mapping[str, Any]], *,
                                    vocab: SourceVocab | None = None) -> dict[str, str]:
    """:func:`independence_groups` over Stage 6 source rows (``values`` with X38 and X28 url)."""
    keys = {}
    for sid, row in sources.items():
        values = row.get("values") or {}
        keys[sid] = (values.get(SYNDICATION), values.get(URL))
    return independence_groups(keys, vocab=vocab)


__all__ = ["GROUP_ID_PREFIX", "INDEPENDENCE_VERSION", "PRODUCER", "RULING", "URL_KEY", "group_id",
           "independence_groups", "independence_groups_for_sources"]
