"""X27 source_language producer (g3o.common.language_id; PI rulings A3.1 a, A3.2 a, 2 b, 2026-11-11).

Offline: lingua runs locally on its bundled models; no network.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import lingua
import pytest

from g3o.classify.jev_page_code import PageInput
from g3o.common import contract
from g3o.common import language_id as lid
from g3o.common import source_fields as sf
from g3o.common.languages import _LANG_TAG

EN = ("The Ministry of Finance announced today that it will pilot a generative AI assistant for "
      "answering citizen questions about tax filing. The pilot will run for six months in three "
      "regional offices, and the results will be published in the annual report. ")
FR = ("Le ministère des Finances a annoncé aujourd'hui qu'il allait tester un assistant "
      "d'intelligence artificielle générative pour répondre aux questions des citoyens sur la "
      "déclaration d'impôts. Le projet pilote durera six mois dans trois bureaux régionaux. ")
DE = ("Das Bundesministerium hat heute bekannt gegeben, dass es einen Assistenten auf Basis "
      "generativer künstlicher Intelligenz erproben wird, der Fragen der Bürgerinnen und Bürger "
      "zur Steuererklärung beantwortet. Das Pilotprojekt dauert sechs Monate. ")


@dataclass(frozen=True)
class _Span:
    language: object
    start_index: int
    end_index: int


class _FakeDetector:
    def __init__(self, spans):
        self.spans = spans

    def detect_multiple_languages_of(self, _text):
        return self.spans


def _fake(monkeypatch, spans):
    monkeypatch.setattr(lid, "_detector", lambda: _FakeDetector(spans))


# --- pin and configuration -------------------------------------------------


def test_pinned_version_and_fixed_configuration():
    assert lid.PINNED_LINGUA == "2.2.0"
    conf = lid.configuration()
    assert conf == lid.configuration()
    assert conf["library"] == "lingua-language-detector" and conf["library_version"] == "2.2.0"
    assert conf["languages"] == "from_all_languages" and conf["language_count"] == 75
    assert conf["accuracy_mode"] == "high" and conf["preloaded_models"] is False
    assert conf["text"] == "main" and conf["min_main_text_chars"] == lid.MIN_MAIN_TEXT_CHARS == 200
    assert conf["mul_share"] == 0.5


def test_other_installed_version_refuses(monkeypatch):
    monkeypatch.setattr(lid, "version", lambda _name: "2.1.1")
    with pytest.raises(lid.LanguageIdError, match="2.2.0"):
        lid._lingua()


# --- tag mapping -----------------------------------------------------------


def test_every_loaded_language_maps_onto_the_search_language_grammar():
    table = lid.tag_table()
    assert len(table) == len(list(lingua.Language.all())) == 75
    single = re.compile(contract.LANGS_PATTERN)
    for name, tag in table:
        assert _LANG_TAG.fullmatch(tag) and single.fullmatch(tag), (name, tag)
        assert tag == getattr(lingua.Language, name).iso_code_639_1.name.lower()
    assert len({t for _, t in table}) == len(table)
    named = dict(table)
    assert (named["ENGLISH"], named["CHINESE"], named["BOKMAL"], named["NYNORSK"]) == ("en", "zh", "nb", "nn")


def test_language_without_a_two_letter_tag_is_refused_not_guessed():
    class NoIso:
        name = "KLINGON"
        iso_code_639_1 = None

    with pytest.raises(lid.UnmappedLanguageError):
        lid.language_tag(NoIso())


# --- decisions -------------------------------------------------------------


def test_single_language_pages():
    assert lid.identify(EN * 2).tag == "en"
    assert lid.identify(FR * 2).tag == "fr"
    assert lid.identify(DE * 2).tag == "de"


def test_deterministic_across_calls_and_a_fresh_detector():
    text = EN + FR + EN + DE
    first = lid.identify(text)
    assert lid.identify(text) == first
    lid._detector.cache_clear()
    assert lid.identify(text) == first


def test_min_length_gives_unknown():
    n = lid.MIN_MAIN_TEXT_CHARS
    short = (EN * 2)[: n - 1]
    res = lid.identify(short)
    assert (res.tag, res.reason, res.text_chars) == ("unknown", "below_min_length", n - 1)
    assert lid.identify((EN * 2)[:n]).reason != "below_min_length"
    assert lid.identify("").tag == "unknown"


def test_no_language_identified_gives_unknown():
    res = lid.identify("1234567890 " * 30)
    assert (res.tag, res.reason) == ("unknown", "no_language_identified")


def test_share_must_exceed_half_strictly(monkeypatch):
    en, fr = lingua.Language.ENGLISH, lingua.Language.FRENCH
    text = "x" * 400
    _fake(monkeypatch, [_Span(en, 0, 200), _Span(fr, 200, 400)])
    assert lid.identify(text).tag == "mul"  # 0.5 exactly: tie, not exceeding
    _fake(monkeypatch, [_Span(en, 0, 201), _Span(fr, 201, 400)])
    res = lid.identify(text)
    assert res.tag == "en" and res.shares[0] == ("en", 201 / 400)
    _fake(monkeypatch, [_Span(en, 0, 200)])  # uncovered characters stay in the denominator
    assert lid.identify(text).tag == "mul"
    _fake(monkeypatch, [_Span(en, 0, 150), _Span(fr, 150, 250), _Span(en, 250, 310)])
    assert lid.identify(text).tag == "en"  # spans of one language are summed: 210 / 400


def test_bilingual_page_is_mul():
    assert lid.identify(EN + FR + EN + FR + DE + DE).tag == "mul"


# --- source_fields wiring: main text only ----------------------------------


def _page(text, chrome):
    return PageInput(page_id="p1", institution_id="i1", institution="Ministry", country="FR",
                     level_of_government="national", url="https://x.example/a", title="t",
                     text=text, chrome_text=chrome)


def test_chrome_text_is_ignored():
    english_main = sf.source_language_of_page(_page(EN * 2, FR * 20))
    assert english_main.value == "en"
    assert english_main == sf.source_language(EN * 2)
    assert sf.source_language_of_page(_page("Accueil", FR * 20)).value == "unknown"


def test_source_language_field_value():
    f = sf.source_language(EN * 2)
    assert (f.item_id, f.value, f.coder) == (sf.LANGUAGE, "en", "mechanical")
    assert f.detail["language_id_version"] == lid.LANGUAGE_ID_VERSION
    assert sf.source_language(EN + FR + EN + FR + DE + DE).value == "mul"
    with pytest.raises(sf.MissingUpstreamError):
        sf.source_language(None)
    with pytest.raises(TypeError):
        sf.source_language(b"bytes")


# --- v2.5 unchanged --------------------------------------------------------


def test_v25_contract_pattern_unchanged():
    assert contract.LANG_PATTERN == r"^[a-z]{2}$"
