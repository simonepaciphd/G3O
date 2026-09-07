#!/usr/bin/env python
"""Is Stage 4's proxy actually in the path? Answer it before a run, not after.

``G3O_SCRAPE_PROXY`` being *set* and the proxy being *live* are different facts,
and the gap between them is expensive: a gateway that quietly is not in the path
produces a run that looks like the network refused it, which is exactly the
symptom the proxy exists to fix. So this asks an echo service what IP it sees,
once direct and once through the proxy, and reports both.

Reads the same value through the same module Stage 4 does — no separate parsing,
so this cannot pass on a URL the pipeline would reject, or the reverse.

**Prints no credential on any path, including failures.** Every line it can emit
carries the endpoint at most, which is what ``manifest.json`` already records.
That is asserted in ``tests/test_verify_egress.py``, not merely intended: an
operator pastes this output into a terminal, a ticket, or a chat thread at
exactly the moment something is wrong.

Usage::

    ~/venv/bin/python scripts/verify_egress.py

Exit codes: 0 the proxy is live and the egress changed; 1 something is wrong and
the run should not be launched; 2 no proxy is configured (direct — not an error,
and the pipeline's default).
"""

from __future__ import annotations

import sys
from typing import Any

import requests

from g3o.scrape import egress

#: Plain-text IP echo. Chosen for having no JSON envelope to drift and no
#: dependency on a key: the body *is* the answer. If it ever disappears, any
#: equivalent works — nothing here parses a schema.
ECHO_URL = "https://api.ipify.org"
TIMEOUT = 20


def _fetch_ip(proxies: dict[str, str] | None) -> tuple[str | None, str | None]:
    """``(ip, error_label)`` — never the exception's own text.

    A ``requests`` exception can carry the proxy URL verbatim (measured
    2026-08-27: a malformed value produces ``InvalidURL: Failed to parse:
    <url>``), so only the exception's *class name* is ever surfaced. The whole
    point of this script is to be safe to paste.
    """
    try:
        response = requests.get(ECHO_URL, proxies=proxies, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text.strip(), None
    except Exception as exc:  # noqa: BLE001 - the message is the thing to suppress
        return None, type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    if not egress.enabled():
        print("G3O_SCRAPE_PROXY is not set — Stage 4 will go out direct.")
        print("This is the default and is not an error.")
        return 2

    # Validate before describing, in that order, for the same reason ``plan_run``
    # does: ``describe`` reads the port, and a port that is not a number is one
    # of the defects ``validate`` exists to name in plain words.
    try:
        egress.validate()
    except egress.EgressConfigError as exc:
        print("REFUSED — the configured proxy cannot work:")
        print(f"  {exc}")
        return 1

    described: dict[str, Any] = egress.describe()
    print(f"endpoint     : {described['endpoint']}")
    print(f"credentialed : {described['credentialed']}")
    print()

    direct_ip, direct_err = _fetch_ip(None)
    print(f"direct egress: {direct_ip or f'FAILED ({direct_err})'}")

    proxy_ip, proxy_err = _fetch_ip(egress.requests_proxies())
    print(f"proxy egress : {proxy_ip or f'FAILED ({proxy_err})'}")
    print()

    if proxy_ip is None:
        print("FAIL — nothing came back through the proxy. The gateway is not")
        print("reachable, or it rejected the credentials. Do not launch a run.")
        return 1

    if direct_ip is not None and proxy_ip == direct_ip:
        # The quiet failure, and the reason this script exists rather than a
        # bare "did it 200" check: a wrong port often connects to *something*.
        print("FAIL — the proxy egress IP is identical to the direct one, so the")
        print("proxy is NOT in the path. Nothing raised; check the port first.")
        return 1

    print("OK — traffic is leaving through a different egress than direct.")
    print()
    print("This does NOT confirm the egress is residential rather than another")
    print("datacenter. Check the ASN of the address above before trusting a run")
    print("to it — the ASN is the variable #90 measured, not the address.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
