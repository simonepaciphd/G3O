#!/usr/bin/env python3
"""T-041 mocked end-to-end: the real ``run_v27_dispatch`` over a few T-041 fixtures, every provider a fake. FREE.

What is real: the T-041 runner's live path (``fixture_run_t041.run_live``: materialise, the
follow leg over the fixture's own pages, compare, journal pricing, X35 summary), the production
entry (``v27_entry.build_v27_dispatch`` from a v2.7 runtime and the live gates of
``fixture_run_t041.require_live_gates``), ``orchestrator.run_v27_dispatch`` with the default
per-page builder (D1 a), the instrument binding to the signed codebook, both stages and the
storage writers.

What is fake (the seams the existing tests use, ``tests/test_e2e_perpage_v27.py``,
``tests/test_perpage_providers_v27.py``, ``tests/test_orchestrator_v27_dispatch.py``): the jev
``ask_fn`` (``FakeJev``), the X35 ``entail_fn`` (``FakeEntail``) and the extractor ``extract_fn``
(:class:`FixtureExtractor`, the providers-test ``FakeExtractor`` / ``FakeExtractorS6`` answering
from the page parts shown in the job instead of a declared world). The keys are dummy strings.

Guards: the paid-key variables are removed from the process environment and ``.env`` loading is
disabled before ``g3o`` is imported; every socket connect / DNS lookup raises and is counted;
the real client constructors (Anthropic SDK, TypeSafe jev, OpenAI, Serper) are replaced by
functions that raise and are counted. Any count above zero fails the run.

Exit code 0 only when every check passes. Outputs go to ``--out-dir`` (default: a fresh
temporary folder): the run directories, ``t041-mock-results.json`` and ``t041-mock-checks.json``.

Example:
  python scripts/t041_mock_e2e.py --out-dir <folder>
  python scripts/t041_mock_e2e.py --fixture v27-real-01   # a real fixture needs $G3O_DRIVE_ROOT
"""

from __future__ import annotations

import os
import re
import socket
import sys
from pathlib import Path

# --- guards, before any g3o import -------------------------------------------------------
_PAID_ENV = re.compile(r"(_API_KEY|DATABASE_URL|BRIGHTDATA|UNLOCKER|SERPER|ANTHROPIC|OPENAI|TYPESAFE)", re.I)
REMOVED_ENV = sorted(k for k in os.environ if _PAID_ENV.search(k))
for _k in REMOVED_ENV:
    del os.environ[_k]

import dotenv  # noqa: E402

dotenv.load_dotenv = lambda *a, **k: False  # g3o.common.config calls it at import

NETWORK_ATTEMPTS: list[str] = []
CLIENT_ATTEMPTS: list[str] = []


class NetworkBlocked(OSError):
    """A real network call was attempted (always a failure of this script)."""


def _blocked(name):
    def block(*args, **kwargs):
        NETWORK_ATTEMPTS.append(f"{name}{args[:2]!r}")
        raise NetworkBlocked(f"t041_mock_e2e: network blocked ({name})")
    return block


socket.socket.connect = _blocked("socket.connect")  # type: ignore[method-assign]
socket.socket.connect_ex = _blocked("socket.connect_ex")  # type: ignore[method-assign]
socket.create_connection = _blocked("socket.create_connection")  # type: ignore[assignment]
socket.getaddrinfo = _blocked("socket.getaddrinfo")  # type: ignore[assignment]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402
from collections import Counter  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

from g3o.run import fixture_run_t041 as fr  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "v27"
#: Default fixtures: a one-activity page, a three-activity page, a followed link that fails to fetch
#: (the follow leg), a long multi-part page, an A-020 date page, and a three-page real institution
#: (cross-page relation, merge and the Stage 6 quote step; read from the Drive store, so it is
#: dropped with a note when no Drive root is set).
DEFAULT_FIXTURES = ("v27-syn-A011-01", "v27-syn-A003-01", "v27-syn-A004-05", "v27-syn-A021-01", "v27-syn-A020-01",
                    "v27-real-40")
#: The v2.7 model bindings (jev-1.13.0; extractor and X35 on claude-haiku-5-5, PI ruling 139 a).
#: The other fields are this mock's own; the paid run's ``--runtime`` file is the PI's.
MOCK_RUNTIME = {"jev_model": "jev-1.13.0", "extractor_model": "claude-haiku-5-5", "extractor_effort": "low",
                "extractor_max_tokens": 8000, "reserved_tokens": 0, "reference_year": 2026,
                "approval_reference": "T-041 mocked e2e: fake providers, no provider execution",
                "x35_model": "claude-haiku-5-5"}
