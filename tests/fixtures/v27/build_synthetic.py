"""Build tests/fixtures/v27/synthetic.json: the T-040 synthetic fixtures (DEC-006 c).

Run: python tests/fixtures/v27/build_synthetic.py
Free and offline. Every expected value cites the signed codebook release 2.7
(codebook/codebook.yaml, sha256 f948fe0b...181e0d) or a SPEC row. Institutions, URLs and
texts are invented (kind "synthetic"); no pilot v1 input is used (C-006).

Modes:
  pipeline  page text goes through the integrated pipeline (T-041 runs jev/extractor);
  injected  page- or part-level answers are given and only deterministic code runs
            (link following, combining, Stage 6 truth table). Injected answers use the
            shape {"value", "p" (chosen-answer probability), "support" (support status),
            "quote"}.
"""

from __future__ import annotations

import json
from pathlib import Path

CB = "codebook 2.7"
HERE = Path(__file__).resolve().parent


def inst(i, name, country="United Kingdom", level="local"):
    return {"institution_id": f"SYN-{i:04d}", "name": name, "country": country, "level": level}


def exp(item, value, rule, scope="page:p0", **kw):
    d = {"item": item, "scope": scope, "value": value, "rule": rule}
    d.update(kw)
    return d


def page(key, url, text=None, links=None, title="", fetch="ok", text_parts=None):
    p = {
        "page_key": key,
        "url": url,
        "title": title,
        "fetch_status": fetch,
        "chrome_text": "",
        "links": links or [],
    }
    if text_parts is not None:
        p["text_parts"] = text_parts
    else:
        p["text"] = text
    return p


def ia(value, p=0.95, support="supported", quote=None):
    """Injected answer."""
    d = {"value": value, "p": p, "support": support}
    if quote:
        d["quote"] = quote
    return d


F = []

# ---------------------------------------------------------------- A-011 page verdicts (synthetic fill)
A011 = [
    (
        "confirms_activity",
        inst(1, "Northfield Borough Council"),
        "Northfield Borough Council has rolled out Microsoft Copilot to 400 staff in its customer services "
        "team after a six-month pilot. The council's digital team configured Copilot to draft replies to "
        "resident enquiries, which officers check before sending.",
        f"{CB} core.page_verdict confirms_activity: own GenAI deployment, named generative product (Copilot)",
    ),
    (
        "ambiguous_genai",
        inst(2, "Eastmoor District Council"),
        "Eastmoor District Council has adopted an AI strategy for 2026-2028. The strategy sets out how the "
        "council will use AI tools and data analytics to improve services. No specific tools are named.",
        f"{CB} core.page_verdict ambiguous_genai: generic 'AI strategy' / 'AI tools' (example in the definition); SPEC R-016",
    ),
    (
        "ambiguous_attribution",
        inst(3, "Little Haddon Parish Council"),
        "A national pilot will give councils across the country access to a generative AI assistant for "
        "drafting planning reports. Councils can register interest with the ministry; the list of "
        "participating councils will be published later this year.",
        f"{CB} core.page_verdict ambiguous_attribution: country-wide GenAI initiative without confirmation this institution takes part",
    ),
    (
        "other_body",
        inst(4, "Brookside Ward Council"),
        "Riverton County Council, which covers Brookside ward among others, has launched ChatGPT Enterprise "
        "for its planning department. The county's IT service manages the licences.",
        f"{CB} core.page_verdict other_body: GenAI activity of a parent/higher-level body (county) when the named institution is a ward",
    ),
    (
        "event_only",
        inst(5, "Southgate Town Council"),
        "Southgate Town Council invites residents to a free evening workshop, 'Getting started with ChatGPT', "
        "at the town library on 12 March. Bring your own laptop.",
        f"{CB} core.page_verdict event_only: only GenAI content is a public-facing workshop; no adoption by the institution",
    ),
    (
        "background_only",
        inst(6, "Westbury City Council"),
        "News roundup: the national government published its AI Opportunities Action Plan this week. "
        "Analysts expect generative AI to change how public services work over the next decade.",
        f"{CB} core.page_verdict background_only: only general context (national AI strategy, news about GenAI in general)",
    ),
    (
        "confirms_absence",
        inst(7, "Hollowmere Town Council"),
        "Freedom of information response: Hollowmere Town Council does not use generative AI tools such as "
        "ChatGPT or Copilot, and has no plans to introduce them.",
        f"{CB} core.page_verdict confirms_absence: page states this institution has no GenAI activity (C01 commits_to, SPEC A-011)",
    ),
    (
        "no_genai",
        inst(8, "Ashby Parva Parish Council"),
        "Ashby Parva Parish Council meets on the first Tuesday of each month in the village hall. Agendas "
        "are posted on the noticeboard three days before each meeting.",
        f"{CB} core.page_verdict no_genai: no GenAI content relevant to this institution",
    ),
]
for n, (val, ins, text, rule) in enumerate(A011, start=1):
    F.append(
        {
            "fixture_id": f"v27-syn-A011-{n:02d}",
            "kind": "synthetic",
            "mode": "pipeline",
            "a_ids": ["A-011"],
            "purpose": f"page verdict {val}",
            "institution": ins,
            "pages": [
                page("p0", f"https://synthetic.example/{ins['institution_id'].lower()}/p0", text)
            ],
            "expected": [exp("core.page_verdict", val, rule)],
        }
    )
