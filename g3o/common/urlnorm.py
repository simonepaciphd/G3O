"""Deterministic URL normalisation shared across stages.

One definition of "the root of a URL", used by every stage that needs to treat
two URLs on the same host as the same institution. Having a single
implementation is the point: Stage 1b's ``site:`` query construction and the
Stage 2 official-site pick previously derived "the domain" independently, so
they could in principle disagree.

Two levels are provided:

``site_host``
    Bare host, lowercased, ``www.`` stripped, port preserved — the form the
    ``site:`` search operator wants (``mcit.gov.qa``).

``site_root``
    A canonical absolute root URL (``https://mcit.gov.qa/``) — the form to
    store and to compare picks on.

**Scheme is canonicalised to https.** This is deliberate: ``http://x.gov/`` and
``https://x.gov/`` are the same institution, and a cross-run report that counts
that difference as divergence is reporting noise. Callers that need the URL the
model actually returned must keep it alongside the normalised form rather than
recovering it from here — see ``2_official_site.json``, which stores both.

Both functions are pure and total: any input that cannot be parsed into a host
yields ``None`` rather than raising.
"""

from __future__ import annotations

from urllib.parse import urlparse

__all__ = ["site_host", "site_root"]


def site_host(url: str | None) -> str | None:
    """Lowercased host with any leading ``www.`` removed; ``None`` if unparseable.

    Port is preserved (``example.gov:8443``) because it is part of the origin.
    Any ``user:pass@`` userinfo is discarded before the ``www.`` strip, so
    credentials never leak into a ``site:`` query. A URL with no scheme
    (``example.gov/a``) has no netloc under :func:`urlparse` and therefore
    yields ``None`` — callers that accept scheme-less input must add a scheme
    first.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    netloc = parsed.netloc.lower().rpartition("@")[2].removeprefix("www.")
    return netloc or None


def site_root(url: str | None) -> str | None:
    """Canonical ``https://<host>/`` root, or ``None`` if unparseable.

    Path, query, fragment, and userinfo are discarded; see the module docstring
    on scheme canonicalisation.
    """
    host = site_host(url)
    return f"https://{host}/" if host else None