PASS1, PASS2, STAGE6_QUOTE = "5_extract_v27", "5b_pass2_support_v27", "6_quote_v27"
#: The four token counts journal pricing needs (cost_monitor.EXTRACTOR_USAGE_KEYS; ruling 58 a).
USAGE = {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
#: Mock-only page title for a fixture page that has none (see :func:`_titled`).
MOCK_TITLE = "Mock page title (t041_mock_e2e)"
_PART_RE = re.compile(r'<part id="([^"]+)">\n(.*?)\n</part>', re.S)
_SNIPPET = 160


def _guard_clients() -> None:
    """Replace every real client constructor with one that raises (and is counted)."""
    from g3o.common import jev_client
    from g3o.run.presweep import v27_entry

    def refuse(name):
        def boom(*args, **kwargs):
            CLIENT_ATTEMPTS.append(name)
            raise RuntimeError(f"t041_mock_e2e: real client constructor called: {name}")
        return boom

    v27_entry.anthropic_sdk_client = refuse("v27_entry.anthropic_sdk_client")
    jev_client.client_from_credentials = refuse("jev_client.client_from_credentials")
    try:
        import anthropic
        anthropic.Anthropic = refuse("anthropic.Anthropic")  # type: ignore[misc]
    except ImportError:
        pass
    try:
        import openai
        openai.OpenAI = refuse("openai.OpenAI")  # type: ignore[misc]
    except ImportError:
        pass


def _snippet(text: str) -> str:
    """A verbatim quote from a part: its first sentence, at most :data:`_SNIPPET` characters."""
    body = text.strip()
    cut = body.find(". ")
    end = cut + 1 if 0 < cut < _SNIPPET else min(len(body), _SNIPPET)
    return body[:end].strip()


class FixtureExtractor:
    """The providers-test ``FakeExtractor`` / ``FakeExtractorS6``, reading the page parts from the job.

    Pass 1: every quote task gets a verbatim snippet of its part; the link task cites every stored
    link; the activity task declares one activity in the first non-blank part, with a name, a tool
    and a page-stated developer (so ``core.developer`` goes through the quote step, A8.1 a). Pass 2:
    every quote task gets its part's snippet, every field task ``None``. Stage 6 quote step: the first
    shown quote, copied. Records each job and the system prompt it carried.
    """

    def __init__(self, model: str) -> None:
        self.model = model
        self.jobs: list[Any] = []
        self.parts: dict[str, dict[str, str]] = {}  # page_id -> part id -> text, from pass 1

    def __call__(self, job: Any) -> Any:
        from g3o.extract.anthropic_client import ExtractorResult
        from g3o.extract.request_v27 import field_name

        self.jobs.append(job)
        stage = job.metadata["stage"]
        user = job.params["messages"][0]["content"]
        if stage == STAGE6_QUOTE:
            rows = json.loads(user.split("QUOTES:\n", 1)[1].split("\n\nTASK:\n", 1)[0])
            payload: dict[str, Any] = {"quote_id": rows[0]["quote_id"], "quote": rows[0]["text"]}
        else:
            parts = {pid: text for pid, text in _PART_RE.findall(user)}
            page_id = job.metadata["page_id"]
            if stage == PASS1:
                self.parts.setdefault(page_id, {}).update(parts)
            known = self.parts.get(page_id, parts)
            tasks = json.loads(user.split("\nTASKS:\n", 1)[1])
            quotes = [{"task_id": t["task_id"], "part_id": t["part_id"],
                       "quote": _snippet(known.get(t["part_id"], "")) or None} for t in tasks["quote_tasks"]]
            if stage == PASS1:
                payload = {"quotes": quotes, "links": [], "activities": [], "publication_date": None}
                first = next(((pid, t) for pid, t in parts.items() if t.strip()), None)
                if tasks.get("link_task") and first is not None and "\nSTORED LINKS:\n" in user:
                    block = user.split("\nSTORED LINKS:\n", 1)[1].split("\n\nTASKS:\n", 1)[0]
                    for line in block.splitlines():
                        link = json.loads(line)
                        payload["links"].append({"link_id": link["link_id"], "part_id": first[0],
                                                 "quote": _snippet(first[1])})
                if tasks["activity_task"] is not None and first is not None:
                    wanted = set(tasks["activity_task"]["fields"])
                    anchor = _snippet(first[1])
                    given = {field_name("core.activity_name"): "Mock GenAI activity",
                             field_name("core.tool_name"): "Mock tool",
                             field_name("core.developer"): "Mock Developer Ltd"}
                    fields = [{"field": f, "value": v, "part_id": first[0], "supporting_text": anchor}
                              for f, v in given.items() if f in wanted]
                    fields += [{"field": f, "value": None, "part_id": None, "supporting_text": None}
                               for f in sorted(wanted - set(given))]
                    payload["activities"].append({"part_id": first[0], "start_text": anchor[:40],
                                                  "end_text": anchor[-40:], "fields": fields})
            else:
                assert stage == PASS2, stage
                payload = {"quotes": quotes,
                           "fields": [{"task_id": t["task_id"], "value": None, "part_id": None,
                                       "supporting_text": None} for t in tasks["field_tasks"]]}
        n = len(self.jobs)
        return ExtractorResult(job.custom_id, True, json.dumps(payload), None, self.model, f"msg-mock-{n}",
                               f"req-mock-{n}", "end_turn", dict(USAGE))

    def systems(self, stage: str) -> set[str]:
        return {_system_text(j.params["system"]) for j in self.jobs if j.metadata["stage"] == stage}

    def stages(self) -> Counter:
        return Counter(j.metadata["stage"] for j in self.jobs)

    # the batch client surface (never used: T-041 is sync, DP-030)
    def submit_batch(self, jobs):  # pragma: no cover
        raise AssertionError("batch submit in a sync run")

    batch_status = batch_results = submit_batch


def _titled(pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """MOCK-ONLY: give each fetched synthetic page without a title :data:`MOCK_TITLE`.

    ``source_row_v27`` refuses an empty ``RenderedPage.title`` (the first-heading fallback is
    unproduced, PI ruling 39 a), which holds the institution at the per-page stage before Stage 6.
    Since PI ruling 4 a (2026-11-17) every synthetic fixture page carries a title
    (``build_synthetic.page``), so this is a guard that should find nothing; the note printed in
    :func:`main` reports the count. ``--keep-untitled`` turns it off.
    """
    out, n = [], 0
    for p in pages:
        if p.get("record") is None and p.get("fetch_ok") and not p.get("title"):
            p, n = {**p, "title": MOCK_TITLE}, n + 1
        out.append(p)
    return out, n


def _system_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    return "".join(block.get("text", "") for block in system)


class _Relations(dict):
    """FakeJev's relation answers for any pair of activity names."""

    def __missing__(self, key):
        return "same_activity" if key[0] == key[1] else "distinct_action"

    def __bool__(self):  # FakeJev keeps ``relations or {}``: an empty mapping would be replaced
        return True


def _fakes(model: str) -> tuple[Any, Any, FixtureExtractor]:
    from g3o.classify import jev_page_code as jpc
    from tests.test_e2e_perpage_v27 import FakeJev
    from tests.test_perpage_providers_v27 import FakeEntail

    class UsageEntail(FakeEntail):
        """``FakeEntail`` that also reports usage, as the live ``LazyX35`` does (so X35 is priced)."""

        def entail_with_usage(self, question, text):
            return self(question, text), dict(USAGE)

    from g3o.classify.questions.v27 import load_set

    pooled = {q["item_id"]: q["question_id"] for q in load_set("activity")["questions"] if q.get("part") is None}
    # page complete (so stored links get a link task and the follow leg follows them); the pooled
    # Stage 6 answers of tests/test_e2e_stage6_v27.py (non-exempt, so the Stage 6 quote step runs)
    answers = {jpc.VERDICT: "confirms_activity", jpc.COMPLETE: "yes", "core.disclosure_form": "informal_official",
               "core.activity_type": "internal_operational", "core.action_type": "deployment",
               **{pooled[i]: v for i, v in (("core.adoption_stage", "pilot"), ("core.permanent_pilot", "yes"))
                  if i in pooled}}
    return FakeJev(answers, _Relations()), UsageEntail(), FixtureExtractor(model)


def _dispatch(jev: Any, entail: Any, extract: Any, runtime: dict[str, Any]) -> Any:
    """The production entry's dispatch (dummy keys), its three provider calls swapped for fakes,
    then the T-041 live gates (``require_live_gates``: X35 stub refusal, binding pins, ruling 36 a,
    sync mode)."""
    from g3o.common.credentials import Credentials, resolve
    from g3o.run.presweep.v27_entry import build_v27_dispatch

    config = SimpleNamespace(v27_runtime=dict(runtime), v27_extractor_mode="no_batch",
                             scrape_host_delay_seconds=1.0, scrape_respect_robots=True,
                             scrape_render_on_download_failure=False, scrape_unlocker_on_block=False,
                             scrape_unlocker_on_empty=False, empty_page_min_chars=0)
    creds = resolve(Credentials(anthropic_api_key="mock-not-a-key", typesafe_api_key="mock-not-a-key"), env={})
    real = build_v27_dispatch(config, creds)
    mocked = dataclasses.replace(real, jev_ask_fn=jev, extract_fn=extract, batch_client=extract, entail_fn=entail)
    return fr.require_live_gates(mocked), real


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def __call__(self, name: str, ok: bool, detail: Any = "") -> None:
        self.rows.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail != "" else ""))

    @property
    def ok(self) -> bool:
        return bool(self.rows) and all(r["status"] == "PASS" for r in self.rows)