F.append(
    {
        "fixture_id": "v27-syn-A011-09",
        "kind": "synthetic",
        "mode": "injected",
        "a_ids": ["A-011", "A-010"],
        "purpose": "page verdict not_assessable is set mechanically for a page not reviewed",
        "institution": inst(9, "Kelby Village Council"),
        "pages": [page("p0", "https://synthetic.example/syn-0009/p0", "", fetch="failed_http_503")],
        "injected": {"p0": {"review": "not_reviewed", "reason": "fetch failed"}},
        "expected": [
            exp(
                "core.page_verdict",
                "not_assessable",
                f"{CB} core.page_verdict not_assessable (jev_choice false) + rule 'not one of the answers: set when a page was not reviewed'; SPEC R-015 (C1 a)",
                asked=False,
            ),
            exp(
                "core.has_genai_activity",
                "unclear",
                "SPEC R-005 / codebook core.has_genai_activity truth table: a failed fetch blocks `no`; no supported confirms_activity page gives no `yes`",
                scope="institution",
            ),
        ],
    }
)

# ---------------------------------------------------------------- A-012 GenAI boundary
A012 = [
    (
        "v27-syn-A012-01",
        "named AI chatbot counts as GenAI",
        "Ask Ellie, Fenwick Council's AI chatbot, answers questions about bin collections and council tax "
        "24 hours a day on the council website.",
        [
            exp(
                "core.page_verdict",
                "confirms_activity",
                f"{CB} core.rule.genai_boundary: a tool the page calls an 'AI chatbot' counts as GenAI; SPEC R-016",
            ),
            exp(
                "core.genai_mechanism_basis",
                "ai_chatbot_or_assistant_label_only",
                f"{CB} core.genai_mechanism_basis value ai_chatbot_or_assistant_label_only (A01 basis)",
                scope="activity:Ask Ellie",
            ),
        ],
    ),
    (
        "v27-syn-A012-02",
        "rule-based chatbot without an AI label is not GenAI",
        "Use our online helper to report a missed bin. Choose an option from the menu and the helper will "
        "take you to the right form. The helper follows a fixed set of menu options.",
        [
            exp(
                "core.page_verdict",
                "no_genai",
                f"{CB} core.page_verdict confirms_activity exclusion (automation without generative capability or a GenAI/AI-chatbot label); no AI mentioned, so not ambiguous_genai; SPEC R-016 (contract L12 rule-based exclusion)",
                judgement_call="JC-S1",
            )
        ],
    ),
    (
        "v27-syn-A012-03",
        "generic AI strategy stays ambiguous",
        "The council's new Artificial Intelligence Strategy commits us to explore AI tools across all "
        "directorates, subject to an ethics review.",
        [
            exp(
                "core.page_verdict",
                "ambiguous_genai",
                f"{CB} core.page_verdict ambiguous_genai (generic 'AI strategy', 'AI tools'); SPEC R-016 (contract §4.1 stays unclear)",
            )
        ],
    ),
    (
        "v27-syn-A012-04",
        "machine translation not tied to a generative product is not GenAI",
        "This website can be translated into 40 languages using the automatic translation button at the "
        "top of each page. Automatic translations may contain errors.",
        [
            exp(
                "core.page_verdict",
                "no_genai",
                f"{CB} core.rule.genai_boundary translation clause: translation counts only when tied to a named generative product or a language model; no AI mentioned",
                judgement_call="JC-S1",
            )
        ],
    ),
    (
        "v27-syn-A012-05",
        "translation tied to a named generative product is GenAI",
        "Harbour City Council now translates its public notices into Polish, Arabic and Urdu using ChatGPT. "
        "A council translator checks every notice before it is published.",
        [
            exp(
                "core.page_verdict",
                "confirms_activity",
                f"{CB} core.rule.genai_boundary translation clause (named generative product); SPEC R-016 S1 a",
            ),
            exp(
                "core.genai_mechanism_basis",
                "named_genai_product_or_model",
                f"{CB} core.genai_mechanism_basis named_genai_product_or_model",
                scope="activity:ChatGPT notice translation",
            ),
            exp(
                "core.function_translation",
                "yes",
                f"{CB} core.function_translation",
                scope="activity:ChatGPT notice translation",
            ),
        ],
    ),
    (
        "v27-syn-A012-06",
        "explicit GenAI label without a product",
        "Greystone County Council is piloting a generative AI tool in its adult social care team to help "
        "social workers write case notes. The pilot runs until June.",
        [
            exp(
                "core.page_verdict",
                "confirms_activity",
                f"{CB} core.page_verdict confirms_activity (explicitly generative AI, own pilot)",
            ),
            exp(
                "core.genai_mechanism_basis",
                "explicit_genai_label",
                f"{CB} core.genai_mechanism_basis explicit_genai_label",
                scope="activity:case-note GenAI pilot",
            ),
            exp(
                "core.adoption_stage",
                "pilot",
                f"{CB} core.adoption_stage pilot",
                scope="activity:case-note GenAI pilot",
            ),
        ],
    ),
    (
        "v27-syn-A012-07",
        "generative capability described without a GenAI label",
        "Our contact centre uses an AI system that writes a first draft of the reply to each resident email; "
        "staff edit the draft before it is sent.",
        [
            exp(
                "core.page_verdict",
                "confirms_activity",
                f"{CB} core.page_verdict confirms_activity: page says the tool generates text",
            ),
            exp(
                "core.genai_mechanism_basis",
                "generative_capability_described",
                f"{CB} core.genai_mechanism_basis generative_capability_described",
                scope="activity:email reply drafting",
            ),
            exp(
                "core.has_human_oversight",
                "yes",
                f"{CB} core.has_human_oversight yes (staff edit before sending)",
                scope="activity:email reply drafting",
            ),
        ],
    ),
]
for n, (fid, purpose, text, ex) in enumerate(A012, start=10):
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "pipeline",
            "a_ids": ["A-012"],
            "purpose": purpose,
            "institution": inst(
                n,
                [
                    "Fenwick Council",
                    "Moorland District Council",
                    "Calder Borough Council",
                    "Linden Town Council",
                    "Harbour City Council",
                    "Greystone County Council",
                    "Oakhurst City Council",
                ][n - 10],
            ),
            "pages": [page("p0", f"https://synthetic.example/syn-{n:04d}/p0", text)],
            "expected": ex,
        }
    )

