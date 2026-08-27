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
    try:
        port = parts.port
    except ValueError:
        # ``urlsplit`` defers the port parse to attribute access, so a
        # non-numeric port raises *here* rather than at parse time. This
        # function must not be the thing that raises: it is the manifest's
        # identity field, and a run that cannot describe its own egress would
        # die inside ``build_manifest`` with a ValueError about integer casting
        # — which reads as a bug in the manifest writer rather than as a typo in
        # an environment variable. :func:`validate` is the check that refuses
        # such a URL, and it runs first in ``plan_run``; this is only what
        # happens if some other caller reaches here anyway.
        #
        # ``None``, not the raw text: the port is unusable, and putting an
        # unparseable string in the manifest's endpoint would let two runs that
        # differ only in a typo compare as different instruments.
        port = None
    if port:
        endpoint = f"{endpoint}:{port}"
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


def _user_agent_has_contact() -> bool:
    """Does the user-agent give anyone a way to reach this project?

    A shape check, not a validity check: it asks whether a URL or an address is
    present at all, not whether it resolves or whether anyone reads it. The
    conventional crawler form is ``Name/version (+https://host/page)``, and an
    email in parentheses is equally reachable, so both count.
    """
    ua = config.USER_AGENT or ""
    return "http://" in ua or "https://" in ua or "@" in ua


class EgressConfigError(ValueError):
    """``G3O_SCRAPE_PROXY`` is set but unusable.

    Its own class so a caller can distinguish "the operator mistyped the proxy"
    from any other ``ValueError`` and refuse the run rather than degrade into
    one. The message names the *defect*, never the value — see
    :func:`validate`.
    """


def validate() -> None:
    """Refuse a proxy URL that cannot work, before a run starts. No-op when direct.

    Added 2026-08-27 after measuring what a malformed value actually does. Two
    ordinary operator typos — a trailing space, which survives a copy-paste out
    of a password manager, and a non-numeric port — make ``requests`` raise
    ``InvalidURL("Failed to parse: <the whole URL>")`` on *every* fetch. Two
    consequences, and the second is the reason this exists:

    * the run does not fail, it fails *per URL*, so 10,000 institutions each
      record a scrape failure and the run reports a catastrophic yield rather
      than a configuration error;
    * that message carries ``user:pass``, so the credential is written once per
      URL. The ledger sinks now redact it, but redaction at the sink is a net
      under a fall. This is the guardrail at the top.

    Raising here converts both into one refusal, before the first fetch and
    before anything is written to disk.

    **The message must never contain the URL.** Every branch below reports a
    property — a missing scheme, a port that will not parse — and the endpoint
    at most, which is what :func:`describe` already puts in the manifest.
    """
    url = proxy_url()
    if not url:
        return
    if url != url.strip():
        # First, because it is both the likeliest typo and the one whose
        # symptom is least legible: everything below would pass on the stripped
        # value, so a later check would report nothing wrong.
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY has leading or trailing whitespace. requests "
            "cannot parse it and echoes the whole URL — credentials included — "
            "into the error it raises on every fetch. Strip it and retry."
        )
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise EgressConfigError(
            f"G3O_SCRAPE_PROXY has scheme {parts.scheme!r}; requests accepts "
            "only 'http' or 'https' for a proxy. A residential gateway is "
            "reached over http even when the target is https."
        )
    if not parts.hostname:
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY has no host. Expected the shape "
            "http://<user>:<pass>@<host>:<port>."
        )
    try:
        port = parts.port
    except ValueError as exc:
        # urlsplit defers the port parse to attribute access, so a non-numeric
        # port only raises here. Chained deliberately — but ``exc`` carries the
        # port text alone, not the URL, so it is safe to keep the context.
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY has a port that is not a number."
        ) from exc
    if port is None:
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY names no port. A residential gateway is reached "
            "on an explicit port; defaulting to 80/443 would silently send "
            "Stage 4 somewhere else."
        )
    if not _user_agent_has_contact():
        # Tied to the proxy deliberately, and only to the proxy. Routing Stage 4
        # through a residential gateway makes the observatory opaque at the
        # *network* layer; the user-agent is then the only identity control it
        # still holds, and a site operator who wants to ask about this traffic —
        # or to have it stop — needs somewhere to write. Going opaque at both
        # layers at once is a different thing from going opaque at one, and it
        # is not a thing this pipeline should be able to do by omission.
        #
        # Measured 2026-08-27, and it is why this is a guard rather than a note:
        # the droplet's ``.env`` sets no ``USER_AGENT`` at all, so every
        # production run so far has gone out as the bare default with no contact,
        # while the laptop — which barely scrapes — sets a full one. The gap was
        # invisible because nothing compared them.
        #
        # A direct run is untouched. This refuses only the combination.
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY is set but USER_AGENT carries no contact point "
            f"({config.USER_AGENT!r}). Through a residential proxy the "
            "user-agent is the only way a site operator can identify or reach "
            "this crawler. Set USER_AGENT to include a contact URL or email — "
            "e.g. 'G3O-Observatory/0.1 (+https://example.org/crawler)'. "
            "urllib.robotparser reads only the token before the first '/', so "
            "a suffix cannot change which robots rules apply."
        )
    if not parts.username or not parts.password:
        # Not fatal in principle — an IP-allowlisted gateway needs no userinfo —
        # but Bright Data's is credentialed, and a gateway reached without the
        # credential it expects answers 407 to every request, which Stage 4
        # books as a scrape failure. Better to say so than to measure it.
        raise EgressConfigError(
            "G3O_SCRAPE_PROXY carries no username:password. If the gateway is "
            "IP-allowlisted rather than credentialed, remove this check "
            "deliberately rather than working around it."
        )
