"""Unit tests for the T-002 spike helpers (chunker, cap guard, script bytes, proxy wording). Free; no network."""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proxy_questions as PQ  # noqa: E402
import t002_core as C  # noqa: E402

# ---- chunker ----

@pytest.mark.parametrize("text", ["", "abc", "a" * 100, "日本語のテキスト" * 50, "ภาษาไทย" * 40, "mixed 中文 ไทย é" * 30])
def test_chunks_roundtrip_and_cap(text):
    cap = 64
    parts = C.byte_chunks(text, cap)
    assert "".join(parts) == text
    assert all(C.utf8_len(p) <= cap for p in parts)


def test_chunks_fewest_and_balanced():
    text = "x" * 250
    parts = C.byte_chunks(text, 100)
    assert len(parts) == 3                      # ceil(250 / 100)
    assert max(map(len, parts)) - min(map(len, parts)) <= len(parts)  # balanced up to rounding


def test_chunks_never_split_a_character():
    text = "語" * 10                              # 3 bytes each
    parts = C.byte_chunks(text, 7)
    assert all(p and all(ch == "語" for ch in p) for p in parts)
    assert all(C.utf8_len(p) <= 7 for p in parts)


def test_chunk_cap_from_estimator():
    assert C.chunk_byte_cap() == int(24_000 / 0.3947) == 60_805
    one = "a" * C.chunk_byte_cap()
    assert len(C.byte_chunks(one, C.chunk_byte_cap())) == 1
    assert len(C.byte_chunks(one + "a", C.chunk_byte_cap())) == 2


def test_halve_gives_two_halves():
    parts = C.halve("ab" * 1000)
    assert len(parts) == 2 and "".join(parts) == "ab" * 1000


def test_bad_cap():
    with pytest.raises(ValueError):
        C.byte_chunks("abc", 3)


# ---- cap guard ----

def test_budget_reserve_and_commit():
    b = C.Budget(cap_usd=1.0)
    b.reserve(0.6)
    b.commit(0.5, "J")
    b.reserve(0.5)                               # 0.5 + 0.5 == cap: allowed
    with pytest.raises(C.CapReached):
        b.reserve(0.5000001)
    assert b.by_leg == {"J": 0.5}
    assert b.remaining_usd == pytest.approx(0.5)


def test_budget_resumes_from_spent():
    b = C.Budget(cap_usd=6.0, spent_usd=5.999)
    with pytest.raises(C.CapReached):
        b.reserve(C.jev_upper_bound() * 1000)
    b.reserve(0.0)


def test_upper_bounds_cover_estimates():
    assert C.jev_upper_bound() == pytest.approx(64_000 * 0.042 / 1e6)
    nbytes, out = 80_000, 16_000
    bound = C.haiku_upper_bound(nbytes, out)
    est = C.haiku_cost(nbytes / C.HAIKU_BYTES_PER_TOKEN, 3_000)
    assert bound > est
    assert C.haiku_upper_bound(nbytes, out, batch=True) == pytest.approx(bound / 2)


def test_negative_bound_rejected():
    with pytest.raises(ValueError):
        C.Budget(1.0).reserve(-1)


# ---- scripts and question packing ----

def test_script_bytes():
    sb = C.script_bytes("Ab 1 中文 ไทย é")
    assert sb["latin"] == 2 + 2                   # A, b, é (2 bytes)
    assert sb["cjk"] == 6 and sb["thai"] == 9
    assert C.dominant_script("ภาษาไทย abc") == "thai"
    assert C.dominant_script("123 ...") == "latin"


def test_pack_questions_respects_budget():
    qs = {f"q{i}": {"instructions": "x" * 1000, "criteria": {"a": "b"}} for i in range(10)}
    per = C.est_jev_tokens({}, {"q0": qs["q0"]}) - C.est_jev_tokens({}, {})
    groups = C.pack_questions(qs, budget_tokens=per * 3)
    assert [len(g) for g in groups] == [3, 3, 3, 1]


# ---- proxy wording is verbatim ----

def _strings(path):
    src = Path(path).read_text(encoding="utf-8")
    out = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


@pytest.mark.skipif(not Path(PQ.SOURCE_PILOT).exists() or not Path(PQ.SOURCE_UNCLEAR2).exists(),
                    reason="source scripts not reachable")
def test_proxy_text_is_verbatim():
    u, p = _strings(PQ.SOURCE_UNCLEAR2), _strings(PQ.SOURCE_PILOT)
    for v in PQ.VERDICT.values():
        assert v in u
    assert PQ.VERDICT_INSTRUCTIONS in u
    for d in (PQ.FORM, PQ.SCOPE, PQ.CONTENT, PQ.EVAL, PQ.EVAL_TYPES, PQ.CONTENT_CRITERIA, PQ.TYPE_CRITERIA):
        for k, v in d.items():
            assert k in p and v in p
    for s in (PQ.FORM_INSTRUCTIONS, PQ.SCOPE_INSTRUCTIONS, PQ.EVAL_EMPHASIS):
        assert s in p
    assert PQ.EVAL_INSTRUCTIONS.removesuffix(PQ.EVAL_EMPHASIS) in p
    # f-string templates: their literal pieces appear in the source
    for tpl in (PQ.CONTENT_INSTRUCTIONS_TEMPLATE, PQ.TYPE_INSTRUCTIONS_TEMPLATE):
        head, tail = tpl.split("{v}")
        assert head in p and tail in p