# ---------------------------------------------------------------- A-003 multi-activity
A003 = [
    (
        "v27-syn-A003-01",
        "named programme with two named components",
        inst(20, "Kingsford City Council"),
        "Kingsford City Council's 'Smart Kingsford AI Programme' has two parts. The first is Ask Kira, an AI "
        "chatbot on the council website that answers resident questions. The second is a Microsoft Copilot "
        "pilot for 50 finance staff.",
        [
            exp(
                "core.activity_segment",
                3,
                "SPEC R-017: a named program is one activity; each named component is its own activity",
                scope="page:p0",
                value_kind="n_activities",
            ),
            exp(
                "core.activity_segment",
                "component_of_program",
                f"{CB} relation vocabulary; SPEC R-017 (components linked, never merged)",
                scope="pair:Ask Kira|Smart Kingsford AI Programme",
            ),
            exp(
                "core.activity_segment",
                "has_component",
                f"{CB} relation has_component (reverse link, RC-D-003 activity-16 b)",
                scope="pair:Smart Kingsford AI Programme|Copilot finance pilot",
            ),
            exp(
                "core.activity_segment",
                "distinct_action",
                "SPEC R-017 shared relation list; two components of one programme are not the same activity",
                scope="pair:Ask Kira|Copilot finance pilot",
                judgement_call="JC-S2",
            ),
        ],
    ),
    (
        "v27-syn-A003-02",
        "policy and the tool it approves",
        inst(21, "Penrose District Council"),
        "Penrose District Council has adopted a Generative AI Acceptable Use Policy. Under the policy, staff "
        "may use Microsoft Copilot for drafting documents; other GenAI tools are not approved.",
        [
            exp(
                "core.activity_segment",
                2,
                "SPEC R-017: a policy and the tools it approves are separate activities",
                value_kind="n_activities",
            ),
            exp(
                "core.activity_segment",
                "governs",
                f"{CB} relation governs; SPEC R-017",
                scope="pair:GenAI Acceptable Use Policy|Copilot drafting",
            ),
            exp(
                "core.activity_segment",
                "governed_by",
                f"{CB} relation governed_by (reverse link)",
                scope="pair:Copilot drafting|GenAI Acceptable Use Policy",
            ),
            exp(
                "core.governance_direction",
                "restricts_with_conditions",
                f"{CB} core.governance_direction: permits one tool, other tools not approved",
                scope="activity:GenAI Acceptable Use Policy",
                judgement_call="JC-S3",
            ),
        ],
    ),
    (
        "v27-syn-A003-03",
        "pair where two links fit: governs wins",
        inst(22, "Thornbury Borough Council"),
        "Thornbury's Digital Futures programme includes the council's AI Use Policy, which sets the rules "
        "for every generative AI tool used within the programme.",
        [
            exp(
                "core.activity_segment",
                "governs",
                "SPEC R-017: when two links fit one pair (component_of_program and governs), governs wins (activity-17 a)",
                scope="pair:AI Use Policy|Digital Futures programme",
            )
        ],
    ),
    (
        "v27-syn-A003-04",
        "repeat purchases of one product by one unit are one activity",
        inst(23, "Wexley Town Council"),
        "Schedule of payments. 3 Jan: OpenAI, ChatGPT Team subscription, IT unit, 150.00. 3 Feb: OpenAI, "
        "ChatGPT Team subscription, IT unit, 150.00. 3 Mar: OpenAI, ChatGPT Team subscription, IT unit, 150.00.",
        [
            exp(
                "core.activity_segment",
                1,
                "SPEC R-017: repeated transactions for the same product by the same unit are one activity",
                value_kind="n_activities",
            ),
            exp(
                "core.procurement_status",
                "payment_or_subscription",
                f"{CB} core.procurement_status payment_or_subscription",
                scope="activity:ChatGPT Team subscription",
            ),
        ],
    ),
    (
        "v27-syn-A003-05",
        "two unrelated activities on one page",
        inst(24, "Marlow Vale Council"),
        "Council update. Parking: our new AI assistant on the parking portal helps drivers appeal penalty "
        "charges. Libraries: the library service ran a free 'AI for beginners' talk for residents.",
        [
            exp(
                "core.activity_segment",
                "distinct_action",
                f"{CB} relation distinct_action; SPEC R-017",
                scope="pair:parking AI assistant|AI for beginners talk",
            ),
            exp(
                "core.page_verdict",
                "confirms_activity",
                f"{CB} core.page_verdict order rule (first fitting value): the AI assistant is the institution's own GenAI tool (R-016)",
            ),
        ],
    ),
]
for fid, purpose, ins, text, ex in A003:
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "pipeline",
            "a_ids": ["A-003"],
            "purpose": purpose,
            "institution": ins,
            "pages": [
                page("p0", f"https://synthetic.example/{ins['institution_id'].lower()}/p0", text)
            ],
            "expected": ex,
        }
    )

