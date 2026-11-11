"""Versioned archive-host list and the archive-address test (codebook core.source_type rules/0).

Rule 0 of ``core.source_type`` (codebook r15, L1580): "whether it is an archive
copy [is taken] from its address; pages typed that way are not asked". The host
list is the one the PI chose on 2026-11-11 (overnight question A2.1, option a,
RC-D-025 P15): ``web.archive.org`` / ``wayback.archive.org``, the archive.today
family (``archive.ph`` / ``.is`` / ``.today`` / ``.li`` / ``.md`` / ``.vn``) and
``webcache.googleusercontent.com``; exact host match, with the version recorded
in the run setup. Version v2 (PI rulings 3 b and 4 b on the build questions,
2026-11-11) drops a leading ``www.`` before the match and adds the
``archive.fo`` alias and ``archive.org`` item pages (path ``/details/...``).
The version is recorded in the instrument payload's ``extractor_configuration``
``archive_host_list`` entry, written by
``g3o.run.presweep.instrument_binding``.

Host semantics:

- The host is :attr:`urllib.parse.SplitResult.hostname` of the URL: lowercased,
  userinfo and port dropped (a port is not part of the host), one trailing
  root dot dropped (``web.archive.org.`` is the same DNS name).
- **One leading ``www.`` is dropped** before the match (ruling 3 b, as
  :func:`g3o.common.urlnorm.site_host` does for the official-domain test), so
  ``www.archive.ph`` matches. **No other subdomain, prefix or suffix
  matching:** ``foo.web.archive.org`` does not.
- **Path-scoped entries** (:data:`ARCHIVE_PATH_PREFIXES`): ``archive.org``
  counts only for paths under ``/details/`` (ruling 4 b), not its whole site.
- A URL with no host (scheme-less, unparseable) is refused, not guessed.

Changing the list is a new version: edit :data:`ARCHIVE_HOSTS` /
:data:`ARCHIVE_PATH_PREFIXES`, bump
:data:`ARCHIVE_HOST_LIST_VERSION` and re-pin :data:`ARCHIVE_HOST_LIST_SHA256`;
the import-time guard refuses a list that drifted from its pinned hash.
"""

from __future__ import annotations

import hashlib
import json
from urllib.parse import urlsplit

#: Version of the archive-host list (PI ruling A2.1 a; v2 rulings 3 b / 4 b, 2026-11-11).
ARCHIVE_HOST_LIST_VERSION = "g3o.archive_hosts.v2"

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
    "archive.fo",  # archive.today alias (ruling 4 b)
    "webcache.googleusercontent.com",
})

#: Hosts that count only under these path prefixes (ruling 4 b): archive.org item pages.
ARCHIVE_PATH_PREFIXES: dict[str, tuple[str, ...]] = {"archive.org": ("/details/",)}

#: A leading ``www.`` is dropped before matching (ruling 3 b).
STRIP_WWW = True


def host_list_sha256(hosts: frozenset[str] = ARCHIVE_HOSTS,
                     path_prefixes: dict[str, tuple[str, ...]] = ARCHIVE_PATH_PREFIXES,
                     strip_www: bool = STRIP_WWW) -> str:
    """SHA-256 of the list's whole definition (hosts, path prefixes, www rule) as compact JSON."""
    spec = {"hosts": sorted(hosts), "path_prefixes": {h: list(p) for h, p in sorted(path_prefixes.items())},
            "strip_www": strip_www}
    return hashlib.sha256(json.dumps(spec, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


#: Pinned hash of :data:`ARCHIVE_HOSTS` for :data:`ARCHIVE_HOST_LIST_VERSION`.
ARCHIVE_HOST_LIST_SHA256 = "db74c36cce68becaff226749d124e40d3d3480ac803ab3a1d34c6dea8af56b7b"
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
    if host and STRIP_WWW and host.startswith("www.") and len(host) > 4:
        host = host[4:]
    if not host:
        raise ValueError(f"source URL has no host: {url!r}")
    return host


def is_archive_address(url: str) -> bool:
    """True when the URL's host is one of :data:`ARCHIVE_HOSTS`, or a path-scoped host under its prefix."""
    host = archive_host(url)
    if host in ARCHIVE_HOSTS:
        return True
    prefixes = ARCHIVE_PATH_PREFIXES.get(host)
    return bool(prefixes) and urlsplit(url.strip()).path.startswith(prefixes)


def setup_record() -> dict[str, object]:
    """What the run setup records about the list: version, hash and the hosts themselves."""
    return {"version": ARCHIVE_HOST_LIST_VERSION, "sha256": ARCHIVE_HOST_LIST_SHA256,
            "hosts": sorted(ARCHIVE_HOSTS),
            "path_prefixes": {h: list(p) for h, p in sorted(ARCHIVE_PATH_PREFIXES.items())},
            "strip_www": STRIP_WWW}


__all__ = ["ARCHIVE_HOSTS", "ARCHIVE_PATH_PREFIXES", "STRIP_WWW", "ARCHIVE_HOST_LIST_SHA256", "ARCHIVE_HOST_LIST_VERSION", "archive_host",
           "host_list_sha256", "is_archive_address", "setup_record"]
