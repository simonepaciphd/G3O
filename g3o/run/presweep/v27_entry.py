"""The v2.7 new-run entry: the real providers of a v2.7 run, built from its config (T-030).

PI ruling 132 a (2026-11-15): a production entry (``g3o.run.api.launch`` ->
``orchestrator.run_presweep`` with no injected ``V27Dispatch``) starts a v2.7 run
with the real v2.7 providers built from config. Wiring only: this module adds no
stage logic and lifts no refusal.

:func:`build_v27_dispatch` turns ``PresweepConfig.v27_runtime`` and the run's
resolved credentials into a :class:`~g3o.run.presweep.orchestrator.V27Dispatch`:

- ``settings``: ``instrument_binding.RuntimeSettings(**config.v27_runtime)``,
  every value explicit (none is defaulted here);
- ``jev_ask_fn``: :class:`LazyJevAsk`, the existing jev adapter
  (``stage_page_code.jev_ask`` over ``jev_client.client_from_credentials``,
  model ``settings.jev_model``);
- ``extract_fn``: :class:`LazyExtractor`, ``AnthropicExtractorClient.create``
  over an ``anthropic.Anthropic`` client given the run's resolved Anthropic key
  (sync Messages calls: the per-page stage calls the extractor one job at a time);
- ``entail_fn``: :func:`x35_entail_fn`, which returns
  ``support_check.run_entailment``, the only X35 entry. It refuses every call (no
  approved X35 binding exists; PI ruling 59 b), and ``run_presweep`` refuses it on
  entry, before planning;
- ``perpage_inputs``: :func:`perpage_inputs_builder`, None, the default builder
  (PI ruling D1 a), refused on entry while ``perpage_inputs_v27.MISSING_PRODUCERS``
  is non-empty (PI ruling 36 a);
- ``follow_fetch``: :func:`follow_fetch`, ``stage_follow.polite_fetch`` over a
  run-scoped robots cache and host throttle configured as Stage 4 is (T-025).

So a real v2.7 run is still refused at entry today (59 b, then 36 a), before any
Stage 1-4 spend; that is intended. The three module-level functions above are
the provider seams a mocked end-to-end test replaces (the X35 client, the per-page
builder ruling 36 a requires, the follow leg's fetch); the jev and Anthropic SDK
clients are replaced at their own constructors.

Nothing here creates a client or opens a connection at import or in
:func:`build_v27_dispatch`: both SDK clients are constructed on the first call
that needs them. A missing jev or extractor key is refused here, before any work.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from dataclasses import fields
from typing import Any

from g3o.common.credentials import ANTHROPIC_ENV_VAR, TYPESAFE_ENV_VAR, ResolvedCredentials


def runtime_settings(config: Any) -> Any:
    """``RuntimeSettings`` from ``config.v27_runtime``: every field given, no other key.

    Raises ``ValueError`` when ``v27_runtime`` is unset (no V27Dispatch injected and
    nothing to build the providers from) or names a missing or unknown field.
    """
    from g3o.run.presweep.instrument_binding import RuntimeSettings

    raw = getattr(config, "v27_runtime", None)
    if raw is None:
        raise ValueError(
            "pipeline_version='v2.7': no V27Dispatch was injected and config.v27_runtime is unset, so "
            "there is no default client to build: set v27_runtime to the RuntimeSettings of the run "
            "(PI ruling 132 a)"
        )
    if not isinstance(raw, Mapping):
        raise ValueError("config.v27_runtime must be a mapping of RuntimeSettings keyword arguments")
    names = {f.name for f in fields(RuntimeSettings)}
    missing, unknown = sorted(names - set(raw)), sorted(set(raw) - names)
    if missing or unknown:
        raise ValueError(f"config.v27_runtime: missing {missing}, unknown {unknown}; every RuntimeSettings "
                         "field must be given explicitly")
    return RuntimeSettings(**raw)


class LazyJevAsk:
    """The jev ``ask_fn`` of the per-page stage and Stage 6; the TypeSafe client is built on first use."""

    def __init__(self, credentials: ResolvedCredentials, model: str) -> None:
        self._credentials, self._model = credentials, model
        self._ask: Callable[..., Any] | None = None
        self._lock = threading.Lock()

    @property
    def constructed(self) -> bool:
        return self._ask is not None

    def _bound(self) -> Callable[..., Any]:
        with self._lock:
            if self._ask is None:
                from g3o.common.jev_client import client_from_credentials
                from g3o.run.presweep.stage_page_code import jev_ask

                self._ask = jev_ask(client_from_credentials(self._credentials, model=self._model))
            return self._ask

    def __call__(self, state: Any, questions: Any) -> Any:
        return self._bound()(state, questions)

    def __repr__(self) -> str:  # never render key material
        return f"LazyJevAsk(model={self._model!r}, constructed={self.constructed})"


def anthropic_sdk_client(api_key: str) -> Any:
    """An ``anthropic.Anthropic`` client given the run's resolved key (the SDK is imported here only)."""
    import anthropic

    return anthropic.Anthropic(api_key=api_key)