# ---------------------------------------------------------------- A-004 incomplete pages (link following)
POS = "The council's generative AI pilot is described on this page; see the linked page for more details."


def chain_page(i, nxt):
    links = (
        [
            {
                "url": f"https://synthetic.example/syn-0030/p{nxt}",
                "anchor": "more details on the GenAI pilot",
            }
        ]
        if nxt is not None
        else []
    )
    return page(f"p{i}", f"https://synthetic.example/syn-0030/p{i}", POS, links)


F.append(
    {
        "fixture_id": "v27-syn-A004-01",
        "kind": "synthetic",
        "mode": "injected",
        "a_ids": ["A-004"],
        "purpose": "hop limit 3: a chain of incomplete pages is followed only to 3 hops",
        "institution": inst(30, "Stonebridge Council"),
        "pages": [chain_page(i, i + 1 if i < 5 else None) for i in range(6)],
        "injected": {
            f"p{i}": {"core.page_complete": ia("yes"), "core.page_verdict": ia("confirms_activity")}
            for i in range(6)
        },
        "expected": [
            exp(
                "followed_urls",
                ["p1", "p2", "p3"],
                "SPEC R-032: links followed only up to 3 hops from the originally scraped page; codebook core.page_complete `yes` means incomplete",
                scope="institution",
            ),
            exp("not_followed", ["p4"], "SPEC R-032 hop limit", scope="institution"),
            exp(
                "provenance",
                {"p1": "p0", "p2": "p1", "p3": "p2"},
                "SPEC R-034: every followed link records the page it came from",
                scope="institution",
            ),
        ],
    }
)
F.append(
    {
        "fixture_id": "v27-syn-A004-02",
        "kind": "synthetic",
        "mode": "injected",
        "a_ids": ["A-004"],
        "purpose": "per-institution cap of 10 followed URLs: following stops and 'cap reached' is recorded",
        "institution": inst(31, "Redcliffe Council"),
        "pages": [
            page(
                "p0",
                "https://synthetic.example/syn-0031/p0",
                POS,
                [
                    {
                        "url": f"https://synthetic.example/syn-0031/l{j:02d}",
                        "anchor": f"GenAI pilot report part {j}",
                    }
                    for j in range(1, 14)
                ],
            )
        ]
        + [
            page(
                f"l{j:02d}",
                f"https://synthetic.example/syn-0031/l{j:02d}",
                "Further detail on the pilot.",
            )
            for j in range(1, 14)
        ],
        "injected": {
            "p0": {"core.page_complete": ia("yes"), "core.page_verdict": ia("confirms_activity")},
            **{
                f"l{j:02d}": {
                    "core.page_complete": ia("no"),
                    "core.page_verdict": ia("confirms_activity"),
                }
                for j in range(1, 14)
            },
            "link_selection": {"p0": [f"l{j:02d}" for j in range(1, 14)]},
        },
        "expected": [
            exp("n_followed", 10, "SPEC R-032 cap value 10 (RC-D-014 S4)", scope="institution"),
            exp(
                "cap_reached",
                True,
                "SPEC R-032: when the cap is reached, following stops and 'cap reached' is recorded",
                scope="institution",
            ),
            exp(
                "which_followed",
                "unspecified",
                "SPEC R-032 does not fix which 10 of 13 eligible links are followed",
                scope="institution",
                judgement_call="JC-S4",
            ),
        ],
    }
)
F.append(
    {
        "fixture_id": "v27-syn-A004-03",
        "kind": "synthetic",
        "mode": "injected",
        "a_ids": ["A-004"],
        "purpose": "link loop and a URL linked from two pages: each URL fetched at most once",
        "institution": inst(32, "Fairhaven Council"),
        "pages": [
            page(
                "p0",
                "https://synthetic.example/syn-0032/p0",
                POS,
                [
                    {
                        "url": "https://synthetic.example/syn-0032/p1",
                        "anchor": "GenAI pilot details",
                    },
                    {
                        "url": "https://synthetic.example/syn-0032/p2",
                        "anchor": "GenAI pilot evaluation",
                    },
                ],
            ),
            page(
                "p1",
                "https://synthetic.example/syn-0032/p1",
                POS,
                [
                    {
                        "url": "https://synthetic.example/syn-0032/p0",
                        "anchor": "back to the GenAI pilot",
                    },
                    {
                        "url": "https://synthetic.example/syn-0032/p2",
                        "anchor": "GenAI pilot evaluation",
                    },
                ],
            ),
            page(
                "p2",
                "https://synthetic.example/syn-0032/p2",
                "The pilot evaluation is summarised here.",
                [],
            ),
        ],
        "injected": {
            "p0": {"core.page_complete": ia("yes")},
            "p1": {"core.page_complete": ia("yes")},
            "p2": {"core.page_complete": ia("no")},
            "link_selection": {"p0": ["p1", "p2"], "p1": ["p0", "p2"]},
        },
        "expected": [
            exp(
                "fetch_count",
                {"p0": 1, "p1": 1, "p2": 1},
                "SPEC R-034: each URL fetched at most once per institution per run (prevents loops under R-032)",
                scope="institution",
            ),
            exp(
                "provenance",
                {"p1": "p0", "p2": "p0"},
                "SPEC R-034 provenance chain; RC-D-015 F2 a (approved 2026-11-04): the recorded parent is the page that first queued the URL, in traversal order. p0 is the root and queues p1 and p2 before p1 is fetched, so p2 <- p0 in any traversal",
                scope="institution",
                judgement_call="JC-S5",
            ),
        ],
    }
)
F.append(
    {
        "fixture_id": "v27-syn-A004-04",
        "kind": "synthetic",
        "mode": "injected",
        "a_ids": ["A-004"],
        "purpose": "a complete page triggers no following",
        "institution": inst(33, "Elmstead Council"),
        "pages": [
            page(
                "p0",
                "https://synthetic.example/syn-0033/p0",
                "The council's Copilot pilot ran from May to July. All details are on this page.",
                [{"url": "https://synthetic.example/syn-0033/x1", "anchor": "council home"}],
            )
        ],
        "injected": {
            "p0": {"core.page_complete": ia("no"), "core.page_verdict": ia("confirms_activity")}
        },
        "expected": [
            exp(
                "followed_urls",
                [],
                f"{CB} core.page_complete `no` (complete; `yes` means the page refers onward); SPEC R-031 follows only incomplete pages",
                scope="institution",
            )
        ],
    }
)
F.append(
    {
        "fixture_id": "v27-syn-A004-05",
        "kind": "synthetic",
        "mode": "pipeline",
        "a_ids": ["A-004", "A-010"],
        "purpose": "followed link fails to fetch: recorded, and it blocks institution `no`",
        "institution": inst(34, "Lowfield Council"),
        "pages": [
            page(
                "p0",
                "https://synthetic.example/syn-0034/p0",
                "The council is reviewing whether to use generative AI. The review paper is linked below.",
                [
                    {
                        "url": "https://synthetic.example/syn-0034/p1",
                        "anchor": "generative AI review paper",
                    }
                ],
            ),
            page("p1", "https://synthetic.example/syn-0034/p1", "", fetch="failed_http_404"),
        ],
        "expected": [
            exp(
                "followed_urls",
                ["p1"],
                "SPEC R-031/R-033 (any cited link eligible)",
                scope="institution",
                judgement_call="JC-S6",
            ),
            exp(
                "core.page_verdict",
                "not_assessable",
                f"{CB} core.page_verdict not_assessable (page not reviewed)",
                scope="page:p1",
            ),
            exp(
                "core.has_genai_activity",
                "unclear",
                "SPEC R-005 (failed fetch blocks `no`, A-010 N18)",
                scope="institution",
            ),
        ],
    }
)


