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

INST = "inst-1"


def words(n: int, prefix: str = "w") -> list[str]:
    return [f"{prefix}{i}" for i in range(n)]


def text(ws: list[str]) -> str:
    return " ".join(ws)


def test_pinned_parameters():
    assert syn.SYNDICATION_VERSION == "g3o.common.syndication.v2"
    assert (syn.SHINGLE_WORDS, syn.JACCARD_NUM, syn.JACCARD_DEN, syn.NUM_PERM) == (5, 4, 5, 128)
    assert syn.EDGE_DECISION == "exact_shingle_set_jaccard"
    assert syn.SHORT_PAGE_POLICY == "singleton_flagged"


def test_normalisation_lower_and_whitespace():
    a = "The  Ministry\tuses\nGenerative AI tools daily"
    b = "  the ministry uses generative ai TOOLS daily "
    assert syn.shingles(a) == syn.shingles(b)
    g = syn.group_pages({"p1": a, "p2": b}, institution_id=INST)
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
    g = syn.group_pages({"a": text(base), "b": text(near), "c": text(far)}, institution_id=INST)
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
    g = syn.group_pages({"a": text(a), "b": text(b), "c": text(c), "d": text(words(30, "d"))}, institution_id=INST)
    assert g.group_of("a") == g.group_of("b") == g.group_of("c")
    assert g.members[g.group_of("a")] == ("a", "b", "c")
    assert g.members[g.group_of("d")] == ("d",)
    assert len(g.members) == 2


def test_order_independence_and_resume_stability():
    pages = {f"inst1:u{i}": text(words(40, f"p{i % 3}")) for i in range(7)}
    g1 = syn.group_pages(pages, institution_id=INST)
    g2 = syn.group_pages(dict(reversed(list(pages.items()))), institution_id=INST)
    assert g1.groups == g2.groups
    assert g1.members == g2.members
    # Group id is derived from version + institution id + sorted member keys only.
    for gid, mem in g1.members.items():
        assert gid == syn.group_id(INST, mem) == syn.group_id(INST, list(reversed(mem)))
        assert gid.startswith("sg-") and len(gid) == 3 + 2 * syn.GROUP_ID_DIGEST_BYTES


def test_singletons_get_own_ids():
    g = syn.group_pages({"a": text(words(20, "a")), "b": text(words(20, "b"))}, institution_id=INST)
    assert g.group_of("a") != g.group_of("b")
    assert g.group_of("a") == syn.group_id(INST, ["a"])


def test_short_pages_flagged_singletons():
    g = syn.group_pages({"s1": "one two three four", "s2": "one two three four", "e": "",
                         "ok": text(words(10))}, institution_id=INST)
    assert g.short_pages == ("e", "s1", "s2")
    assert len({g.group_of("s1"), g.group_of("s2"), g.group_of("e")}) == 3
    assert g.pages["s1"].short and g.pages["s1"].signature_sha is None
    assert g.pages["s1"].signature is None and g.detail("s1")["signature"] is None
    assert g.detail("s1")["short_page_policy"] == "singleton_flagged"
    assert g.detail("ok")["short_page_policy"] is None


def test_chrome_text_not_read():
    @dataclass
    class Page:
        text: str
        chrome_text: str | None

    body = text(words(30))
    g = syn.group_rendered_pages({"a": Page(body, "menu home contact " * 50),
                                  "b": Page(body, "totally different footer " * 50)}, institution_id=INST)
    assert g.group_of("a") == g.group_of("b")


def test_signature_deterministic_known_values():
    sig = syn.minhash_signature(syn.shingles(text(words(12))))
    assert sig is not None and len(sig) == syn.NUM_PERM
    assert sig == syn.minhash_signature(syn.shingles(text(words(12))))
    assert all(0 <= v < syn.MERSENNE_61 for v in sig)


_PROBE = (
    "from g3o.common import syndication as s;"
    "t=' '.join('w%d'%i for i in range(12));"
    "g=s.group_pages({'b':t,'a':t,'c':'x y z q r s'},institution_id='inst-1');"
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
    g = syn.group_pages({"p1": text(words(20)), "p2": text(words(20))}, institution_id=INST)
    fv = sf.syndication_group_for(g, "p1")
    assert fv.item_id == sf.SYNDICATION and fv.value == g.group_of("p2")
    assert fv.detail["version"] == syn.SYNDICATION_VERSION
    assert fv.detail["members"] == ["p1", "p2"]
    assert fv.detail["institution_id"] == INST
    assert fv.detail["signature"] == list(g.pages["p1"].signature)
    with pytest.raises(sf.MissingUpstreamError):
        sf.syndication_group_for(g, "missing")
    with pytest.raises(sf.MissingUpstreamError):
        sf.syndication_group_for(None, "p1")
    assert sf.syndication_group(fv.value).value == fv.value


def test_golden_values():
    # Pinned outputs of SYNDICATION_VERSION v2: a change to any parameter, hash or
    # normalisation (or a platform difference) fails here. The signature itself is
    # unchanged from v1; the group ids changed when the institution id joined the hash.
    t = " ".join(f"w{i}" for i in range(12))
    g = syn.group_pages({"b": t, "a": t, "c": "x y z q r s"}, institution_id=INST)
    assert g.pages["a"].signature_sha == "cd5bdf99c60be73443ca5765fa552cc7"
    assert g.pages["a"].signature[:2] == (348204508626453818, 129868701720063631)
    assert g.group_of("a") == g.group_of("b") == "sg-cb478f2efc52d268c04b"
    assert g.group_of("c") == "sg-9a45fef9c7a03df126b3"


def test_full_signature_stored_per_page():
    # A4 ruling 7: the MinHash signature is stored per page, not only its digest.
    g = syn.group_pages({"a": text(words(12)), "b": text(words(30, "b"))}, institution_id=INST)
    for k in ("a", "b"):
        fp = g.pages[k]
        assert fp.signature == syn.minhash_signature(syn.shingles(text(words(12) if k == "a" else words(30, "b"))))
        assert len(fp.signature) == syn.NUM_PERM
        assert fp.signature_sha == syn.signature_sha(fp.signature)
        assert g.detail(k)["signature"] == list(fp.signature)
        assert g.detail(k)["signature_sha"] == fp.signature_sha


def test_institutions_never_share_group_ids():
    pages = {"p1": text(words(20)), "p2": text(words(20)), "p3": text(words(20, "z"))}
    g1 = syn.group_pages(pages, institution_id="inst-1")
    g2 = syn.group_pages(pages, institution_id="inst-2")
    assert g1.members.keys().isdisjoint(g2.members.keys())
    assert list(g1.members.values()) == list(g2.members.values())  # same partition
    assert g1.detail("p1")["institution_id"] == "inst-1"
    assert syn.group_id("inst-1", ["p1"]) != syn.group_id("inst-2", ["p1"])


@pytest.mark.parametrize("bad", [None, "", "   ", 7])
def test_institution_id_required(bad):
    with pytest.raises(ValueError):
        syn.group_pages({"p1": text(words(20))}, institution_id=bad)
    with pytest.raises(ValueError):
        syn.group_id(bad, ["p1"])
    with pytest.raises(TypeError):
        syn.group_pages({"p1": text(words(20))})  # keyword is mandatory
