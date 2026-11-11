"""Versioned archive-host list and the archive-address test (codebook core.source_type rules/0).

Rule 0 of ``core.source_type`` (codebook r15, L1580): "whether it is an archive
copy [is taken] from its address; pages typed that way are not asked". The host
list is the one the PI chose on 2026-11-11 (overnight question A2.1, option a,
RC-D-025 P15): ``web.archive.org`` / ``wayback.archive.org``, the archive.today
family (``archive.ph`` / ``.is`` / ``.today`` / ``.li`` / ``.md`` / ``.vn``) and
``webcache.googleusercontent.com``; exact host match, with the version recorded
in the run setup (the instrument payload's ``extractor_configuration``
``archive_host_list`` entry, written by
``g3o.run.presweep.instrument_binding``).

Host semantics (exact match):

- The host is :attr:`urllib.parse.SplitResult.hostname` of the URL: lowercased,
  userinfo and port dropped (a port is not part of the host), one trailing
  root dot dropped (``web.archive.org.`` is the same DNS name).
- **No ``www.`` stripping and no subdomain or suffix matching.** Only the hosts
  listed match; ``www.archive.ph`` or ``foo.web.archive.org`` do not. (This
  differs on purpose from :func:`g3o.common.urlnorm.site_host`, which drops
  ``www.`` for the official-domain comparison.)
- A URL with no host (scheme-less, unparseable) is refused, not guessed.

Changing the list is a new version: edit :data:`ARCHIVE_HOSTS`, bump
:data:`ARCHIVE_HOST_LIST_VERSION` and re-pin :data:`ARCHIVE_HOST_LIST_SHA256`;
the import-time guard refuses a list that drifted from its pinned hash.
"""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

#: Version of the archive-host list (PI ruling A2.1 a, 2026-11-11).
ARCHIVE_HOST_LIST_VERSION = "g3o.archive_hosts.v1"

#: The hosts, exact match (PI ruling A2.1 a, 2026-11-11).
ARCHIVE_HOSTS: frozenset[str] = frozenset({
    "web.archive.org",
    "wayback.archive.org",
    "archive.ph",
    "archive.is",
    "archive.today",
    "archive.li",
    "archive.md",
    "archive.vn",
    "webcache.googleusercontent.com",
})


def host_list_sha256(hosts: frozenset[str] = ARCHIVE_HOSTS) -> str:
    """SHA-256 of the sorted host list as compact JSON."""
    return hashlib.sha256(json.dumps(sorted(hosts), separators=(",", ":")).encode("utf-8")).hexdigest()


#: Pinned hash of :data:`ARCHIVE_HOSTS` for :data:`ARCHIVE_HOST_LIST_VERSION`.
ARCHIVE_HOST_LIST_SHA256 = "78f3a586bd519dd3484c14e850ef87ff828b06a0233145c18ec65c7058471eae"
if host_list_sha256() != ARCHIVE_HOST_LIST_SHA256:  # pragma: no cover - drift guard
    raise ImportError(f"archive host list differs from the pinned {ARCHIVE_HOST_LIST_VERSION}")


def archive_host(url: str) -> str:
    """The host compared against the list; ``ValueError`` when the URL has no host."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"source URL has no host: {url!r}")
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        host = None
    if host and host.endswith("."):
        host = host[:-1]
    if not host:
        raise ValueError(f"source URL has no host: {url!r}")
    return host


def is_archive_address(url: str) -> bool:
    """True when the URL's host is exactly one of :data:`ARCHIVE_HOSTS`."""
    return archive_host(url) in ARCHIVE_HOSTS


def setup_record() -> dict[str, object]:
    """What the run setup records about the list: version, hash and the hosts themselves."""
    return {"version": ARCHIVE_HOST_LIST_VERSION, "sha256": ARCHIVE_HOST_LIST_SHA256,
            "hosts": sorted(ARCHIVE_HOSTS)}


__all__ = ["ARCHIVE_HOSTS", "ARCHIVE_HOST_LIST_SHA256", "ARCHIVE_HOST_LIST_VERSION", "archive_host",
           "host_list_sha256", "is_archive_address", "setup_record"]