# ---------------------------------------------------------------- A-010 Stage 6 institution fixtures (injected page answers)
def s6(fid, purpose, i, name, pages_ans, value, rule, extra=None, jc=None):
    e = [
        exp(
            "core.has_genai_activity",
            value,
            rule,
            scope="institution",
            **({"judgement_call": jc} if jc else {}),
        )
    ]
    if extra:
        e += extra
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "injected",
            "a_ids": ["A-010"],
            "purpose": purpose,
            "institution": inst(i, name),
            "pages": [
                page(k, f"https://synthetic.example/syn-{i:04d}/{k}", "(injected)")
                for k in pages_ans
            ],
            "injected": {k: v for k, v in pages_ans.items()},
            "expected": e,
        }
    )


TT = "SPEC R-005 / codebook core.has_genai_activity truth table"
s6(
    "v27-syn-A010-01",
    "complete context, all pages negative at p >= 0.8",
    40,
    "Banford Council",
    {
        "p0": {"core.page_verdict": ia("no_genai", 0.92, "not_required")},
        "p1": {"core.page_verdict": ia("confirms_absence", 0.88, "not_required")},
    },
    "no",
    f"{TT}: every attempted page negative at >= 0.8, none ambiguous/failed",
)
s6(
    "v27-syn-A010-02",
    "background_only sits in the `no` set (S2 b)",
    41,
    "Cresswell Council",
    {
        "p0": {"core.page_verdict": ia("background_only", 0.9, "not_required")},
        "p1": {"core.page_verdict": ia("no_genai", 0.95, "not_required")},
    },
    "no",
    f"{TT}; SPEC R-005 RC-D-002 row 6: background_only pages may sit in the institution `no` set (S2 b, the PI variant)",
)
s6(
    "v27-syn-A010-03",
    "a downgraded (low-probability) negative page blocks `no`",
    42,
    "Dunmore Council",
    {
        "p0": {"core.page_verdict": ia("no_genai", 0.62, "downgraded_low_confidence")},
        "p1": {"core.page_verdict": ia("no_genai", 0.95, "not_required")},
    },
    "unclear",
    f"{TT}: any downgraded page counts as unresolved (r2#40); bar is chosen-answer p >= 0.8 (SPEC R-081)",
)
s6(
    "v27-syn-A010-04",
    "an unfollowed link blocks `no`",
    43,
    "Ellerby Council",
    {
        "p0": {
            "core.page_verdict": ia("no_genai", 0.95, "not_required"),
            "unfollowed_links": ["https://synthetic.example/syn-0043/x"],
            "reason": "cap reached",
        }
    },
    "unclear",
    f"{TT}: `no` needs every attempted page incl. failed fetches and unfollowed links negative (A-010 N18)",
    jc="JC-S7",
)
s6(
    "v27-syn-A010-05",
    "procurement-only positive gives `yes` (C5 a)",
    44,
    "Farleigh Council",
    {
        "proc0": {
            "pipeline": "procurement",
            "record": ia(
                "genai_purchase",
                0.95,
                "supported",
                "Award: Microsoft 365 Copilot licences, 120 seats",
            ),
        }
    },
    "yes",
    f"{TT}: any supported GenAI purchase record can give `yes` (C5 a); evidence tier still shows commitment",
    extra=[
        exp(
            "core.evidence_tier",
            "documented_commitment",
            "SPEC R-005 (C5 a); codebook core.evidence_tier rule: commitment = announced, or a tender, contract or payment",
            scope="institution",
            judgement_call="JC-S8",
        )
    ],
)
s6(
    "v27-syn-A010-06",
    "procurement-only negative never gives `no`",
    45,
    "Glenholm Council",
    {"proc0": {"pipeline": "procurement", "record": ia("no_genai_purchase", 0.95, "not_required")}},
    "unclear",
    f"{TT}: `no` from web pages only (r2#44)",
)
s6(
    "v27-syn-A010-07",
    "not_assessable does not block `no` (C1 a)",
    46,
    "Harwood Council",
    {
        "p0": {"core.page_verdict": ia("no_genai", 0.93, "not_required")},
        "p1": {
            "core.page_verdict": {
                "value": "not_assessable",
                "set_by": "mechanical",
                "reason": "not reviewed",
            }
        },
    },
    "no",
    f"{TT}: not_assessable is set mechanically and does not block `no` (C1 a); left out of the rate base",
    jc="JC-S9",
)
s6(
    "v27-syn-A010-08",
    "AI-text detector result never counts",
    47,
    "Ivybridge Council",
    {
        "p0": {"core.page_verdict": ia("no_genai", 0.95, "not_required")},
        "txt0": {"pipeline": "ai_text", "text.published_text_ai_use": ia("likely", 0.97)},
    },
    "no",
    f"{TT}: AI-text results never count (r2#15)",
    jc="JC-S10",
)
s6(
    "v27-syn-A010-09",
    "one supported confirms_activity page gives `yes`",
    48,
    "Jessop Council",
    {
        "p0": {
            "core.page_verdict": ia("confirms_activity", 0.91, "supported", "staff use Copilot"),
            "activities": [{"activity_name": "Copilot for staff", "support": "supported"}],
        },
        "p1": {"core.page_verdict": ia("ambiguous_genai", 0.85, "supported")},
    },
    "yes",
    f"{TT}: `yes` if >= 1 supported confirms_activity page with a supported activity",
)
s6(
    "v27-syn-A010-10",
    "X30 identical-name pair: unresolved relation never merges",
    49,
    "Kirkdale Council",
    {
        "p0": {
            "core.page_verdict": ia("confirms_activity", 0.9, "supported", "AI chatbot launched"),
            "activities": [{"activity_name": "AI chatbot", "support": "supported"}],
        },
        "p1": {
            "core.page_verdict": ia(
                "confirms_activity", 0.9, "supported", "AI chatbot for housing"
            ),
            "activities": [{"activity_name": "AI chatbot", "support": "supported"}],
        },
        "relations": [
            {
                "pair": ["p0:AI chatbot", "p1:AI chatbot"],
                "core.activity_relation_cross_page": ia("unresolved", 0.7),
            }
        ],
    },
    "yes",
    TT,
    extra=[
        exp(
            "n_institution_activities",
            2,
            "SPEC R-005: distinct/unresolved relations never merge; explicit relations before merging (X30)",
            scope="institution",
        )
    ],
)

