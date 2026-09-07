"""Serper.dev Google Search API client.

Ported from the pre-restructure `src/search_serper.py`. The pipeline calls
`search_google()` with institution-scoped queries from `query_builder`; the
multi-strategy and entity helpers below cover the cases where we need to
identify an institution's homepage or scope a query to a known domain.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config
from g3o.common.credentials import ResolvedCredentials, resolve

logger = logging.getLogger(__name__)

# One-shot flag: warn the operator the first time we silently fall back to
# mock results because SERPER_API_KEY is unset. Repeats would just spam logs.
_warned_mock = False

# Sentinel substring embedded in the mock-result URLs. The cache guard refuses
# to write any payload containing it so a mock result can never poison the
# shared on-disk cache again (review F1c, 2026-06-10).
_MOCK_LINK_SENTINEL = "g3o-mock"

# Live (``--execute``) mode. When True, the mock fallback is disabled and a
# missing key or a failed request is a hard error rather than a silent mock or
# empty-result — an empty artifact must mean the search actually ran and found
# nothing (review F1, 2026-06-10). The presweep orchestrator sets this at
# ``--execute`` startup; it stays False for dev/CLI use and dry runs.
_live_mode = False


class SerperConfigError(RuntimeError):
    """No Serper key is resolvable while live (``--execute``) mode is active."""


class SerperRequestError(RuntimeError):
    """A Serper request failed (quota/403/network) after retries in live mode.

    Distinct from "searched, found nothing": callers persist this as an
    explicit failure (attrition ledger + error marker), never as an empty
    result artifact.
    """


def set_live_mode(enabled: bool) -> None:
    """Enable/disable live mode (no mock, honest failures). Set by presweep."""
    global _live_mode
    _live_mode = enabled


def _serper_key(credentials: ResolvedCredentials | None) -> str | None:
    """The Serper key for one call (Run API spec §3.1/§3.2).

    ``credentials`` is what the presweep orchestrator threads down. ``None`` —
    the CLI subcommands, ad-hoc/library callers, and every test that predates the
    spec — resolves from the environment **at call time**, so precedence stays
    explicit -> env -> unset and no key is ever frozen at import.
    """
    if credentials is not None:
        return credentials.serper_api_key
    return resolve().serper_api_key


def _contains_mock(data: list[dict]) -> bool:
    return any(_MOCK_LINK_SENTINEL in (r.get("link") or "") for r in data)


@dataclass(frozen=True)
class SerperOptions:
    """Request parameters beyond ``q``/``num``, as one immutable bundle.

    Every field defaults to ``None`` meaning **omit the key entirely**, so
    ``SerperOptions()`` reproduces the pre-2026-08-01 request payload
    byte-for-byte. A parameter only ever reaches Serper by being named here,
    which is what keeps :func:`build_request_payload` the single place a
    parameter can enter both the request *and* the cache key.

    ``autocorrect`` (2026-08-01, PI sign-off): Serper's server-side default is
    ``true``, so Google has been free to silently respell institution names in
    every query G3O has run. Setting it ``False`` is a provenance fix — the
    query recorded in the artifact becomes the query Google actually answered.
    It is **not** a recall lever and was not measured as one.

    ``gl`` / ``hl`` (2026-08-30, PI sign-off) — **the search locale, which until
    now G3O could not express at all.** ``gl`` is the country the search is run
    from; ``hl`` is Google's interface language. Both were absent from this
    class, so every Serper query G3O has ever issued went out with them unset
    and took Serper's server-side default — US / English. That was invisible
    while only English ran. Under the signed language policy of 2026-08-30 it is
    a live confound: the policy chooses the *term's* language per institution
    while the *locale* stays anglophone, so a Japanese term is issued through a
    US/English Google and the run cannot claim to have searched Japan in
    Japanese.

    They are deliberately **two independent fields, not one "locale"**, because
    they come from different tables: ``hl`` is a property of the language tag
    and ``gl`` a property of the institution's country. France-``fr`` and
    Senegal-``fr`` share a term and need different ``gl``.

    Neither is validated here. Serper drops an unrecognised value with HTTP 200
    and no error, so the only evidence that a locale was honoured is its
    presence in :attr:`SerperResult.search_parameters` — validating against a
    hardcoded list would replace that live signal with a stale guess about what
    Google supports. Not all 89 tags of the signed policy have a Google
    interface language (Tifinagh, Dhivehi, Dzongkha, Tetum, Papiamento and
    Greenlandic are expected to have none), and the echo is how we find out.

    **Not measured as a recall lever.** Like ``autocorrect``, this is added so
    the parameter *can* be set and recorded; whether a matched locale retrieves
    more than the default is exactly what the 2026-08-30 term probe measures.
    """

    autocorrect: bool | None = None
    gl: str | None = None
    hl: str | None = None


DEFAULT_OPTIONS = SerperOptions()


def build_request_payload(
    query: str, num_results: int, options: SerperOptions | None = None
) -> dict:
    """Build the exact JSON body POSTed to Serper — the single source of truth.

    Both :func:`_execute` and :func:`_cache_key` consume the dict this returns,
    so a parameter cannot enter the request without entering the cache key.
    That coupling is the point: before 2026-08-01 the key was
    ``md5(f"{num_results}:{query}")`` and ignored every other parameter, so two
    materially different requests would have collided silently the moment any
    parameter began to vary (review, 2026-08-01).

    Key insertion order is ``q``, ``num``, then options in field order, so the
    legacy payload serialises byte-identically to ``{"q": ..., "num": ...}``.

    ``gl``/``hl`` follow ``autocorrect`` in field order and are omitted when
    ``None``, so an unlocalised call still produces the legacy two-key payload
    and therefore the legacy cache key. That is what keeps the locale addition
    from invalidating every cached result from before 2026-08-30 — and, on the
    other side, what guarantees a *localised* query can never be served from an
    *unlocalised* cache entry, since the key is derived from this payload.
    """
    opts = options if options is not None else DEFAULT_OPTIONS
    payload: dict = {"q": query, "num": num_results}
    if opts.autocorrect is not None:
        payload["autocorrect"] = opts.autocorrect
    if opts.gl is not None:
        payload["gl"] = opts.gl
    if opts.hl is not None:
        payload["hl"] = opts.hl
    return payload


def _cache_key(payload: dict, engine: str = "serper") -> str:
    """Hash the whole request payload, namespaced by search backend.

    ``sort_keys`` makes the key insensitive to insertion order (two callers
    building the same parameters in a different order must hit the same entry);
    ``ensure_ascii=False`` keeps non-ASCII queries from hashing differently than
    they are sent.

    ``engine`` namespaces the key by search backend and is prefixed onto the
    hashed blob rather than folded into ``payload``: it is a cache-partition
    tag, **not** a request parameter, so it must never reach the wire or the
    stored ``searchParameters`` provenance (that is what keeps ``payload``
    byte-faithful to what Serper received — see :func:`build_request_payload`).
    Two backends issuing the *same* query at the *same* result count must not
    collide on one on-disk entry and silently serve each other's results.
    Inert while Serper is the sole backend; defaulting to ``"serper"`` keeps
    every current call site unchanged.
    """
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    namespaced = f"{engine}:{blob}"
    return hashlib.md5(namespaced.encode("utf-8")).hexdigest()


# Cache filename prefix. Bumped ``serp_`` -> ``serp_v2_`` when the key became
# payload-derived and the on-disk entry gained the ``searchParameters`` echo
# (2026-08-01): the two generations are not interchangeable, and the prefix
# bump orphans the old files rather than silently reinterpreting them. Same
# precedent as the fetcher's ``page_v2_``.
_CACHE_PREFIX = "serp_v2_"


def _cache_path(payload: dict, engine: str = "serper") -> str:
    return os.path.join(config.CACHE_DIR, f"{_CACHE_PREFIX}{_cache_key(payload, engine)}.json")


def _cached(payload: dict, engine: str = "serper") -> dict | None:
    path = _cache_path(payload, engine)
    # Concurrent-read retry (Stage 1a/1b concurrency, 2026-07): a reader's
    # open() can transiently lose a Windows sharing-violation race against
    # another thread's os.replace() landing on this exact path (the atomic
    # write itself is still correct — the reader only ever sees a torn file
    # or this transient error, never partial content). Bounded retry clears
    # it; a no-op on POSIX, which doesn't raise for this reason.
    for attempt in range(5):
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, FileNotFoundError):
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))
    return None


def _save_cache(payload: dict, entry: dict, engine: str = "serper") -> None:
    """Persist one cache entry keyed by the full request ``payload``.

    ``entry`` is the v2 on-disk shape: ``{"results": [...],
    "searchParameters": {...}}``. The echo is stored alongside the results so a
    cache hit stays as auditable as a live call — otherwise the parameters
    Serper honoured would be recoverable only for uncached queries.

    ``engine`` namespaces the on-disk entry by backend (see :func:`_cache_key`)
    so a write under one backend is never read back under another.
    """
    if _contains_mock(entry.get("results") or []):
        # Belt-and-suspenders: in live mode mock is never produced, but a dev
        # session must not seed the shared cache with mock URLs (review F1c).
        logger.debug("Refusing to cache mock SERP results for payload %r", payload)
        return
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(payload, engine)
    # Atomic write (Stage 1a/1b concurrency, 2026-07): two worker threads can
    # race on the same cache key (identical query + num_results). A plain
    # open(path, "w") lets a concurrent reader observe a torn/partial file; a
    # per-writer temp file + os.replace makes the swap atomic. The temp name
    # includes pid + thread id so two concurrent writers never collide on the
    # same temp path before either replace() lands.
    tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
    # Windows can transiently deny os.replace with PermissionError while
    # another thread's open(path) (a concurrent _cached() read) still holds
    # the destination — Windows files aren't opened with FILE_SHARE_DELETE by
    # default, unlike POSIX rename which never raises for this reason. The
    # reader's open/read/close window is brief, so a bounded retry with capped
    # backoff clears it; this loop is a no-op (succeeds first try) on POSIX.
    #
    # A cache write is best-effort: if the replace never lands (sustained
    # same-key contention), we log, drop the temp file, and give up rather than
    # raise — a missed cache write costs a re-fetch, never a crashed stage.
    for attempt in range(12):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 11:
                logger.warning(
                    "serper cache write gave up after contention on %s", path
                )
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                return
            time.sleep(min(0.01 * (2**attempt), 0.25))


def _mock_response() -> dict:
    """Dev-mode mock payload (one-shot warning). Never cached (see _save_cache)."""
    global _warned_mock
    if not _warned_mock:
        logger.warning(
            "SERPER_API_KEY unset — returning MOCK results; live discovery is OFF"
        )
        _warned_mock = True
    return {
        "organic": [
            {"title": "Mock Result 1", "link": "https://example.com/g3o-mock", "snippet": "Mock GenAI policy."},
            {"title": "Mock Result 2", "link": "https://example.org/g3o-mock.pdf", "snippet": "Mock guidelines."},
        ]
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _execute(payload: dict, *, api_key: str) -> dict:
    """POST ``payload`` to Serper with retry. Assumes a key is present.

    Takes the already-built payload rather than ``(query, num_results)`` so the
    bytes on the wire and the bytes fed to :func:`_cache_key` are the same dict
    — see :func:`build_request_payload`.

    ``api_key`` is passed in rather than read here so this function holds no
    credential policy at all (§3.2); the missing-key / mock decision and the
    precedence live in :func:`search_google_detailed`, so a config error is never
    retried or wrapped in a tenacity ``RetryError``.
    """
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    response = requests.post(
        config.SERPER_ENDPOINT,
        headers=headers,
        data=json.dumps(payload),
        timeout=config.REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def account_endpoint() -> str:
    """Derive the ``/account`` URL from :data:`config.SERPER_ENDPOINT`.

    Derived rather than hard-coded so a redirected or self-hosted endpoint
    keeps both URLs on the same host. Verified live 2026-08-01:
    ``GET https://google.serper.dev/account`` -> HTTP 200
    ``{"balance":48028,"rateLimit":50}``. (``api.serper.dev`` 404s; there is no
    prose documentation — ``docs.serper.dev`` is NXDOMAIN.)
    """
    parts = urlsplit(config.SERPER_ENDPOINT)
    return urlunsplit((parts.scheme, parts.netloc, "/account", "", ""))


def get_account(credentials: ResolvedCredentials | None = None) -> dict:
    """Return Serper's live account state, e.g. ``{"balance": N, "rateLimit": 50}``.

    The spend guard: credit cost is reported as a **balance delta** across a
    run rather than as ``queries x 1`` arithmetic, so a silently-retried or
    silently-dropped request cannot hide inside an estimate. Querying
    ``/account`` does not itself consume a credit (balance is unchanged across
    back-to-back calls, verified 2026-08-01).

    Raises whatever ``requests`` raises; callers decide whether a missing
    balance reading is fatal.
    """
    headers = {
        "X-API-KEY": _serper_key(credentials),
        "Content-Type": "application/json",
    }
    response = requests.get(
        account_endpoint(), headers=headers, timeout=config.REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def get_balance(credentials: ResolvedCredentials | None = None) -> int | None:
    """Best-effort credit balance. Returns ``None`` rather than raising.

    Used at run start/end where a failed balance read must not abort a run that
    is otherwise fine — the validation report then reports the delta as
    unavailable instead of the run dying over telemetry.
    """
    try:
        value = get_account(credentials).get("balance")
    except Exception as exc:  # network, auth, malformed JSON
        logger.warning("Serper /account balance read failed: %s", exc)
        return None
    return int(value) if isinstance(value, (int, float)) else None


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


@dataclass(frozen=True)
class SerperResult:
    """One Serper call's outcome: results plus the provenance to audit them."""

    results: list[dict]
    # Serper's echo of the parameters it actually honoured. Recording it makes
    # silent parameter drops detectable: an unrecognised value (``gl='zz'``) is
    # dropped with HTTP 200 and no error, so the only evidence that a request
    # was not the request you wrote is the absence of the key here.
    search_parameters: dict
    from_cache: bool
    payload: dict