def _storage_checks(check: Checks, run_root: Path, fixture_ids: list[str]) -> None:
    """Every written ``6_storage.json`` re-validated against its bound instrument (r16), plus the
    r16 item checks on the stored activity rows."""
    from g3o.codebook.r16_candidate import STAGE_AS_OF_BASIS_CODES, r16_active
    from g3o.common.instrument import load_instrument
    from g3o.common.storage import StorageEnvelope
    from g3o.persist.stage6_adapters import STORAGE_ARTIFACT

    n_storage, n_acts, bad, developer_coders, basis_values = 0, 0, [], Counter(), Counter()
    signed = set()
    for fid in fixture_ids:
        run_dir = run_root / fid
        for path in sorted(run_dir.glob(f"institutions/*/*/{STORAGE_ARTIFACT}")):
            n_storage += 1
            try:
                env = StorageEnvelope.load(path, run_dir / "final" / "instruments", artifact_root=run_dir)
            except Exception as exc:
                bad.append(f"{fid}: {type(exc).__name__}: {exc}")
                continue
            data = env.data
            record = load_instrument(run_dir / "final" / "instruments", data["setup_pointer"])
            signed.add(_instrument_codebook(record))
            for row in data["activities"].values():
                n_acts += 1
                values = row.get("values") or row
                basis_values[str(values.get("core.stage_as_of_basis"))] += 1
                for coder in _coders_for(row, data, "core.developer"):
                    developer_coders[coder] += 1
    check("storage: every written 6_storage.json re-validates against its bound instrument",
          n_storage > 0 and not bad, f"{n_storage} envelope(s), {n_acts} activity row(s)" + (f"; {bad}" if bad else ""))
    check("codebook: the generated tree is r16 and each instrument names it", r16_active() and bool(signed)
          and all(s in (None, _r16()) for s in signed), sorted(str(s) for s in signed))
    check("core.stage_as_of_basis: every stored activity value is an r16 step code",
          n_acts > 0 and set(basis_values) <= set(STAGE_AS_OF_BASIS_CODES), dict(basis_values))
    check("core.developer: coded by the quote step (Q200 a / A8.1 a)",
          bool(developer_coders) and set(developer_coders) == {"quote_step"}, dict(developer_coders))