def test_cx_question_count_is_19():
    # pilot v2: form, scope, evaluation_documented, 10 content, 6 evaluation types
    assert 2 + 1 + len(PQ.CONTENT) + len(PQ.EVAL_TYPES) == 19


# ---- paid-path orchestration with fake clients (no network, no keys) ----

def _fake_runner(S, out_dir, cap, calls):
    import json as _json
    from types import SimpleNamespace as NS

    class JevAccountError(Exception):
        pass

    def ask(state, qs, client):
        calls["jev"] += 1
        if C.utf8_len(state["page_text"]) > 30_000:
            raise RuntimeError("TypeSafeBadRequestError max_tokens_exceeded")
        pick = {"verdict": "confirms_activity", "disclosure_form": "register_single_institution",
                "evaluation_documented": "results_reported"}
        ans = {k: NS(choice=("same_activity" if "~" in k else pick.get(k, "yes")), confidence=0.9,
                     probabilities={}) for k in qs}
        return NS(answers=ans, input_tokens=1000, output_tokens=0, request_id="jr", response_model="jev-test")

    def create(**params):
        calls["haiku"] += 1
        sch = params["output_config"]["format"]["schema"]
        if "spans" in sch["properties"]:
            req = sch["properties"]["spans"]["items"]["required"]
            body = {"source_publication_date": {"date": "", "quote": ""},
                    "spans": [{k: f"v{i}" for k in req} for i in range(2)]}
        else:
            ids = sch["properties"]["items"]["items"]["properties"]["item"]["enum"]
            body = {"items": [{"item": ids[0], "quotes": ["q1"]}]}
        msg = NS(content=[NS(type="text", text=_json.dumps(body))], usage=NS(input_tokens=5000, output_tokens=800),
                 stop_reason="end_turn", id="m", _request_id="r")
        return NS(parse=lambda: msg, headers={"request-id": "r"})

    store = {}

    def bcreate(requests):
        store["b"] = requests
        return NS(id="b1")

    def bretrieve(bid):
        return NS(processing_status="ended", created_at="t0", ended_at="t1", request_counts="x")

    def bresults(bid):
        for r in store["b"]:
            yield NS(custom_id=r["custom_id"], result=NS(type="succeeded", message=create(**r["params"]).parse()))

    class APIError(Exception):
        pass

    S.OUT_DIR = out_dir
    r = object.__new__(S.Runner)
    r.anthropic = NS(AuthenticationError=APIError, PermissionDeniedError=APIError, APIError=APIError)
    r.ts = NS(Choice=lambda **kw: kw)
    r.jc = NS(ask=ask, JevAccountError=JevAccountError, DEFAULT_JEV_MODEL="jev-test")
    r.aclient = NS(messages=NS(with_raw_response=NS(create=create),
                               batches=NS(create=bcreate, retrieve=bretrieve, results=bresults)))
    r.jclient = None
    r.log = S.Log(out_dir / "SPIKE-T002-answers.jsonl")
    r.budget = C.Budget(cap, r.log.spent)
    r.gen = S.load_generated()
    r.ratelimit_recorded = False
    return r


def _pages():
    sizes = [100, 70_000]
    pages = [{"page_id": f"X:{i}", "url": "u", "script": "latin", "n_chunks": 1,
              "institution": {"institution_name": "I", "country": "C", "level_of_government": "L"}}
             for i in range(len(sizes))]
    return pages, {p["page_id"]: {"text": "a" * n, "title": "t"} for p, n in zip(pages, sizes, strict=True)}


def test_runner_resume_makes_no_new_calls(tmp_path):
    import spike_t002 as S
    calls = {"jev": 0, "haiku": 0}
    pages, texts = _pages()
    _fake_runner(S, tmp_path, 6.0, calls).run(pages, texts)
    first = dict(calls)
    assert first["jev"] > 0 and first["haiku"] > 0
    _fake_runner(S, tmp_path, 6.0, calls).run(pages, texts)
    assert calls == first                      # every key done, halvings remembered
    rows = [__import__("json").loads(x) for x in (tmp_path / "SPIKE-T002-answers.jsonl").read_text().splitlines()]
    assert any(r.get("max_tokens_exceeded") for r in rows)   # halve-and-retry exercised
    assert any(r.get("kind") == "quote" and r.get("chunk_id") for r in rows)


def test_runner_stops_at_cap(tmp_path):
    import spike_t002 as S
    calls = {"jev": 0, "haiku": 0}
    pages, texts = _pages()
    r = _fake_runner(S, tmp_path, 0.01, calls)
    r.run(pages, texts)
    assert r.budget.spent_usd <= 0.01
    rows = (tmp_path / "SPIKE-T002-answers.jsonl").read_text()
    assert "cap_reached" in rows
