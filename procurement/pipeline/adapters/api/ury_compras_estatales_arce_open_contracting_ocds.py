"""Adapter: Uruguay - Agencia Reguladora de Compras Estatales (ARCE), Open
Contracting (OCDS).

Verified live 2026-08-10 (partial verification — see notes below, not a full
production sign-off):
  - Index feed (Atom/RSS XML, NOT JSON): GET
    http://www.comprasestatales.gub.uy/ocds/rss/{YYYY}/{MM}
    Lists recent releases for that month: each <item> carries a <guid>
    (release id, e.g. "llamado-1352555" for a tender, "adjudicacion-..." for
    an award) and a <link> to the individual release.
  - Individual release (real OCDS 1.1 release package, confirmed by direct
    HTTP call): GET http://www.comprasestatales.gub.uy/ocds/release/{id}
    Returns {"uri", "version": "1.1", "publisher", "license",
    "publicationPolicy", "releases": [...]} — a genuine OCDS release, not a
    native format. This IS an OCDS source (unlike Brazil's PNCP, see that
    adapter's module docstring for the contrast).
  - No API key. HTTP (not HTTPS) on this host; the RSS endpoint 406s if the
    request forces `Accept: application/json` — it only serves XML there.
  - Blocks the default `python-requests/x.y` User-Agent with a 403 (confirmed:
    plain `curl` and a browser UA both succeed against the identical URL that
    a bare `requests.get()` fails on). A browser-style User-Agent header is
    required on every request to this host, not just a courtesy.

Because extract_ocds() (core.standardize) is the shared, already-tested OCDS
extractor and this source's payload is genuine OCDS, this adapter does NOT
override extract() — SourceAdapter.extract() already routes is_ocds=True
sources through extract_ocds() for free (see core/base.py). This is the
"first OCDS-API source" the roadmap has been waiting on: earlier this session
Brazil's PNCP was built and run first, but turned out on verification to be
non-OCDS, so it did not exercise this shared path — this adapter is the
correction.

The tracker's own RA note on this row ("bulk ocds, cant find api (language)")
undersold it — the release-lookup pattern above is a real, working, per-record
API, not bulk-only, once you follow the RSS index rather than looking for a
single documented REST API page.

NOT YET DONE (plumbing/QC probe only): full rate-limit measurement, robots.txt/
ToS review, complete date-range coverage beyond the bounded probe window below.
verification_status stays unverified_snapshot; run only via
--allow-unverified --limit N.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

from ...core.base import SourceAdapter
from ...core.models import GenAIQuerySet, Hit, RawRecord

log = logging.getLogger(__name__)

RSS_URL = "http://www.comprasestatales.gub.uy/ocds/rss/{year}/{month:02d}"
RELEASE_URL = "http://www.comprasestatales.gub.uy/ocds/release/{release_id}"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CACHE_DIR = Path("data_cache") / "ury_compras_estatales_arce_open_contracting_ocds"


def _cache_raw(native_id: str, payload: dict, cache_dir: Path = CACHE_DIR) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_id = native_id.replace("/", "_")
    path = cache_dir / f"{safe_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


RETRY_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = (1, 2, 4)
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _get(url: str, headers: dict) -> tuple[requests.Response | None, str, int]:
    """GET with retries on network errors, 429 and 5xx. Other 4xx fail at once.

    Returns (response or None, last error, attempts used).
    """
    error = ""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code not in _RETRY_STATUS:
                resp.raise_for_status()
                return resp, "", attempt
            error = f"HTTP {resp.status_code}"
        except requests.HTTPError as exc:
            return None, str(exc), attempt
        except requests.RequestException as exc:
            error = f"{type(exc).__name__}: {exc}"
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
    return None, error, RETRY_ATTEMPTS


def _parse_year_month(value: str) -> tuple[int, int]:
    year, month = str(value).split("-")
    year, month = int(year), int(month)
    if not 1 <= month <= 12:
        raise ValueError(f"bad month in {value!r}")
    return year, month


def window_year_months(since: str, until: str) -> list[tuple[int, int]]:
    """Every (year, month) from `since` to `until` inclusive, oldest first."""
    (y, m), end = _parse_year_month(since), _parse_year_month(until)
    if (y, m) > end:
        raise ValueError(f"window since {since} is after until {until}")
    out = []
    while (y, m) <= end:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _recent_year_months(count: int) -> list[tuple[int, int]]:
    """The current month plus `count - 1` prior months, most recent first."""
    today = datetime.now(timezone.utc)
    year, month = today.year, today.month
    out = []
    for _ in range(count):
        out.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return out


class Adapter(SourceAdapter):
    access_mode = "api"
    is_ocds = True  # confirmed by direct verification — see module docstring

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """The monthly RSS index has no free-text keyword parameter either;
        same documented fallback as the PNCP adapter (architecture.md §5a):
        return recent releases and let the classifier filter downstream.

        The window is fixed by config `window_since`/`window_until` (YYYY-MM,
        set by the CLI's --since/--until) so a run is reproducible. Without it,
        the last 3 months relative to today are used: a probe default only,
        never for a documented run. The index starts at 2017-11 (earlier
        months return 404, checked 2026-10-07).
        """
        since, until = self.config.get("window_since"), self.config.get("window_until")
        months = window_year_months(since, until) if since and until else list(reversed(_recent_year_months(3)))
        self.window_months = [f"{y:04d}-{m:02d}" for y, m in months]
        self.search_failures = []
        for year, month in months:
            url = RSS_URL.format(year=year, month=month)
            resp, error, attempts = _get(url, {"User-Agent": BROWSER_UA})
            if resp is None:
                log.error("ARCE RSS fetch failed (%s) after %d attempt(s): %s", url, attempts, error)
                self.search_failures.append({"month": f"{year:04d}-{month:02d}", "url": url,
                                             "error": error, "attempts": attempts})
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as exc:
                log.error("ARCE RSS parse failed (%s): %s", url, exc)
                continue

            items = root.findall("./channel/item")
            for item in items:
                guid = item.findtext("guid")
                link = item.findtext("link")
                if not guid or not link:
                    continue
                yield Hit(source_id=self.source_id, native_id=guid, ref=link)

            time.sleep(0.5)  # polite pacing — untested rate limit, be conservative

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """Each hit is an index entry only (id + link) — the RSS feed does not
        carry the release itself, so every hit costs one real HTTP GET here."""
        for hit in hits:
            url = str(hit.ref)
            resp, error, attempts = _get(url, {"Accept": "application/json", "User-Agent": BROWSER_UA})
            payload = None
            if resp is not None:
                try:
                    payload = resp.json()
                except ValueError as exc:
                    error = f"invalid JSON: {exc}"
            if payload is None:
                log.error("ARCE release fetch failed (%s) after %d attempt(s): %s", url, attempts, error)
                self.fetch_failures.append({"native_id": hit.native_id, "url": url,
                                            "error": error, "attempts": attempts})
                continue

            raw_payload_ref = _cache_raw(hit.native_id, payload,
                                         Path(self.config.get("cache_dir") or CACHE_DIR))
            yield RawRecord(
                source_id=self.source_id,
                native_id=hit.native_id,
                payload=payload,
                fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                raw_payload_ref=raw_payload_ref,
            )
            time.sleep(0.2)

    # No extract() override: is_ocds=True routes through the shared
    # core.standardize.extract_ocds() automatically (core/base.py).