def _r16() -> str:
    """The codebook the generated tree is built from: r16, or a later revision that carries the r16 fields."""
    from g3o.codebook.r16_candidate import active_codebook_sha256
    return active_codebook_sha256()


def _instrument_codebook(record: Any) -> str | None:
    """The codebook SHA256 an instrument record names (searched by key, as its layout nests it)."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("codebook_sha256", "codebook_hash") and isinstance(v, str):
                    found.append(v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(record)
    return found[0] if found else None


def _coders_for(row: dict[str, Any], data: dict[str, Any], item: str) -> list[str]:
    """The coder types of ``item``'s coder records attached to one stored row."""
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("item_id") == item and "coder_type" in node:
                out.append(node["coder_type"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fixture", action="append", default=None, help="fixture id (repeatable); default: a fixed five")
    ap.add_argument("--out-dir", type=Path, default=None, help="output folder (default: a fresh temp folder)")
    ap.add_argument("--runtime", type=Path, default=None,
                    help="JSON object of every RuntimeSettings field (the paid run's file); default MOCK_RUNTIME")
    ap.add_argument("--keep-untitled", action="store_true",
                    help="do not add the mock-only page title (shows the ruling 39 a hold the paid run would hit)")
    ap.add_argument("--drive", default=None, help=f"G3O Drive root (real fixtures only); default ${fr.DRIVE_ENV}")
    args = ap.parse_args(argv)
    _guard_clients()
    check = Checks()
    check("environment: paid-key variables removed before import", not any(_PAID_ENV.search(k) for k in os.environ),
          f"removed {len(REMOVED_ENV)} variable(s)")

    out_dir = args.out_dir or Path(tempfile.mkdtemp(prefix="t041-mock-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    run_root = fr.fresh_run_root(out_dir / "runs", fr.utc_stamp())
    drive = fr.drive_root(args.drive)
    wanted = args.fixture or [f for f in DEFAULT_FIXTURES if drive is not None or not f.startswith("v27-real-")]
    if wanted != list(args.fixture or DEFAULT_FIXTURES):
        print(f"note: no Drive root (${fr.DRIVE_ENV}): the real default fixture is left out")
    fixtures = fr.select_fixtures(fr.load_fixtures(FIX), fr.GROUPS, wanted)
    missing = sorted(set(wanted) - {f["fixture_id"] for f in fixtures})
    if missing:
        print(f"error: unknown fixtures {missing}", file=sys.stderr)
        return 2
    if any(fr.fixture_group(f) == fr.GROUP_REAL for f in fixtures) and drive is None:
        print(f"error: a real fixture needs the Drive root (${fr.DRIVE_ENV})", file=sys.stderr)
        return 2
    ft = fr.load_fixture_text_module(FIX)
    pages = {f["fixture_id"]: fr.fixture_pages(f, fixture_text=ft, drive=drive) for f in fixtures}
    untitled = sum(1 for ps in pages.values() for p in ps if p.get("fetch_ok") and not p.get("title"))
    if not args.keep_untitled:
        titled = {fid: _titled(ps) for fid, ps in pages.items()}
        pages = {fid: ps for fid, (ps, _) in titled.items()}
    print(f"note: {untitled} fetched fixture page(s) have no title"
          + ("" if args.keep_untitled else f"; mock-only title {MOCK_TITLE!r} added to the synthetic ones"))

    if args.runtime is not None:
        runtime = json.loads(args.runtime.read_text(encoding="utf-8"))
        print(f"runtime: {args.runtime.name} sha256 {hashlib.sha256(args.runtime.read_bytes()).hexdigest()}")
    else:
        runtime = dict(MOCK_RUNTIME)
        print("runtime: the mock's own MOCK_RUNTIME (no --runtime given)")
    jev, entail, extract = _fakes(runtime["extractor_model"])
    dispatch, real = _dispatch(jev, entail, extract, runtime)
    check("entry: the production dispatch's real calls are the lazy clients, none constructed",
          not real.jev_ask_fn.constructed and not real.extract_fn.constructed
          and not getattr(real.entail_fn, "constructed", True) and real.perpage_inputs is None,
          f"jev={real.jev_ask_fn!r} extractor={real.extract_fn!r} x35={real.entail_fn!r}")
    check("entry: require_live_gates passed (X35 gate, binding pins, ruling 36 a) and forced no_batch",
          dispatch.extractor_mode == "no_batch")

    from g3o.run.presweep import orchestrator

    calls: list[str] = []
    real_run = orchestrator.run_v27_dispatch

    def traced(run_dir, sample, scraped, v27, **kw):  # the real function, its calls counted
        calls.append(run_dir.name)
        return real_run(run_dir, sample, scraped, v27, **kw)

    run = fr.run_live(fixtures, dispatch=dispatch, run_root=run_root, max_usd=1e9,
                      page_loader=lambda f: pages[f["fixture_id"]], searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED,
                      access_date="2026-11-17", run_fn=traced, cost_fn=fr.journal_cost(dispatch),
                      continue_on_error=True)
    results = run["results"]
    ids = [f["fixture_id"] for f in fixtures]
    print()
    for r in results:
        s = r.get("summary") or {}
        print(f"  {r['fixture_id']}: status={r.get('status')} error={r.get('error')} "
              f"perpage ready/held/failed={s.get('n_perpage_ready')}/{s.get('n_perpage_held')}/"
              f"{s.get('n_perpage_failed_pages')} stage6 written/held/failed={s.get('n_stage6_written')}/"
              f"{s.get('n_stage6_held')}/{s.get('n_stage6_failed')} x35={r.get('x35', {}).get('n_calls')} "
              f"cost(fake tokens)={r.get('cost_usd')}")
    print()

    check("dispatch: the real run_v27_dispatch ran once per fixture", calls == ids, calls)
    errors = {r["fixture_id"]: r["error"] for r in results if r.get("error")}
    check("dispatch: no fixture stopped with an error", not errors, errors)
    summaries = [r.get("summary") or {} for r in results]
    check("per-page stage: ran and passed institutions on to Stage 6",
          all(s.get("n_perpage_ready", 0) >= 1 for s in summaries),
          [s.get("n_perpage_ready") for s in summaries])
    check("Stage 6: wrote every fixture institution", all(s.get("n_stage6_written", 0) >= 1 for s in summaries),
          [s.get("n_stage6_written") for s in summaries])
    stages = extract.stages()
    check("extractor: pass 1, pass 2 and the Stage 6 quote step were each called",
          all(stages.get(s, 0) > 0 for s in (PASS1, PASS2, STAGE6_QUOTE)), dict(stages))
    check("jev: per-page and Stage 6 questions answered", len(jev.calls) > 0, f"{len(jev.calls)} call(s)")
    check("X35: called through the fake entail_fn", len(entail.calls) > 0, f"{len(entail.calls)} call(s)")

    follow_ids = [f["fixture_id"] for f in fixtures if any(p.get("links") for p in pages[f["fixture_id"]])]
    followed = {}
    for fid in follow_ids:
        state = fr.load_run_telemetry(run_root / fid)["follow_state"]
        followed[fid] = None if state is None else {k: v for k, v in state.items() if k != "format"}
    check("follow leg: ran on every fixture with stored links (fixture fetch, no network)",
          not follow_ids or all(followed.values()), json.dumps(followed, default=str)[:400])

    from g3o.common.instrument import sha256_text
    from g3o.run.presweep.perpage_providers_v27 import PASS1_SYSTEM_SHA256, PASS2_SYSTEM_SHA256

    p1 = {sha256_text(s) for s in extract.systems(PASS1)}
    p2 = {sha256_text(s) for s in extract.systems(PASS2)}
    check("PASS1: every pass-1 job's system prompt hashes to PASS1_SYSTEM_SHA256", p1 == {PASS1_SYSTEM_SHA256},
          sorted(p1))
    check("PASS2: every pass-2 job's system prompt hashes to PASS2_SYSTEM_SHA256", p2 == {PASS2_SYSTEM_SHA256},
          sorted(p2))
    from g3o.extract.request_v27 import field_name

    dev_field = field_name("core.developer")
    asked = [j for j in extract.jobs if j.metadata["stage"] == PASS1 and f'"{dev_field}"' in
             j.params["messages"][0]["content"].split("\nTASKS:\n", 1)[1]]
    check("core.developer: asked in the pass-1 activity task (A8.1 a)", bool(asked),
          f"{len(asked)} pass-1 job(s) list field {dev_field!r}")
    _storage_checks(check, run_root, ids)

    check("network: no real connection or DNS lookup attempted", not NETWORK_ATTEMPTS, NETWORK_ATTEMPTS[:5])
    check("clients: no real provider client constructed", not CLIENT_ATTEMPTS and not real.jev_ask_fn.constructed
          and not real.extract_fn.constructed, CLIENT_ATTEMPTS[:5])

    (out_dir / "t041-mock-results.json").write_text(json.dumps(run, indent=1, default=str), encoding="utf-8")
    (out_dir / "t041-mock-checks.json").write_text(json.dumps({
        "ok": check.ok, "fixtures": ids, "run_root": str(run_root), "checks": check.rows,
        "extractor_jobs": dict(stages), "jev_calls": len(jev.calls), "x35_calls": len(entail.calls),
        "network_attempts": NETWORK_ATTEMPTS, "client_attempts": CLIENT_ATTEMPTS,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=1), encoding="utf-8")
    n_fail = sum(r["status"] == "FAIL" for r in check.rows)
    print(f"\nmock e2e: {len(check.rows) - n_fail}/{len(check.rows)} checks PASS; outputs in {out_dir}")
    return 0 if check.ok else 1


if __name__ == "__main__":
    sys.exit(main())