# ---------------------------------------------------------------- A-020 CX C2-C4 and reworded CX items
A020 = [
    (
        "v27-syn-A020-01",
        "C2: required pre-use review mixing fitness-for-purpose with security checks",
        "Corbridge Council AI guidance: before any generative AI tool is used, the digital team must review "
        "whether it is fit for its intended purpose and complete the information security checklist.",
        [
            exp(
                "core.evaluation_documented",
                "required_or_planned",
                f"{CB} core.evaluation_documented rule: a required pre-use review that mixes fitness-for-purpose with security or compliance checks counts as required_or_planned (CX-01.2 C2 a)",
                scope="activity:AI guidance",
            )
        ],
    ),
    (
        "v27-syn-A020-02",
        "C3 (r11 wording): periodic review of the policy itself is not_documented",
        "Dalton Council Generative AI Policy. This policy will be reviewed every two years by the Head of "
        "Digital.",
        [
            exp(
                "core.evaluation_documented",
                "not_documented",
                f"{CB} core.evaluation_documented rule (r11): a clause requiring periodic review of the GenAI policy itself is not_documented unless it requires testing, monitoring or evaluation of GenAI tools or their outputs",
                scope="activity:Generative AI Policy",
            )
        ],
    ),
    (
        "v27-syn-A020-03",
        "C3 (r11 wording): policy review clause that requires testing of the tools is required_or_planned",
        "Eskdale Council Generative AI Policy. Each year the Head of Digital will review this policy and test "
        "the accuracy of every approved generative AI tool against a sample of council documents.",
        [
            exp(
                "core.evaluation_documented",
                "required_or_planned",
                f"{CB} core.evaluation_documented rule (r11): review clause requiring testing of GenAI tools counts as required_or_planned",
                scope="activity:Generative AI Policy",
            )
        ],
    ),
    (
        "v27-syn-A020-04",
        "C4: an evaluation clearly of a different tool is not_documented",
        "Foxton Council uses Copilot for drafting letters. Separately, last year's audit of the council's "
        "parking-permit database found 12 data-quality errors.",
        [
            exp(
                "core.evaluation_documented",
                "not_documented",
                f"{CB} core.evaluation_documented value unclear definition: an evaluation clearly of a different tool or activity is not_documented, not unclear (CX-01.2 C4 a)",
                scope="activity:Copilot letter drafting",
            )
        ],
    ),
    (
        "v27-syn-A020-05",
        "pilot evaluation with a reported result",
        "After a three-month trial of an AI assistant in Garth Council's housing team, 78% of staff said the "
        "assistant saved them time, according to the pilot evaluation survey.",
        [
            exp(
                "core.evaluation_documented",
                "results_reported",
                f"{CB} core.evaluation_documented worked example (1)",
                scope="activity:housing AI assistant trial",
            ),
            exp(
                "core.evaluation_type_user_feedback",
                "yes",
                f"{CB} core.evaluation_type_user_feedback (survey of staff)",
                scope="activity:housing AI assistant trial",
                judgement_call="JC-S11",
            ),
        ],
    ),
    (
        "v27-syn-A020-06",
        "usage count with no evaluation described",
        "Hartley Council's AI chatbot has answered 40,000 questions since it launched in January.",
        [
            exp(
                "core.evaluation_documented",
                "not_documented",
                f"{CB} core.evaluation_documented worked example (4): a usage count with no evaluation described",
                scope="activity:AI chatbot",
            )
        ],
    ),
]
for n, (fid, purpose, text, ex) in enumerate(A020, start=60):
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "pipeline",
            "a_ids": ["A-020"],
            "purpose": purpose,
            "institution": inst(
                n,
                [
                    "Corbridge Council",
                    "Dalton Council",
                    "Eskdale Council",
                    "Foxton Council",
                    "Garth Council",
                    "Hartley Council",
                ][n - 60],
            ),
            "pages": [page("p0", f"https://synthetic.example/syn-{n:04d}/p0", text)],
            "expected": ex,
        }
    )

