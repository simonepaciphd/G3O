"""Where Stage 4's HTTP requests leave from, and how that is recorded.

Measured 2026-08-26 against run ``r20260824T215623Z-bb4e``. A paired probe of
120 URLs — one per institution, sampled from the 636 institutions whose triage
kept URLs and whose every fetch failed — run with identical code and identical
headers from two egresses:

===================================  ==============  ===================
egress                               200-with-body   what came back
===================================  ==============  ===================
DigitalOcean sfo3 (the run droplet)  **0 / 120**     64x HTTP 406, 37x 403
residential ISP                      **91 / 120**    10x 403, rest TLS/conn
===================================  ==============  ===================

The 406s arrive with the ``server`` header stripped (a school-CMS edge); the
403s are Cloudflare (``server: cloudflare``, ``cf-ray``). **The user-agent is
not the cause** — the same probe from the droplet under a Chrome UA returned the
identical distribution (64x 406, 36x 403, 0 successes). The discriminating
variable is the egress ASN, which is issue #90 and about 12.4% of every run's
institutions.

So this module exists to let Stage 4 leave from somewhere else. Three properties
it is written to hold:

* **All three egress points move together.** Page fetches
  (:mod:`g3o.scrape.fetcher`), ``robots.txt`` fetches
  (:mod:`g3o.scrape.politeness`) and the headless render
  (:mod:`g3o.scrape.render`) must share one egress. Fetching ``robots.txt``
  direct while fetching pages through a proxy would decide politeness from one
  identity and act on it from another — the D4 respect-robots decision assumes
  those are the same host asking.
* **Credentials never reach a log, a manifest, or a leg record.** A residential
  proxy endpoint carries ``user:pass`` in its URL. :func:`describe` records the
  host and port only, and :func:`redact` scrubs the full URL out of any text on
  its way to disk — the same discipline
  :func:`g3o.run.orchestrate.ingest.redact_dsn` applies to the DSN.
* **Off by default, and recorded when on.** No proxy is the historical behaviour
  and stays the default. When one *is* set, which egress a run used is part of
  what that run measured, so :func:`describe` goes into the manifest and the
  resume guard compares it (a run that changed egress halfway measured two
  different instruments).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from g3o.common import config


def proxy_url() -> str:
    """The configured proxy URL, or ``""`` when Stage 4 should go out direct.

    Read through :mod:`g3o.common.config` rather than :func:`os.environ` at the
    call site so tests can set it one way, and so the value is resolved exactly
    once per process like every other engineering parameter there.
    """
    return config.SCRAPE_PROXY_URL or ""


def enabled() -> bool:
    return bool(proxy_url())


def requests_proxies() -> dict[str, str] | None:
    """``proxies=`` for a :class:`requests.Session`, or ``None`` for direct.

    Both schemes get the same endpoint: a residential gateway is reached over
    HTTP and CONNECTs to the target, so an https-only or http-only mapping would
    send half of Stage 4's traffic out of the wrong egress — which is the failure
    this module is written against, in miniature.
    """
    url = proxy_url()
    if not url:
        return None
    return {"http": url, "https": url}


def playwright_proxy() -> dict[str, str] | None:
    """``proxy=`` for ``chromium.launch()``, or ``None`` for direct.

    playwright takes the credentials as separate fields rather than inline in the
    server URL, so they are split out here instead of at the launch site.
    """
    url = proxy_url()
    if not url:
        return None
    parts = urlsplit(url)
    server = f"{parts.scheme}://{parts.hostname}"
    if parts.port:
        server = f"{server}:{parts.port}"
    proxy: dict[str, str] = {"server": server}
    if parts.username:
        proxy["username"] = parts.username
    if parts.password:
        proxy["password"] = parts.password
    return proxy


def describe() -> dict[str, object]:
    """What went into the manifest: the egress identity, never its credentials.

    ``mode`` is the field a reader compares between two runs; ``endpoint`` is
    host[:port] so a proxy swap is visible, and ``credentialed`` records that a
    secret was in play without recording it.
    """
    url = proxy_url()
    if not url:
        return {"mode": "direct", "endpoint": None, "credentialed": False}
    parts = urlsplit(url)
    endpoint = parts.hostname or ""
    if parts.port:
        endpoint = f"{endpoint}:{parts.port}"
    return {
        "mode": "proxy",
        "endpoint": endpoint,
        "credentialed": bool(parts.username or parts.password),
    }


def redact(text: str) -> str:
    """Replace the proxy URL — and its bare password — with a marker.

    Ordered widest-match-first: the full URL goes before the bare password, so a
    password that is a substring of the URL is not replaced inside it and left
    with a dangling marker. Returns ``text`` unchanged when no proxy is set,
    which is the common case and must not pay for a scan.
    """
    url = proxy_url()
    if not url or not text:
        return text
    out = text.replace(url, "<proxy redacted>")
    password = urlsplit(url).password
    # Same floor as the DSN redactor: below 8 characters a "password" is a
    # substring of ordinary English and blanking it damages the log more than it
    # protects the secret.
    if password and len(password) >= 8:
        out = out.replace(password, "<redacted>")
    return out


__all__ = [
    "describe",
    "enabled",
    "playwright_proxy",
    "proxy_url",
    "redact",
    "requests_proxies",
]