def search_google_detailed(
    query: str,
    num_results: int = 10,
    force_refresh: bool = False,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
) -> SerperResult:
    """Run a Serper query and return results **plus** request/echo provenance.

    :func:`search_google` is the thin list-returning wrapper over this and
    remains the pipeline's ordinary entry point; callers that persist telemetry
    (the Stage 1a/1b runners) use this form to capture ``searchParameters``.

    ``credentials`` (spec §3.2) carries the key for this call; ``None`` resolves
    from the environment at call time. Note the ordering below: the cache is
    consulted **before** any key is needed, so a fully-cached dry run still
    requires no credential at all — the property the byte-identical dry-run gate
    depends on.
    """
    payload = build_request_payload(query, num_results, options)

    if not force_refresh:
        cached = _cached(payload)
        if cached is not None:
            return SerperResult(
                results=cached.get("results") or [],
                search_parameters=cached.get("searchParameters") or {},
                from_cache=True,
                payload=payload,
            )

    api_key = _serper_key(credentials)
    if not api_key:
        if _live_mode:
            # Missing key in live mode is a hard error — never degrade to mock.
            raise SerperConfigError(
                "No Serper API key is resolvable (explicit credentials or "
                "SERPER_API_KEY) but live (--execute) discovery is active. "
                "Refusing to return mock results. Set SERPER_API_KEY before running "
                "--execute, or run a dry run."
            )
        data = _mock_response()
    else:
        try:
            data = _execute(payload, api_key=api_key)
        except Exception as exc:  # network / Serper error (quota, 403, timeout)
            if _live_mode:
                # Honest failure: an empty artifact must mean "searched, found
                # nothing", so a failed request raises rather than returning [].
                raise SerperRequestError(
                    f"Serper request failed for query {query!r}: {exc}"
                ) from exc
            logger.warning("Search failed: %s", exc)
            return SerperResult(
                results=[], search_parameters={}, from_cache=False, payload=payload
            )

    results: list[dict] = []
    for idx, item in enumerate(data.get("organic", [])):
        results.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
                "domain": _domain(item.get("link", "")),
                "position": item.get("position", idx + 1),
                "date": item.get("date"),
                "sitelinks": item.get("sitelinks", []),
            }
        )
    echo = data.get("searchParameters") or {}

    _save_cache(payload, {"results": results, "searchParameters": echo})
    return SerperResult(
        results=results, search_parameters=echo, from_cache=False, payload=payload
    )


