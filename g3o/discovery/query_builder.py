"""Institution-driven query construction.

Given an institution and a list of languages, produce a list of
`(query_string, language)` tuples that the Serper client can execute.
The query-construction logic is deliberately simple in Push #1: a small
set of GenAI-term variants combined with the institution name, with
language-specific GenAI terms for the languages we currently support.
The full multilingual roster will land alongside the master institutions
universe.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

GENAI_TERMS_BY_LANG: dict[str, list[str]] = {
    # English roster expanded 2026-07-04 (PI sign-off): +Copilot, AI chatbot,
    # AI assistant, large language model — closes the discovery-recall gap vs
    # the extraction prompt's vocabulary (Copilot/chatbot deployments were
    # codeable but never searched for). Non-English rosters not yet expanded;
    # translate + promote per-language after the readiness-bar comparison.
    "en": [
        "generative AI",
        "ChatGPT",
        "AI policy",
        "AI pilot",
        "Copilot",
        "AI chatbot",
        "AI assistant",
        "large language model",
    ],
    "fr": ["IA générative", "ChatGPT", "politique IA", "pilote IA"],
    "es": ["IA generativa", "ChatGPT", "política de IA", "piloto de IA"],
    "de": ["generative KI", "ChatGPT", "KI-Richtlinie", "KI-Pilot"],
    "it": ["IA generativa", "ChatGPT", "politica IA", "progetto pilota IA"],
    "pt": ["IA generativa", "ChatGPT", "política de IA", "piloto de IA"],
    "ja": ["生成AI", "ChatGPT", "AIポリシー", "AIパイロット"],
    "zh": ["生成式AI", "ChatGPT", "AI政策", "AI试点"],
    "ar": ["الذكاء الاصطناعي التوليدي", "ChatGPT", "سياسة الذكاء الاصطناعي"],
    "fi": ["generatiivinen tekoäly", "ChatGPT", "tekoälyn periaatteet"],
}


def genai_terms_roster_hash() -> str:
    """Stable fingerprint of the whole GenAI-term roster.

    Hashed over the **entire** mapping rather than the subset a given run's
    ``discovery_languages`` selects: the roster is one instrument, versioned as
    a whole, and a run resumed after an edit to any language is running against
    a different instrument than it launched with.

    Determinism: keys are sorted, so the source-literal order cannot leak in.
    Per-language term lists deliberately keep their source order — reordering a
    language's terms is still a roster edit, and sorting the lists here would
    hash it identically and hide it from the resume guard.

    Reads the module constant at call time (not at import), so a test that
    monkeypatches ``GENAI_TERMS_BY_LANG`` sees the fingerprint move.
    """
    payload = json.dumps(
        GENAI_TERMS_BY_LANG,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _phrase(value: str) -> str:
    """Quote `value` as a single Google exact-phrase slot — a binding match.

    Inner double quotes are dropped rather than escaped: Google has no
    in-phrase escape syntax, so an embedded `"` closes the phrase early and
    silently changes the query. 17 master rows carry one (the Argentine
    `Comisión Municipal "B"` entries).
    """
    return '"' + value.replace('"', "") + '"'

# A `-` at the start of a token is Google's exclusion operator, so bare
# `Kunkavav -Vadia` would actively suppress the very result we want (75 master
# rows, e.g. `Kunkavav -Vadia, Amreli, Gujarat — gram panchayat`). Mid-token
# hyphens (`Al-Anbar`) are inert and must survive, hence the `^|\s` anchor.
_TOKEN_INITIAL_MINUS = re.compile(r"(^|\s)-+(?=\S)")

def _hint(value: str) -> str:
    """Sanitize `value` for use as an UNQUOTED hint slot — non-binding.

    Unquoted slots bias ranking instead of constraining the result set, which
    is the point: a fourth mandatory phrase can empty a result set, a hint
    cannot. The cost is that characters inert inside quotes become live query
    syntax outside them, so anything operator-significant is neutralized here.
    Counts below are from a full scan of the 719,588-row master.

    - `"` (17 rows) — bare, an embedded quote *opens* a phrase, turning a hint
      into a stray binding match. Dropped.
    - `(` / `)` (35,179 disambiguation rows, 7 country rows — `Holy See
      (Vatican City State)`) — brackets removed, inner text kept, per the
      2026-07-30 decision to keep unit-type suffixes as hint tokens.
    - token-initial `-` (75 rows) — see `_TOKEN_INITIAL_MINUS`.
    - whitespace runs (173 rows, e.g. `Division No.  4, Manitoba`) collapsed,
      also mopping up any double space that bracket removal leaves behind.

    Em dashes, commas, and apostrophes carry no query meaning and pass through.
    """
    cleaned = value.replace('"', "").replace("(", "").replace(")", "")
    cleaned = _TOKEN_INITIAL_MINUS.sub(r"\1", cleaned)
    return " ".join(cleaned.split())

# ---------------------------------------------------------------------------
# Two-query discovery chain (2026-08-01). Additive: `build_queries` above is
# untouched and still serves the legacy Stage 1a/1b path.
#
# Findings (agent-workspace/2026-08-01-serper-discovery-yield-findings.md,
# n=24 with hand-adjudicated ground truth): the four-slot format asks one query
# to identify the institution *and* find GenAI evidence, and does neither well
# (6/24 relevant at a designed 16 credits/inst). Splitting the jobs across two
# 1-credit legs scores 14/24; paired McNemar 9 gains / 1 loss, p=0.021.
#
# Confirmed at n=200 and now the pipeline default (2026-08-01-discovery-chain-
# validation.md, PI sign-off). Measured as GET /account balance deltas over 200
# institutions per arm, same sample: 1.84 credits/inst and 64.5% of
# institutions with an own-domain relevant hit, against legacy's 8.52 and
# 20.0%. Paired McNemar 94 gains / 5 losses, exact two-sided p = 2.4e-22.
# (Legacy measures below its 16-credit design cost only because Stage 2 finds
# an official site for just 13/200, so Stage 1b is skipped for 187.)
#
# Two results from that work are load-bearing here and should not be
# re-litigated by tuning these functions:
#   - The **quoted institution name is the primary failure**. Master local names
#     are abbreviated (`Polson H S`, `KELLER ISD`) and quoting them exactly
#     matches almost nothing — three institutions returned zero URLs. Hence
#     `_hint`, not `_phrase`, in leg 1.
#   - Once site-bound, **extra English terms measure at exactly 0 pp** and
#     OR-chains are actively harmful (4/24 vs 16/24 for the bare token). Hence
#     leg 2 is one bare, unquoted token.
# ---------------------------------------------------------------------------

# Leg 1's suffix. Deliberately **not** per-language (PI decision, 2026-08-02).
# Localizing it would change the domain-discovery instrument for every
# institution, against a measured 82.0% recall on the n=200 truth pool and with
# no measurement on the other side. Settling it needs its own A/B on the
# existing harness, not a default flip — so there is no per-language mapping
# here to tempt one.
DOMAIN_QUERY_SUFFIX = "official website"

# The language tag leg 1's queries honestly carry. A constant, not a config
# value, precisely because the suffix above is not localized: the tag must
# describe the query that was issued, not the language the run was configured
# for. Change this only together with DOMAIN_QUERY_SUFFIX.
DOMAIN_QUERY_LANG = "en"

# Leg 1's suffix, per language — the leg-1 counterpart of ``EVIDENCE_TERMS_BY_LANG``.
#
# **TABLED FOR PI SIGNATURE 2026-09-03. The merge of the PR carrying this table is
# the signature; until then the flag that reads it, ``discovery_leg1_multilingual``,
# defaults False and production issues the English row only.** The signable table
# with the evidence beside each row is
# ``agent-workspace/2026-09-01-discovery-legs/leg1-suffix-roster/SIGNABLE-SUFFIX-ROSTER-90.md``.
#
# How the rows were built. The PI ruled on 2026-09-01 that leg 1 goes multilingual
# and on 2026-09-03 that it ships as an **English-first fallback**: the English
# query is issued on every institution as today, and the localized queries are
# issued only where Stage 2 then finds no official site. That is the design the
# card-2 probe supported (``leg1-suffix-roster/FINDINGS-ordering.md``): on an
# unselected pool of 1,412 institutions the localized block added **zero recall**
# over English (McNemar p = 1.0), while on the 26 institutions where English had
# failed it recovered 7 (p = 0.344, underpowered) — so its value is entirely
# conditional on English having failed, and issuing it everywhere would cost ~4x
# for nothing.
#
# Three provenance classes, in the order they appear below, and the class matters
# more than the string:
#
#   PROBED, per language   — 32 tags issued live against Serper on 2026-09-01
#                            (strata A and C; ``data/probe-*results.json``).
#   PROBED, pooled only    — 22 tags added the same day to cover the 77-row
#                            stratum-B cell; too few institutions each for a
#                            per-tag claim, so the evidence is the pooled figure.
#   DRAFTED, unprobed      — 35 tags never issued. Written 2026-09-03 under the
#                            construction rule alone ("the native phrase
#                            governments actually use, not a literal translation
#                            of the English"), so that the roster is complete and
#                            the gate can pass. A miss on one of these costs a
#                            wasted credit on institutions whose English query
#                            already failed — it cannot misattribute anything,
#                            because the tag on the query is the tag whose suffix
#                            built it. Rows marked ``(check)`` are the ones the
#                            drafter had genuine doubt about; read those first.
#
# Why a complete table and not the one English row that stood here until today:
# :func:`g3o.common.languages.assert_policy_rostered` checks every tag the signed
# policy could emit, on every run, before the first credit. A partial roster does
# not make leg 1 partially multilingual — it makes a multilingual run unable to
# start. The PI's direction (2026-09-03) is to ship the fallback; a complete table
# is the only shape that can.
#
# One suffix per tag, not a list. Leg 1 costs one credit per language issued, and
# nothing measured says a second suffix per language buys anything.
DOMAIN_SUFFIX_BY_LANG: dict[str, str] = {
    "en": DOMAIN_QUERY_SUFFIX,

    # ── PROBED, per language (strata A/C, 2026-09-01) ──────────────────────
    "ar": "الموقع الرسمي",
    "bn": "অফিসিয়াল ওয়েবসাইট",  # (check) loanword; the native form may be দাপ্তরিক ওয়েবসাইট
    "ca": "lloc web oficial",
    "cs": "oficiální stránky",
    "cy": "gwefan swyddogol",
    "de": "offizielle Website",
    "es": "sitio web oficial",
    "eu": "webgune ofiziala",
    "fr": "site officiel",
    "ga": "suíomh oifigiúil",
    "gl": "páxina web oficial",  # (check) deliberately not byte-identical to the es row
    "hi": "आधिकारिक वेबसाइट",
    "hu": "hivatalos honlap",
    "id": "situs resmi",
    "it": "sito ufficiale",
    "ja": "公式サイト",
    "kk-cyrl": "ресми сайт",
    "nl": "officiële website",
    "pt": "site oficial",  # Brazil is 93 of 147 pt rows; European pt would be "sítio oficial"
    "ro": "site oficial",  # identical string to pt; different countries, no collision
    "ru": "официальный сайт",
    "rw": "urubuga rwemewe",  # (check) low confidence on government Kinyarwanda
    "sk": "oficiálna stránka",
    "sr-cyrl": "званична презентација",  # (check) Serbian gov usage favours prezentacija over sajt
    "sr-latn": "zvanična prezentacija",  # (check) same caveat
    "sw": "tovuti rasmi",
    "th": "เว็บไซต์ทางการ",
    "uk": "офіційний сайт",
    "uz-cyrl": "расмий сайт",  # same phrase as uz-latn in Cyrillic — a script test
    "uz-latn": "rasmiy sayt",
    "vi": "trang thông tin điện tử",  # (check) what Vietnamese portals call themselves
    "zh-hans": "官方网站",

    # ── PROBED, pooled only (stratum B, 2026-09-01) ────────────────────────
    "dv": "ރަސްމީ ވެބްސައިޓް",  # (check) low confidence
    "dz": "ངོ་མའི་དྲ་ཚིགས།",  # (check) lowest confidence in the probed set
    "el": "επίσημη ιστοσελίδα",
    "fa": "وب‌سایت رسمی",
    "ht": "sit ofisyèl",
    "hy": "պաշտոնական կայք",
    "ka": "ოფიციალური ვებგვერდი",
    "ko": "공식 웹사이트",
    "ku": "malpera fermî",  # (check) Kurmanji; Sorani would differ
    "ky": "расмий сайт",  # identical string to uz-cyrl; different countries
    "lt": "oficiali svetainė",
    "mk": "официјална веб-страница",
    "mn": "албан ёсны вэбсайт",
    "ms": "laman web rasmi",
    "mt": "sit uffiċjali",
    "my": "တရားဝင် ဝဘ်ဆိုက်",
    "ne": "आधिकारिक वेबसाइट",  # identical string to hi; different countries
    "pap": "sitio ofisial",  # (check) low confidence, close to Spanish
    "ps": "رسمي ویب پاڼه",  # (check) low confidence
    "sl": "uradna spletna stran",
    "sq": "faqja zyrtare",
    "tzm-tfng": "ⴰⵙⵉⵜ ⵓⵏⵚⵉⴱ",  # (check) Tifinagh government publication is itself thin

    # ── DRAFTED, unprobed (2026-09-03) ─────────────────────────────────────
    "am": "ይፋዊ ድህረ ገጽ",
    "az": "rəsmi sayt",
    "be": "афіцыйны сайт",
    "bg": "официален сайт",
    "bs": "službena stranica",
    "cnr-cyrl": "званични сајт",  # (check) Montenegrin follows Serbian usage; unverified
    "cnr-latn": "zvanični sajt",  # (check) same caveat
    "da": "officiel hjemmeside",
    "et": "ametlik veebileht",
    "fi": "viralliset verkkosivut",
    "fo": "almenn heimasíða",  # (check) low confidence
    "he": "אתר רשמי",
    "hr": "službena stranica",  # identical string to bs; different countries
    "is": "opinber vefsíða",
    "kl": "pisortat nittartagaat",  # (check) LOWEST confidence in the table; verify before signing
    "km": "គេហទំព័រផ្លូវការ",
    "lb": "offiziell Websäit",
    "lo": "ເວັບໄຊທ໌ທາງການ",
    "lv": "oficiālā mājaslapa",  # (check) "oficiālā tīmekļvietne" is the other government form
    "mg": "tranonkala ofisialy",
    "no": "offisiell nettside",
    "om": "marsariitii ofisiyaalaa",  # (check) low confidence
    "pl": "oficjalna strona internetowa",
    "rn": "urubuga rwemewe",  # identical string to rw; Kirundi and Kinyarwanda share it (check)
    "si": "නිල වෙබ් අඩවිය",
    "so": "bogga rasmiga ah",  # (check) low confidence
    "sv": "officiell webbplats",
    "ta": "அதிகாரப்பூர்வ இணையதளம்",
    "tet": "website ofisiál",  # (check) low confidence
    "tg": "сомонаи расмӣ",
    "ti": "ወግዓዊ መርበብ ሓበሬታ",  # (check) low confidence
    "tk": "resmi web sahypasy",
    "tr": "resmi web sitesi",
    "ur": "سرکاری ویب سائٹ",
    "zh-hant": "官方網站",
}

# Leg 2's default evidence token. Bare and unquoted by measurement, not by
# omission — see the module note above.
DEFAULT_EVIDENCE_TERM = "AI"

# Leg 2's evidence token, per language. The chain-mode counterpart of
# ``GENAI_TERMS_BY_LANG``, and the instrument the signed language policy of
# 2026-08-30 selects from.
#
# A row here is a methodology surface, not a translation: it silently changes
# every leg-2 query a run issues for that language. **All 90 rows were signed by
# the PI on 2026-08-31** against
# ``agent-workspace/2026-08-31-multilingual-readiness/SIGNABLE-ROSTER-90.md``,
# on evidence from two Serper probes (1,856 + 736 credits, 2026-08-30).
#
# **The construction rule: one term per tag, the native multi-character phrase.**
# Not a judgement imposed on the measurement but the one it produced — of the 57
# arms that beat the English control at national tier, 54 were multi-character
# native terms, 1 was an abbreviation, and 0 was the loanword ``AI``. It is also
# the homograph test in the signed relevance screen (whitespace, or length >= 4),
# which keeps out every documented failure: Hungarian ``MI`` (the pronoun that
# outranked the real term on raw volume), ``IA`` (the *ia* in *media*/*social*),
# and bare ``ai`` (the French verb). Applied to all 89 non-English tags it yields
# exactly one candidate each, with no gaps and no ties.
#
# It overrides a measured winner on exactly one row, by PI ruling: ``tr`` takes
# ``yapay zeka`` (marginal 4) over ``YZ`` (marginal 5), because ``YZ`` is on the
# homograph list and won by a single URL under a screen since found biased.
#
# **Why all 90 and not the 21 that cleared the floor.**
# :func:`g3o.common.languages.assert_policy_rostered` checks every tag the signed
# policy could emit on any institution, before the first Serper credit. Under the
# ``2026-08-30`` policy that is all 90, on every run. A partial roster does not
# make the pipeline partially multilingual — it makes it unable to start. The PI
# ruled (2026-08-31) that multilingual is to be a permanent, automatic part of
# the pipeline, so the roster is complete by construction.
#
# The tags are exactly the policy's 90 selectable languages — set equality,
# asserted in ``tests/test_language_policy_wiring.py``.
#
# One term per language, not a list: extra terms measure at exactly 0 pp once
# site-bound and OR-chains are actively harmful (4/24 vs 16/24). If a language
# ever needs two, that is a measured decision and changes leg-2's credit cost.
EVIDENCE_TERMS_BY_LANG: dict[str, str] = {
    "en": DEFAULT_EVIDENCE_TERM,

    # Class A - cleared the sub-national floor. 21 tags, 300,705 master rows.
    # Marginal >=3 AND >=25% of the English control, measured on 216 sub-national
    # domains - the tier the frame lives at. Four rest on one or two registrable
    # domains (kk-cyrl, uz-cyrl, uz-latn, ru); gov.kz and gov.uz reach every
    # subdomain of that government, which is broader than one site and still one
    # country.
    "ar": "الذكاء الاصطناعي",
    "bn": "কৃত্রিম বুদ্ধিমত্তা",
    "bs": "umjetna inteligencija",
    "ca": "intel·ligència artificial",
    "cnr-latn": "vještačka inteligencija",
    "cs": "umělá inteligence",
    "de": "künstliche Intelligenz",
    "es": "inteligencia artificial",
    "fr": "intelligence artificielle",
    "gl": "intelixencia artificial",
    "hr": "umjetna inteligencija",
    "hu": "mesterséges intelligencia",
    "id": "kecerdasan buatan",
    "it": "intelligenza artificiale",
    "kk-cyrl": "жасанды интеллект",
    "pt": "inteligência artificial",
    "ru": "искусственный интеллект",
    "sr-cyrl": "вештачка интелигенција",
    "sr-latn": "veštačka inteligencija",
    "uz-cyrl": "сунъий интеллект",
    "uz-latn": "sunʼiy intellekt",

    # Classes B1-B3 - ON PROBATION. 14 tags, 311,707 master rows.
    # Carried by PI ruling 2026-08-31 ("same as hi for now"), not by measurement.
    # B1 (hi, rw, eu) measured a marginal of 0-2 against a control of 22-34 on nine
    # sub-national domains each: the government publishes its AI material in
    # English. B2 (lo, mn, km, mg, tzm-tfng, cnr-cyrl) is uninformative rather than
    # null - the control found nothing either, so the domains carry no AI content in
    # any language. B3 (am, om, fa, ps, tet) is underpowered: one to three domains.
    # These rows spend a leg-2 credit per institution for a term with no measured
    # yield. hi alone is 267,177 master rows. The first multilingual run's readout
    # is where they are ruled on; until then they stay, because the run cannot
    # produce the evidence to drop them if they are not in it.
    "am": "ሰው ሰራሽ አስተውሎት",
    "cnr-cyrl": "вјештачка интелигенција",
    "eu": "adimen artifiziala",
    "fa": "هوش مصنوعی",
    "hi": "कृत्रिम बुद्धिमत्ता",
    "km": "បញ្ញាសិប្បនិម្មិត",
    "lo": "ປັນຍາປະດິດ",
    "mg": "faharanitan-tsaina artifisialy",
    "mn": "хиймэл оюун ухаан",
    "om": "beekumsa nam-tolchee",
    "ps": "مصنوعي ځیرکتیا",
    "rw": "ubwenge bwa artifisiye",
    "tet": "inteligensia artifisial",
    "tzm-tfng": "ⵜⴰⵎⵓⵙⵏⵉ ⵜⴰⵏⴰⴼⴳⴰⵏⵜ",

    # Class C - never reached at sub-national tier. 54 tags, 50,057 master rows.
    # The 2026-08-29 signature pass recorded no non-national host for these
    # countries, so the sub-national probe had no pool to build. The term is the
    # drafted native phrase under the construction rule. The national-tier
    # measurement exists but is not the signing basis: that table is superseded,
    # and its relevance screen was differentially biased toward fr/es/pt/de/it,
    # none of which are in this class.
    "az": "süni intellekt",
    "be": "штучны інтэлект",
    "bg": "изкуствен интелект",
    "cy": "deallusrwydd artiffisial",
    "da": "kunstig intelligens",
    "dv": "މަސްނޫއީ ބުއްދި",
    "dz": "བཟོ་བཀོད་རིག་པ།",
    "el": "τεχνητή νοημοσύνη",
    "et": "tehisintellekt",
    "fi": "tekoäly",
    "fo": "vitmaskina",
    "ga": "intleacht shaorga",
    "he": "בינה מלאכותית",
    "ht": "entèlijans atifisyèl",
    "hy": "արհեստական բանականություն",
    "is": "gervigreind",
    "ja": "人工知能",
    "ka": "ხელოვნური ინტელექტი",
    "kl": "silatusaaq",
    "ko": "인공지능",
    "ku": "زیرەکی دەستکرد",
    "ky": "жасалма интеллект",
    "lb": "kënschtlech Intelligenz",
    "lt": "dirbtinis intelektas",
    "lv": "mākslīgais intelekts",
    "mk": "вештачка интелигенција",
    "ms": "kecerdasan buatan",
    "mt": "intelliġenza artifiċjali",
    "my": "ဉာဏ်ရည်တု",
    "ne": "कृत्रिम बुद्धिमत्ता",
    "nl": "kunstmatige intelligentie",
    "no": "kunstig intelligens",
    "pap": "inteligensia artificial",
    "pl": "sztuczna inteligencja",
    "rn": "ubwenge bwa artifisiye",
    "ro": "inteligență artificială",
    "si": "කෘත්‍රිම බුද්ධිය",
    "sk": "umelá inteligencia",
    "sl": "umetna inteligenca",
    "so": "sirdoonka macmalka ah",
    "sq": "inteligjenca artificiale",
    "sv": "artificiell intelligens",
    "sw": "akili bandia",
    "ta": "செயற்கை நுண்ணறிவு",
    "tg": "зеҳни сунъӣ",
    "th": "ปัญญาประดิษฐ์",
    "ti": "ሰብ ሰራሕ ኣእምሮ",
    "tk": "emeli aň",
    "tr": "yapay zeka",
    "uk": "штучний інтелект",
    "ur": "مصنوعی ذہانت",
    "vi": "trí tuệ nhân tạo",
    "zh-hans": "人工智能",
    "zh-hant": "人工智慧",
}


def evidence_terms_roster_hash() -> str:
    """Stable fingerprint of the whole chain-mode evidence-term roster.

    The counterpart of :func:`genai_terms_roster_hash` for the roster chain mode
    actually issues its leg-2 queries from, and it did not exist until the roster
    did. While ``EVIDENCE_TERMS_BY_LANG`` held a single English row that was
    harmless: the manifest recorded a fingerprint of ``GENAI_TERMS_BY_LANG``,
    which a chain run never reads, and none of the roster a chain run *does*
    read. With 90 PI-signed rows the evidence roster is the instrument, and a run
    resumed after an edit to any row is running a different one than it launched
    with — the exact failure the A4 guard exists to catch.

    Hashed over the entire mapping, keys sorted, read at call time rather than at
    import, for the same three reasons the GenAI-roster hash is.
    """
    payload = json.dumps(
        EVIDENCE_TERMS_BY_LANG,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def domain_suffix_roster_hash() -> str:
    """Stable fingerprint of the whole leg-1 domain-suffix roster.

    The leg-1 counterpart of :func:`evidence_terms_roster_hash`, and load-bearing
    for the same reason: the moment this roster carries more than the English row
    it *is* the domain-discovery instrument, and a run resumed after an edit to
    any row is running a different instrument than the one it launched with.

    Recorded from the day the roster is a single row, deliberately. The evidence
    roster's own history is the argument: while ``EVIDENCE_TERMS_BY_LANG`` held
    one English row the manifest recorded a fingerprint of ``GENAI_TERMS_BY_LANG``
    — a roster a chain run never reads — and none of the roster it does read. The
    manifest key exists here before the rows do so that the first signed row moves
    a fingerprint that was already being written down.

    Hashed over the entire mapping, keys sorted, read at call time rather than at
    import, for the same three reasons the GenAI-roster hash is.
    """
    payload = json.dumps(
        DOMAIN_SUFFIX_BY_LANG,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class UnknownLanguageError(ValueError):
    """A configured language has no roster entry for the mode being run.

    Fail-loud replaces the silent English fallback (roadmap A7, PI decision
    2026-08-02). The fallback was safe while only English ran; under language
    expansion it is actively misleading — a run configured ``ru`` would issue
    **English** queries, record ``institution_search_languages = ru``, and
    produce a "Russian readiness assessment" computed on English data, silently
    at every stage and all the way into a published per-country figure.
    """


def assert_languages_rostered(
    languages: Iterable[str],
    roster: dict[str, Any],
    route: str = "subprojects/multilingual-pipeline/, not a config change — "
    "see roadmap A2/A7",
) -> None:
    """Raise :class:`UnknownLanguageError` for any language absent from ``roster``.

    ``roster`` is ``GENAI_TERMS_BY_LANG`` under ``legacy``,
    ``EVIDENCE_TERMS_BY_LANG`` under ``chain``, and ``DOMAIN_SUFFIX_BY_LANG`` for
    chain's leg 1 (2026-09-01) — the three are not interchangeable, and a
    language rostered for one is not thereby runnable under the others.

    ``route`` names where a missing row is *added*, and it differs per roster:
    the evidence rosters route through the multilingual subproject, the leg-1
    suffix roster through card 2 of the discovery-legs plan. It is a parameter
    with the evidence-roster wording as its default so that every pre-existing
    call site raises a byte-identical message; only a caller that knows its
    roster is a different instrument overrides it. Telling a reader to add a
    leg-1 suffix in the leg-2 subproject would send the one person who hits this
    error to the wrong signature table.
    """
    unknown = [lang for lang in languages if lang not in roster]
    if not unknown:
        return
    raise UnknownLanguageError(
        f"no roster entry for language(s) {unknown!r}; "
        f"rostered: {sorted(roster)!r}. Adding one is a PI-signed roster "
        f"decision routed through {route}."
    )


def build_domain_query(
    institution_name: str,
    country: str | None = None,
    disambiguation: str | None = None,
    quote_name: bool = False,
    suffix: str = DOMAIN_QUERY_SUFFIX,
) -> str:
    """Leg 1 — identify the institution's own domain. One credit.

    ``<name> <country> <disambiguation> official website``. Slot order matches
    :func:`build_queries`; any absent slot is skipped.

    ``suffix`` defaults to :data:`DOMAIN_QUERY_SUFFIX`, so every existing call
    site issues the query it always issued, byte for byte. It is a parameter
    rather than a lookup inside this function for the same reason
    :func:`build_evidence_query` takes ``term``: the *choice* of suffix is the
    instrument and belongs to the caller that holds the language, and a function
    that reached into :data:`DOMAIN_SUFFIX_BY_LANG` itself would have to invent a
    behaviour for an unrostered tag — which is exactly the silent English
    fallback :func:`build_domain_queries` refuses.

    ``disambiguation`` is the master's parent-geography annotation (PI catch,
    2026-08-01 — it was missing from the first cut of this function). It carries
    **30.2% of the full master (217,385 rows)** and separates units that
    ``country`` alone cannot: three distinct ``Ain Beida`` local bodies sit in
    Algeria, told apart only by ``Oum El Bouaghi — commune`` vs
    ``Ouargla — commune``. Domain discovery is hardest on exactly those rows, so
    omitting it silently degraded the case leg 1 most needs to get right. (Only
    4.7% of the ground-truth-eligible pool carries one, which is why the
    2026-08-01 confirmation run barely felt it.)

    ``quote_name`` binds the institution name as an exact phrase instead of a
    hint. **Default False, and that default is evidence-backed:** the findings
    identify the quoted name as the primary failure of the four-slot format —
    master local names are abbreviated (``Polson H S``, ``KELLER ISD``) and
    quoting them matches almost nothing. That evidence was gathered where a
    quoted name *and* a quoted GenAI term both had to match, so it does not
    transfer to leg 1 automatically; the flag exists to settle the question on
    measurement rather than argument.

    Unquoted slots are sanitized through :func:`_hint`: outside quotes a
    token-initial ``-`` is Google's exclusion operator and a stray ``"`` opens a
    phrase.
    """
    name = _phrase(institution_name) if quote_name else _hint(institution_name)
    slots = [name]
    for qualifier in (country, disambiguation):
        hint = _hint(qualifier) if qualifier else ""
        if hint:
            slots.append(hint)
    slots.append(suffix)
    return " ".join(s for s in slots if s)


def build_domain_queries(
    institution_name: str,
    languages: Iterable[str],
    country: str | None = None,
    disambiguation: str | None = None,
    quote_name: bool = False,
) -> list[tuple[str, str]]:
    """Leg 1, once per language the institution's policy row names. One credit each.

    The multilingual form of :func:`build_domain_query` (PI ruling 2026-09-01),
    shaped to match :func:`build_queries` so the two legs are read the same way:
    ``(query_string, language)`` tuples, in the order ``languages`` gives them,
    which is the signed policy's row order with ``always_include`` applied.

    **Additive, not a swap.** Because the signed 2026-08-30 policy carries
    ``always_include: ['en']``, ``en`` is among the languages of every
    institution, so the English query production issues today is always in the
    returned list. No institution loses its English arm, and the comparison the
    card asks for is within-institution rather than between runs.

    **Fail loud, never fall back.** A tag with no row in
    :data:`DOMAIN_SUFFIX_BY_LANG` raises
    :class:`UnknownLanguageError` through :func:`assert_languages_rostered` — the
    same choke point, and the same definition of "rostered", that leg 2 uses.
    The alternative was measured and rejected on leg 2 in the same words: a
    silent English fallback would issue English queries, tag them with the
    requested language, and make the misattribution invisible from the artifact
    onward. Asserted once for the whole list, before any query is built, so the
    caller cannot half-issue an institution.

    **Identical queries are not deduped, and that is deliberate.** Two tags
    sharing a suffix produce byte-identical query strings; dropping the second
    would save nothing and lose that language's attribution, since
    :func:`g3o.discovery.serper_client.search_google_detailed` keys its on-disk
    cache on the whole request payload — the repeat is served from cache, costs
    no credit, and records ``from_cache: true`` in its own provenance entry. Cost
    is handled by the cache; attribution is handled by keeping the row.

    Under the roster as it stands — one English row — an institution whose policy
    languages reduce to ``("en",)`` gets exactly one query, identical to
    :func:`build_domain_query`'s. Any other tag raises. That is the gate, not a
    limitation of this function.
    """
    languages = list(languages)
    assert_languages_rostered(
        languages,
        DOMAIN_SUFFIX_BY_LANG,
        route="agent-workspace/2026-09-01-discovery-legs/cards/"
        "2-legs-leg1-multilingual.txt, not a config change",
    )
    return [
        (
            build_domain_query(
                institution_name,
                country,
                disambiguation,
                quote_name=quote_name,
                suffix=DOMAIN_SUFFIX_BY_LANG[lang],
            ),
            lang,
        )
        for lang in languages
    ]


def build_evidence_query(site_domain: str, term: str = DEFAULT_EVIDENCE_TERM) -> str:
    """Leg 2 — find GenAI evidence on a known domain. One credit.

    ``site:<domain> AI``. Deliberately *not* wrapped around
    :func:`build_queries`: production Stage 1b wraps the whole four-slot query
    in ``site:``, repeating the institution name inside a query already bound
    to that institution's domain, and **93.2% of those queries (179/192) return
    zero results.**

    ``term`` stays a parameter so the multilingual subproject can pass a
    native-language token without touching this module; it is not a knob for
    adding English terms, which measure at 0 pp.
    """
    return f"site:{site_domain} {term}".strip()


def build_open_evidence_queries(
    institution_name: str,
    terms: Mapping[str, str],
    country: str | None = None,
    disambiguation: str | None = None,
) -> list[tuple[str, str]]:
    """The open (non-site-bound) evidence leg — one query per language. One credit each.

    ``"<name>" <country> <disambiguation> "<term>"``: the four-slot shape of the
    retired legacy leg, with ``terms`` — the institution's ``{language: term}``
    map off the signed 90-term ``EVIDENCE_TERMS_BY_LANG`` roster — supplying one
    native phrase per language where legacy issued eight English ones. That
    difference is the whole of what card 3 measured (2026-09-02, n=600, real
    Stages 1c → 3 → 5, ``agent-workspace/2026-09-01-discovery-legs/leg3/READOUT.md``):

    * as an **addition** to the site-bound chain it surfaced 45 institutions with
      confirmed GenAI evidence that chain never reached (7.5% of the sample,
      10.8% → 18.3%), 53 of them from third-party sources and 5 own-domain;
    * as a **replacement** it is worthless (loses 38 of chain's 65, p = 0.51);
    * in **English alone** it is significantly worse than chain (p = 0.047) — the
      multilingual half is what redeems it.

    The PI ruled on 2026-09-03 that it enters production as a fourth leg, in every
    policy language, English included via ``always_include``. It is additive to
    leg 2, never instead of it, and its URLs feed Stage 1c and triage but **not**
    Stage 2's official-site adjudication — a query for content is not a query for
    a website, and mixing the two candidate sets would change the domain
    instrument as a side effect of an evidence change.

    Slot sanitizing is :func:`_phrase` / :func:`_hint`, the same rules the other
    legs use, so the 719,588-row master's edge cases (token-initial ``-``,
    embedded quotes, brackets) behave identically here. Same slot order as
    :func:`build_queries`; an absent qualifier is skipped.

    ``terms`` is a mapping rather than a language list so this function cannot
    reach into the roster and invent a behaviour for an unrostered tag — the
    caller (``PresweepConfig.evidence_terms_for``) has already been through the
    pre-spend choke point. Order is the mapping's order, which is the policy's.
    """
    out: list[tuple[str, str]] = []
    for lang, term in terms.items():
        slots = [_phrase(institution_name)]
        for qualifier in (country, disambiguation):
            hint = _hint(qualifier) if qualifier else ""
            if hint:
                slots.append(hint)
        slots.append(_phrase(term))
        out.append((" ".join(slots), lang))
    return out


def build_queries(
    institution_name: str,
    languages: Iterable[str],
    extra_terms: Iterable[str] | None = None,
    country: str | None = None,
    disambiguation: str | None = None,
) -> list[tuple[str, str]]:
    """Build (query_string, language) tuples for a given institution.

    For each language in `languages`, emit one query per GenAI term known
    for that language. A language with no roster entry raises
    :class:`UnknownLanguageError`; it does **not** fall back to English
    (roadmap A7, PI decision 2026-08-02 — see that class's docstring for why
    the fallback was worse than an error). `extra_terms` (if given) are
    appended as language-agnostic additions to every language.

    Only two slots are binding: the institution name and the GenAI term stay
    quoted exact phrases. The two qualifier slots are **unquoted hints** —
    they bias ranking without constraining the result set:

        "Ain Beida" Algeria Oum El Bouaghi — commune "generative AI"

    `country` (if given and non-empty) disambiguates institutions whose name
    is shared by a more prominent entity elsewhere — "House of
    Representatives" unqualified is dominated by US Congress results.

    `disambiguation` (if given and non-empty) is the master's parent-geography
    annotation for rows flagged `duplicate=1`, produced by the same-name
    resolution work under ticket_0006 ("disambiguate genuinely-distinct
    same-name entries"). It separates units `country` alone cannot: same-named
    units recur both within a country and across countries (three distinct
    "Oran" local bodies sit in India and Uganda).

    Hint rather than phrase, decided 2026-07-30, reversing the quoted country
    slot shipped in 6878d1a. Master disambiguation values are compound
    (`"Prantij, Sabar Kantha, Gujarat — gram panchayat"`); as a mandatory
    fourth phrase such a value matches almost no document and would suppress
    recall on the 216,640 rows that carry one, so the qualifiers inform
    ranking instead. Values are otherwise passed through whole — no component
    is extracted, since choosing one would change what discovery collects and
    is a reviewed decision rather than something this function assumes. See
    `_hint` for the sanitizing that unquoting makes necessary.

    Slot order is name → country → disambiguation → term. Any absent slot is
    skipped, so an institution with neither qualifier reproduces the original
    two-phrase query exactly.
    """
    queries: list[tuple[str, str]] = []
    extras = list(extra_terms or [])
    languages = list(languages)
    # Fail loud rather than fall back to English (A7, PI decision 2026-08-02).
    # This is the defect line itself: the old `.get(lang) or ...["en"]` issued
    # English queries and then labelled them with the *requested* code, so the
    # misattribution was invisible from the artifact onward.
    assert_languages_rostered(languages, GENAI_TERMS_BY_LANG)

    for lang in languages:
        terms = GENAI_TERMS_BY_LANG[lang]
        for term in terms + extras:
            slots = [_phrase(institution_name)]
            for qualifier in (country, disambiguation):
                # Sanitize before the emptiness check: a value that reduces to
                # nothing (say "()") must not leave a blank slot in the join.
                hint = _hint(qualifier) if qualifier else ""
                if hint:
                    slots.append(hint)
            slots.append(_phrase(term))
            queries.append((" ".join(slots), lang))

    return queries
