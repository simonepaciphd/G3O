"""Tests for the P15 near-duplicate grouper (PI A4.1 a, A4.2 a, 2026-11-11).

Expected values follow the ruling text: 5-word shingles on lower-cased,
whitespace-collapsed main text; Jaccard >= 0.8; connected components; one
institution; stable on resume. No network.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

import pytest

from g3o.common import source_fields as sf
from g3o.common import syndication as syn


def words(n: int, prefix: str = "w") -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def text(ws: list[str]) -> str:
    return " ".join(ws)


def test_pinned_parameters():
    assert syn.SYNDICATION_VERSION == "g3o.common.syndication.v1"
    assert (syn.SHINGLE_WORDS, syn.JACCARD_NUM, syn.JACCARD_DEN, syn.NUM_PERM) == (5, 4, 5, 128)
    assert syn.EDGE_DECISION == "exact_shingle_set_jaccard"
    assert syn.SHORT_PAGE_POLICY == "singleton_flagged"


def test_normalisation_lower_and_whitespace():
    a = "The  Ministry\tuses\nGenerative AI tools daily"
    b = "  the ministry uses generative ai TOOLS daily "
    assert syn.shingles(a) == syn.shingles(b)
    g = syn.group_pages({"p1": a, "p2": b})
    assert g.group_of("p1") == g.group_of("p2")


def test_shingle_count():
    assert len(syn.shingles(text(words(5)))) == 1
    assert len(syn.shingles(text(words(9)))) == 5
    assert syn.shingles(text(words(4))) == frozenset()


def test_threshold_edge_exact():
    # A has 100 distinct shingles (104 words); B shares a prefix of k of them and adds extras.
    base = words(104)
    a = syn.shingles(text(base))
    assert len(a) == 100
    # Sets built directly for exact edges.
    s80 = frozenset(list(a)[:80]) | frozenset(f"x{i}" for i in range(20))
    # |A & B| = 80, |A | B| = 120 -> J = 2/3 < 0.8
    assert not syn.jaccard_at_least_threshold(a, s80)
    sub = frozenset(sorted(a)[:80])  # B subset of A, |B| = 80 -> J = 0.8 exactly
    assert syn.jaccard_at_least_threshold(a, sub)
    sub79 = frozenset(sorted(a)[:79])  # J = 0.79
    assert not syn.jaccard_at_least_threshold(a, sub79)
    # J = 8/10 exactly with overlap: |A|=9,|B|=9, inter 8, union 10.
    x = frozenset(f"s{i}" for i in range(9))
    y = frozenset(f"s{i}" for i in range(1, 10))
    assert syn.jaccard_at_least_threshold(x, y)
    y2 = frozenset(f"s{i}" for i in range(2, 11))  # inter 7, union 11 -> 0.636
    assert not syn.jaccard_at_least_threshold(x, y2)


def test_threshold_on_pages():
    base = words(104)  # 100 shingles
    # Changing the last word replaces 5 shingles: inter 95, union 105 -> J = 0.905 -> linked.
    near = base[:-1] + ["CHANGED"]
    # Changing every 10th word destroys most shingles -> not linked.
    far = [w if i % 10 else "Z" + w for i, w in enumerate(base)]
    g = syn.group_pages({"a": text(base), "b": text(near), "c": text(far)})
    assert g.group_of("a") == g.group_of("b") != g.group_of("c")
    assert g.edges == (("a", "b"),)


def test_components_transitivity():
    # a~b and b~c but a !~ c: one component of three.
    base = words(60)  # 56 shingles
    a = base
    b = base[5:] + words(5, "q")  # shift keeps 51 of 56
    c = b[5:] + words(5, "r")
    sa, sb, sc = (syn.shingles(text(x)) for x in (a, b, c))
    assert syn.jaccard_at_least_threshold(sa, sb)
    assert syn.jaccard_at_least_threshold(sb, sc)
    assert not syn.jaccard_at_least_threshold(sa, sc)
    g = syn.group_pages({"a": text(a), "b": text(b), "c": text(c), "d": text(words(30, "d"))})
    assert g.group_of("a") == g.group_of("b") == g.group_of("c")
    assert g.members[g.group_of("a")] == ("a", "b", "c")
    assert g.members[g.group_of("d")] == ("d",)
    assert len(g.members) == 2


def test_order_independence_and_resume_stability():
    pages = {f"inst1:u{i}": text(words(40, f"p{i % 3}")) for i in range(7)}
    g1 = syn.group_pages(pages)
    g2 = syn.group_pages(dict(reversed(list(pages.items()))))
    assert g1.groups == g2.groups
    assert g1.members == g2.members
    # Group id is derived from version + sorted member keys only.
    for gid, mem in g1.members.items():
        assert gid == syn.group_id(mem) == syn.group_id(list(reversed(mem)))
        assert gid.startswith("sg-") and len(gid) == 3 + 2 * syn.GROUP_ID_DIGEST_BYTES


def test_singletons_get_own_ids():
    g = syn.group_pages({"a": text(words(20, "a")), "b": text(words(20, "b"))})
    assert g.group_of("a") != g.group_of("b")
    assert g.group_of("a") == syn.group_id(["a"])


def test_short_pages_flagged_singletons():
    g = syn.group_pages({"s1": "one two three four", "s2": "one two three four", "e": "",
                         "ok": text(words(10))})
    assert g.short_pages == ("e", "s1", "s2")
    assert len({g.group_of("s1"), g.group_of("s2"), g.group_of("e")}) == 3
    assert g.pages["s1"].short and g.pages["s1"].signature_sha is None
    assert g.detail("s1")["short_page_policy"] == "singleton_flagged"
    assert g.detail("ok")["short_page_policy"] is None


def test_chrome_text_not_read():
    @dataclass
    class Page:
        text: str
        chrome_text: str | None

    body = text(words(30))
    g = syn.group_rendered_pages({"a": Page(body, "menu home contact " * 50),
                                  "b": Page(body, "totally different footer " * 50)})
    assert g.group_of("a") == g.group_of("b")


def test_signature_deterministic_known_values():
    sig = syn.minhash_signature(syn.shingles(text(words(12))))
    assert sig is not None and len(sig) == syn.NUM_PERM
    assert sig == syn.minhash_signature(syn.shingles(text(words(12))))
    assert all(0 <= v < syn.MERSENNE_61 for v in sig)


_PROBE = (
    "from g3o.common import syndication as s;"
    "t=' '.join('w%d'%i for i in range(12));"
    "g=s.group_pages({'b':t,'a':t,'c':'x y z q r s'});"
    "print(sorted(g.groups.items()), g.pages['a'].signature_sha)"
)


def test_cross_process_byte_stable():
    # Fresh interpreters with different hash seeds give identical output (no built-in hash()).
    outs = set()
    for seed in ("0", "12345"):
        env = {"PYTHONHASHSEED": seed}
        import os
        env = {**os.environ, **env}
        r = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, env=env, check=True)
        outs.add(r.stdout)
    assert len(outs) == 1


def test_source_field_from_grouping():
    g = syn.group_pages({"p1": text(words(20)), "p2": text(words(20))})
    fv = sf.syndication_group_for(g, "p1")
    assert fv.item_id == sf.SYNDICATION and fv.value == g.group_of("p2")
    assert fv.detail["version"] == syn.SYNDICATION_VERSION
    assert fv.detail["members"] == ["p1", "p2"]
    with pytest.raises(sf.MissingUpstreamError):
        sf.syndication_group_for(g, "missing")
    with pytest.raises(sf.MissingUpstreamError):
        sf.syndication_group_for(None, "p1")
    assert sf.syndication_group(fv.value).value == fv.value


def test_golden_values():
    # Pinned outputs of SYNDICATION_VERSION v1: a change to any parameter, hash or
    # normalisation (or a platform difference) fails here.
    t = " ".join(f"w{i}" for i in range(12))
    g = syn.group_pages({"b": t, "a": t, "c": "x y z q r s"})
    assert g.pages["a"].signature_sha == "cd5bdf99c60be73443ca5765fa552cc7"
    assert g.group_of("a") == g.group_of("b") == "sg-0b79d53f7a3042069631"
    assert g.group_of("c") == "sg-c65e0e3f018b3b710c76"