# ---------------------------------------------------------------- A-021 chunked pages
LONG = 40000  # filler tokens per block; three blocks put start/end passages in different parts (> 32k tokens each, C-004)


def longpage(i, first, last, middle=None):
    parts = [{"text": first}, {"filler_tokens": LONG, "seed": 1}]
    if middle is not None:
        parts += [{"text": middle}]
    parts += [{"filler_tokens": LONG, "seed": 2}, {"text": last}]
    return [page("p0", f"https://synthetic.example/syn-{i:04d}/p0", text_parts=parts)]


A021P = [
    (
        "v27-syn-A021-01",
        "verdict order across parts: background part loses to a confirms_activity part; quote from the producing part",
        "Briefing note: the national government published its AI strategy this year.",
        "Annex: Lakeside Council deployed Microsoft Copilot to all planning officers in April.",
        [
            exp(
                "core.page_verdict",
                "confirms_activity",
                "SPEC R-044 S3 a verdict order (confirms_activity first); codebook core.page_verdict long_page_rule priority_order",
            ),
            exp(
                "quote_part",
                "last",
                "SPEC R-044: the supporting quote comes from the chunk that produced the code",
                scope="page:p0",
            ),
        ],
    ),
    (
        "v27-syn-A021-02",
        "combined list with mapping step: staff in one part, public in another gives both",
        "Lakeside Council's AI assistant, Ask Lakeside, is available to council staff on the intranet.",
        "Ask Lakeside, the council's AI assistant, is also open to residents on the public website.",
        [
            exp(
                "core.target_users",
                "both",
                f"{CB} core.target_users long_page_rule combined_list map internal_staff + public -> both (activity-22 b)",
                scope="activity:Ask Lakeside",
            )
        ],
    ),
    (
        "v27-syn-A021-03",
        "governance_direction mapping: a ban in one part and a conditional permission in another",
        "Lakeside Council AI policy, section 2: staff must not enter personal data into ChatGPT.",
        "Section 9: staff may use ChatGPT for drafting public information if a manager approves the text.",
        [
            exp(
                "core.governance_direction",
                "restricts_with_conditions",
                "SPEC R-044 (RC-D-005 T-020 readings): a ban in one part and a permission in another give restricts_with_conditions; codebook priority order",
                scope="activity:Lakeside Council AI policy",
            )
        ],
    ),
    (
        "v27-syn-A021-04",
        "earliest year across parts",
        "In 2024 Lakeside Council expanded its AI chatbot to council tax queries.",
        "Lakeside Council first announced its AI chatbot in 2023.",
        [
            exp(
                "core.year_announced",
                2023,
                f"{CB} core.year_announced long_page_rule earliest_year",
                scope="activity:AI chatbot",
                judgement_call="JC-S12",
            )
        ],
    ),
    (
        "v27-syn-A021-05",
        "any-yes function item across parts",
        "Lakeside Council uses a generative AI tool to answer resident questions.",
        "The same generative AI tool also drafts summaries of planning objections for officers.",
        [
            exp(
                "core.function_summarization",
                "yes",
                f"{CB} core.function_summarization long_page_rule any_yes",
                scope="activity:generative AI tool",
            )
        ],
    ),
]
for n, (fid, purpose, first, last, ex) in enumerate(A021P, start=70):
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "pipeline",
            "a_ids": ["A-021"],
            "purpose": purpose,
            "institution": inst(n, "Lakeside Council"),
            "pages": longpage(n, first, last),
            "expected": ex,
        }
    )