def search_google(
    query: str,
    num_results: int = 10,
    force_refresh: bool = False,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
) -> list[dict]:
    """Run a Serper query and return normalized organic results.

    Each result dict has keys: title, link, snippet, domain, position, date, sitelinks.
    """
    return search_google_detailed(
        query,
        num_results=num_results,
        force_refresh=force_refresh,
        options=options,
        credentials=credentials,
    ).results


def build_site_query(query: str, site_domain: str) -> str:
    """Wrap a query with Google's `site:` operator."""
    return f"site:{site_domain} {query}"


def build_filetype_query(query: str, filetype: str = "pdf") -> str:
    """Wrap a query with Google's `filetype:` operator."""
    return f"{query} filetype:{filetype}"


def search_entity_homepage(entity_name: str, entity_type: str = "government institution") -> dict:
    """Best-effort homepage discovery for a named entity."""
    query = f'"{entity_name}" official website {entity_type}'
    results = search_google(query, num_results=5)
    if not results:
        results = search_google(f"{entity_name} {entity_type}", num_results=5)
    if results:
        return {
            "homepage": results[0].get("link"),
            "domain": results[0].get("domain"),
            "confidence": "high",
        }
    return {"homepage": None, "domain": None, "confidence": "none"}


def search_entity_with_site_scope(
    entity_name: str, topic: str, homepage_domain: str | None = None
) -> list[dict]:
    """Scope a topic search to an entity's known (or discoverable) homepage."""
    if not homepage_domain:
        homepage_domain = search_entity_homepage(entity_name).get("domain")

    if homepage_domain:
        return search_google(build_site_query(topic, homepage_domain), num_results=10)
    return search_google(f"{entity_name} {topic}", num_results=10)


def multi_strategy_search(
    entity_name: str, topic: str, num_results_per_strategy: int = 5
) -> list[dict]:
    """Run several query patterns against Serper and dedupe by URL.

    Each result carries a `search_strategy` field naming the query that found it,
    which downstream layers use for provenance and ranking.
    """
    strategies = [
        f'"{entity_name}" "{topic}"',
        f"{entity_name} {topic}",
        f"{entity_name} {topic} policy",
        f"{entity_name} {topic} announcement",
        build_filetype_query(f"{entity_name} {topic}", "pdf"),
    ]

    seen: set[str] = set()
    out: list[dict] = []
    for query in strategies:
        for r in search_google(query, num_results=num_results_per_strategy):
            url = r.get("link", "")
            if url and url not in seen:
                seen.add(url)
                r["search_strategy"] = query
                out.append(r)
    return out
