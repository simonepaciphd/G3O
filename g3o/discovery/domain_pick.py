"""Naive first-non-aggregator domain pick over leg-1 results.

This is **not** the pipeline's official-site decision. Stage 2's
``classify_official_site`` remains the arbiter it already is architecturally:
the chain's leg 1 hands Stage 2 a list of candidate URLs exactly as the legacy
Stage 1a did, and Stage 2 chooses.

What this module provides is the *naive baseline* that the findings memo
measured (21/24 correct), recorded into the Stage 1a artifact so the
confirmation run can score Stage 2's adjudication against it without a second
paid pass. Its three known failures are precisely the class of error Stage 2
exists to catch: ``wipo.int`` returned for both Madagascar and Burkina Faso
(an intergovernmental body's page *about* the institution), and
``loslunasnm.gov`` (the village) for Los Lunas Schools (the district).

No network calls; pure functions over already-fetched result dicts.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Hosts that are never an institution's own domain. Kept deliberately short and
# obvious: this is a baseline for comparison, not a curated allowlist, and
# padding it would flatter the naive rule against the Stage 2 arbiter it is
# meant to be measured against.
AGGREGATOR_SUFFIXES: tuple[str, ...] = (
    "wikipedia.org",
    "wikimedia.org",
    "wikiwand.com",
    "dbpedia.org",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "crunchbase.com",
    "bloomberg.com",
    "glassdoor.com",
    "indeed.com",
    "yelp.com",
    "tripadvisor.com",
    "mapquest.com",
    "google.com",
    "bing.com",
    "amazon.com",
    "scribd.com",
    "issuu.com",
    "slideshare.net",
    "academia.edu",
    "researchgate.net",
)

# Host *prefixes* that are infrastructure endpoints rather than a public site.
# Called out in the findings' scoring rule; applied here too so leg 1 cannot
# nominate a mail-autodiscovery host as an institution's domain.
INFRA_HOST_PREFIXES: tuple[str, ...] = (
    "autodiscover.",
    "webmail.",
    "mail.",
    "smtp.",
    "imap.",
    "mx.",
    "cpanel.",
    "webdisk.",
)


def host_of(url: str) -> str:
    """Lowercased host with a leading ``www.`` stripped; ``""`` if unparseable."""
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def is_aggregator(host: str) -> bool:
    """True if ``host`` is (or is a subdomain of) a known aggregator."""
    if not host:
        return True
    return any(host == s or host.endswith("." + s) for s in AGGREGATOR_SUFFIXES)


def is_infra_host(host: str) -> bool:
    """True if ``host`` is a mail/infrastructure endpoint rather than a site."""
    return any(host.startswith(p) for p in INFRA_HOST_PREFIXES)


def is_usable_domain(host: str) -> bool:
    """A host that could plausibly be an institution's own public domain."""
    return bool(host) and "." in host and not is_aggregator(host) and not is_infra_host(host)


def pick_domain(records: list[dict]) -> dict:
    """Return the first non-aggregator host in ``records``, with its rank.

    ``records`` are leg-1 result dicts in Serper's returned order. The shape is
    always the same three keys so the Stage 1a artifact has a stable schema
    whether or not a domain was found:

        {"domain": str | None, "url": str | None, "rank": int | None}

    ``rank`` is 1-based over the result list as returned, so ``rank == 1`` means
    the very first organic result was usable (18/24 on the evaluation set).
    """
    for idx, rec in enumerate(records, start=1):
        url = rec.get("link") or ""
        host = host_of(url)
        if is_usable_domain(host):
            return {"domain": host, "url": url, "rank": idx}
    return {"domain": None, "url": None, "rank": None}