def parts(fid, purpose, i, item, part_answers, value, rule, extra=None, jc=None):
    e = [exp(item, value, rule, **({"judgement_call": jc} if jc else {}))]
    if extra:
        e += extra
    F.append(
        {
            "fixture_id": fid,
            "kind": "synthetic",
            "mode": "injected",
            "a_ids": ["A-021"],
            "purpose": purpose,
            "institution": inst(i, "Lakeside Council"),
            "pages": [
                page("p0", f"https://synthetic.example/syn-{i:04d}/p0", "(injected; 3 parts)")
            ],
            "injected": {"p0": {"parts": part_answers, "item": item}},
            "expected": e,
        }
    )


NC = {"value": "not covered by this part"}
parts(
    "v27-syn-A021-06",
    "two-tier verdict order: a supported verdict outranks a failed higher one",
    80,
    "core.page_verdict",
    [
        ia("confirms_activity", 0.9, "downgraded_no_quote"),
        ia("ambiguous_genai", 0.9, "supported", "AI tools at the council"),
        NC,
    ],
    "ambiguous_genai",
    "SPEC R-044 (page-02 b): supported verdicts in the S3 a order, then failed verdicts; a verdict is never rewritten (R-041)",
    extra=[exp("support_status", "supported", f"{CB} core.support_status", scope="page:p0")],
)
parts(
    "v27-syn-A021-07",
    "every part answers 'not covered by this part' for a field: page is not documented",
    81,
    "core.evaluation_documented",
    [NC, NC, NC],
    "not_documented",
    "SPEC R-044 (all-03 a): if every part gives the temporary answer, the page's answer is not documented",
)
parts(
    "v27-syn-A021-08",
    "every part answers 'not covered by this part' for the verdict: not_assessable",
    82,
    "core.page_verdict",
    [NC, NC, NC],
    "not_assessable",
    "SPEC R-044 (RC-D-005 9 a): for the page verdict it is not_assessable",
)
parts(
    "v27-syn-A021-09",
    "most-sure quote: quote and certainty from the highest-certainty part; first-section skips silent part",
    83,
    "core.adoption_stage",
    [
        NC,
        ia("pilot", 0.85, "supported", "pilot started in May"),
        ia("pilot", 0.93, "supported", "the pilot is running in two teams"),
    ],
    "pilot",
    "SPEC R-044 (all-05 a): among parts giving the winning answer, quote and certainty come from the highest-certainty part; ties go to the earliest part",
    extra=[
        exp(
            "supporting_text",
            "the pilot is running in two teams",
            "SPEC R-044 all-05 a",
            scope="activity:pilot",
        ),
        exp("confidence", 0.93, "SPEC R-044 all-05 a", scope="activity:pilot"),
    ],
)
parts(
    "v27-syn-A021-10",
    "missing-answer rank: not_documented outranks unknown",
    84,
    "core.has_human_oversight",
    [
        ia("unknown", 0.9, "downgraded_low_confidence"),
        {"value": "not_documented", "p": 0.9, "support": "not_required"},
        NC,
    ],
    "not_documented",
    "SPEC R-044 (all-04 b): real answers first, then not_documented, then unknown; codebook priority order [yes,no,unclear,not_documented,unknown]",
)
parts(
    "v27-syn-A021-11",
    "first-section rule skips silent and failed parts",
    85,
    "core.source_publication_date",
    [
        NC,
        ia("2025-03-01", 0.6, "downgraded_low_confidence", "1 March 2025"),
        ia("2025-04-10", 0.92, "supported", "10 April 2025"),
    ],
    "2025-04-10",
    f"{CB} core.source_publication_date long_page_rule first_section; SPEC R-044 (all-06 a): first part with a supported real answer, skipping silent or failed parts",
)


# ---------------------------------------------------------------- output
def counts(fixtures):
    by = {}
    for f in fixtures:
        for a in f["a_ids"]:
            by[a] = by.get(a, 0) + 1
    return dict(sorted(by.items()))


def main():
    out = {
        "_about": "T-040 synthetic fixtures; generated by build_synthetic.py; do not hand-edit",
        "fixtures": F,
    }
    (HERE / "synthetic.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(len(F), "synthetic fixtures", counts(F))


if __name__ == "__main__":
    main()