class LazyExtractor:
    """The extractor ``extract_fn``: ``AnthropicExtractorClient.create``; the SDK client is built on first use."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Any = None
        self._lock = threading.Lock()

    @property
    def constructed(self) -> bool:
        return self._client is not None

    def _bound(self) -> Any:
        with self._lock:
            if self._client is None:
                from g3o.extract.anthropic_client import AnthropicExtractorClient

                self._client = AnthropicExtractorClient(anthropic_sdk_client(self._api_key))
            return self._client

    def __call__(self, job: Any) -> Any:
        return self._bound().create(job)

    def __repr__(self) -> str:  # never render key material
        return f"LazyExtractor(constructed={self.constructed})"


def x35_entail_fn(settings: Any, credentials: ResolvedCredentials) -> Callable[..., Any]:
    """The X35 ``entail_fn``: ``support_check.run_entailment``, the only X35 entry.

    It refuses every call (no approved X35 binding exists; PI ruling 59 b), and
    ``orchestrator._require_v27_dispatch`` refuses it on entry. Lift together with the
    TODO in ``support_check.run_entailment``.
    """
    del settings, credentials
    from g3o.common import support_check

    return support_check.run_entailment


def perpage_inputs_builder(config: Any) -> Callable[..., Any] | None:
    """The per-page inputs builder: None, the default builder over the stored scrape artifacts (D1 a).

    Refused on entry while ``perpage_inputs_v27.MISSING_PRODUCERS`` is non-empty (PI ruling 36 a).
    """
    del config
    return None


def follow_fetch(config: Any) -> Callable[[str], Any]:
    """The T-025 follow leg's fetch: ``stage_follow.polite_fetch`` configured as Stage 4 scrapes.

    A run-scoped robots cache (when ``scrape_respect_robots``) and host throttle; the
    scrape options are the config's Stage 4 ones. Builds no connection: robots files
    and pages are fetched only when the follow leg calls it.
    """
    from g3o.run.presweep.stage_follow import polite_fetch
    from g3o.scrape.politeness import HostThrottle, RobotsCache

    throttle = HostThrottle(config.scrape_host_delay_seconds)
    robots = RobotsCache(throttle=throttle) if config.scrape_respect_robots else None
    return polite_fetch(
        robots, throttle,
        prefer_render_on_empty=True,
        prefer_render_on_download_failure=config.scrape_render_on_download_failure,
        prefer_unlocker_on_block=config.scrape_unlocker_on_block,
        prefer_unlocker_on_empty=config.scrape_unlocker_on_empty,
        empty_page_min_chars=config.empty_page_min_chars,
    )


def build_v27_dispatch(config: Any, credentials: ResolvedCredentials) -> Any:
    """The ``V27Dispatch`` of a v2.7 run with no injected one, from config and the resolved credentials.

    Refuses (``ValueError``) an unset or incomplete ``config.v27_runtime`` and a missing
    jev (TypeSafe) or extractor (Anthropic) key. Constructs no client. The entry
    refusals of ``orchestrator._require_v27_dispatch`` (59 b, 36 a, the binding
    checks) still run on the result.
    """
    from g3o.run.presweep.orchestrator import V27Dispatch

    settings = runtime_settings(config)
    missing = [f"{var} ({use})" for var, use, present in (
        (TYPESAFE_ENV_VAR, "jev: the v2.7 per-page stage and v2.7 Stage 6", credentials.has_typesafe),
        (ANTHROPIC_ENV_VAR, "the v2.7 extractor", credentials.has_anthropic),
    ) if not present]
    if missing:
        raise ValueError(f"pipeline_version='v2.7' is refused before any work: {', '.join(missing)} is not set "
                         "(pass it in Credentials or the environment)")
    return V27Dispatch(
        settings=settings,
        jev_ask_fn=LazyJevAsk(credentials, settings.jev_model),
        extract_fn=LazyExtractor(credentials.anthropic_api_key or ""),
        entail_fn=x35_entail_fn(settings, credentials),
        perpage_inputs=perpage_inputs_builder(config),
        follow_fetch=follow_fetch(config),
    )


__all__ = ["LazyExtractor", "LazyJevAsk", "anthropic_sdk_client", "build_v27_dispatch", "follow_fetch",
           "perpage_inputs_builder", "runtime_settings", "x35_entail_fn"]
