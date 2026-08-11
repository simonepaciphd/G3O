"""Per-call API credentials — the single place a provider key is resolved.

Run API spec v0.1 (2026-08-02) §3. Before this module, :mod:`g3o.common.config`
resolved ``SERPER_API_KEY`` / ``OPENAI_API_KEY`` into **module-level constants at
import time**, which made a per-call key impossible: everything in the process
shared whatever the environment held when the first import happened, so two runs
in one process could not use two different grants' keys. Those constants survive
for one release as a deprecation shim with no in-repo consumers (§3.2, enforced
by ``tests/test_credentials.py``); every code path that needs key material now
takes a :class:`ResolvedCredentials` explicitly, and resolution happens per call.

Precedence, uniform for both providers (§3.1): explicit :class:`Credentials`
field -> process environment -> unset. "Unset" behaves exactly as it did before
this module existed — mock/refuse logic in :mod:`g3o.discovery.serper_client`,
a raise in :mod:`g3o.common.batch_client`.

Secrecy (§3.3, hard): key material never reaches a manifest, event, state file,
log line, receipt, or exception. Both dataclasses below therefore define their
own ``__repr__``: a stock dataclass repr puts the key into every traceback and
log line that happens to carry the object, which is precisely the leak §3.3
forbids. Telemetry gets :meth:`ResolvedCredentials.telemetry` — source,
``sha256(key)[:8]``, and the operator's label, nothing else.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

# Environment variable names. Named here (not in config.py) so the resolver is
# the only module that has to know how a key reaches the process.
OPENAI_ENV_VAR = "OPENAI_API_KEY"
SERPER_ENV_VAR = "SERPER_API_KEY"

# Fingerprint width. 8 hex chars = 32 bits: enough to tell "key A" from "key B"
# in a manifest or a server-side batch listing, far too little to attack the key
# with. Spec §3.3 pins the value; do not widen it without changing the spec.
FINGERPRINT_CHARS = 8

Source = Literal["explicit", "env", "unset"]


def fingerprint(key: str | None) -> str | None:
    """``sha256(key)[:8]`` — the only representation of a key that may be recorded.

    Returns ``None`` for an unset (or empty) key so telemetry records a null
    rather than the hash of an empty string, which would look like a real key.
    """
    if not key:
        return None
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:FINGERPRINT_CHARS]


def _redact(key: str | None) -> str:
    """Repr-safe rendering of one key: its fingerprint, never its material."""
    fp = fingerprint(key)
    return f"set(fp={fp})" if fp else "unset"


@dataclass(frozen=True, repr=False)
class Credentials:
    """Caller-supplied keys for one run (spec §1).

    Every field is optional: ``None`` (or empty) means "fall back to the
    environment", so ``Credentials()`` reproduces the pre-spec behavior of
    reading both keys from the process environment.

    ``label`` is a human tag for the key bundle — e.g. ``"key-B-grant"``. It is
    the operator's note about *which* key paid for a run, and it appears in
    telemetry next to the fingerprint.
    """

    openai_api_key: str | None = None
    serper_api_key: str | None = None
    label: str | None = None

    def __repr__(self) -> str:  # §3.3 — never render key material
        return (
            f"Credentials(openai={_redact(self.openai_api_key)}, "
            f"serper={_redact(self.serper_api_key)}, label={self.label!r})"
        )


@dataclass(frozen=True, repr=False)
class ResolvedCredentials:
    """The keys a run will actually use, plus where each one came from.

    Produced once by :func:`resolve` and threaded explicitly from the
    orchestrator down to the client constructors (§3.2). ``*_source`` records
    the precedence branch that won, which is what makes a manifest able to say
    "this run used an explicitly passed key", not merely "a key was present".
    """

    openai_api_key: str | None
    serper_api_key: str | None
    openai_source: Source
    serper_source: Source
    label: str | None = None

    @property
    def openai_fingerprint(self) -> str | None:
        return fingerprint(self.openai_api_key)

    @property
    def serper_fingerprint(self) -> str | None:
        return fingerprint(self.serper_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_serper(self) -> bool:
        return bool(self.serper_api_key)

    def telemetry(self) -> dict[str, dict[str, str | None]]:
        """The ``credentials`` block of the run manifest (§4.1), key-free.

        Shape is fixed by the published fixture
        ``tests/fixtures/run_contract/manifest.json`` — Katon's loader is written
        against it, so the keys here are a contract, not an implementation
        detail.

        The label: spec §1 gives :class:`Credentials` **one** ``label`` while the
        manifest block has a per-provider slot, so one label cannot distinguish
        the two providers. It is emitted for each provider that actually resolved
        a key and ``null`` for one that did not — a tag naming a key is
        meaningless against a provider that has none. (Flagged to the PI: the
        fixture's example, where two env-sourced keys carry different labels, is
        not reachable through a single-label ``Credentials``.)
        """
        return {
            "openai": self._provider_block(self.openai_api_key, self.openai_source),
            "serper": self._provider_block(self.serper_api_key, self.serper_source),
        }

    def _provider_block(self, key: str | None, source: Source) -> dict[str, str | None]:
        return {
            "source": source,
            "fingerprint": fingerprint(key),
            "label": self.label if key else None,
        }

    def __repr__(self) -> str:  # §3.3 — never render key material
        return (
            f"ResolvedCredentials(openai={_redact(self.openai_api_key)}"
            f"/{self.openai_source}, serper={_redact(self.serper_api_key)}"
            f"/{self.serper_source}, label={self.label!r})"
        )


def _resolve_one(
    explicit: str | None, env_var: str, env: Mapping[str, str]
) -> tuple[str | None, Source]:
    """Apply §3.1 precedence to one provider.

    An empty string counts as absent on both branches: an empty environment
    variable is how a shell spells "unset", and every pre-spec consumer tested
    the key for truthiness (``if not config.SERPER_API_KEY``), so treating ``""``
    as unset keeps behavior identical rather than newly sending an empty key to
    a provider.
    """
    if explicit:
        return explicit, "explicit"
    from_env = env.get(env_var) or None
    if from_env:
        return from_env, "env"
    return None, "unset"


def resolve(
    credentials: Credentials | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> ResolvedCredentials:
    """Resolve ``credentials`` against the environment (§3.1).

    ``env`` defaults to :data:`os.environ` **read at call time** — that lateness
    is the whole point of this module. ``.env`` support is unchanged: importing
    :mod:`g3o.common.config` still calls ``load_dotenv()``, which populates the
    process environment that this function then reads.
    """
    creds = credentials or Credentials()
    environ: Mapping[str, str] = os.environ if env is None else env
    openai_key, openai_source = _resolve_one(
        creds.openai_api_key, OPENAI_ENV_VAR, environ
    )
    serper_key, serper_source = _resolve_one(
        creds.serper_api_key, SERPER_ENV_VAR, environ
    )
    return ResolvedCredentials(
        openai_api_key=openai_key,
        serper_api_key=serper_key,
        openai_source=openai_source,
        serper_source=serper_source,
        label=creds.label,
    )


__all__ = [
    "FINGERPRINT_CHARS",
    "OPENAI_ENV_VAR",
    "SERPER_ENV_VAR",
    "Credentials",
    "ResolvedCredentials",
    "Source",
    "fingerprint",
    "resolve",
]
