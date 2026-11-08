"""Proxy questions for T-002, copied verbatim (by AST literal extraction, not retyped) from:
 - RS-004 unclear2.py (re-pilot 2 verdict question): VERDICT and its instruction string;
 - RS-024 pilot.py (CX pilot v2, 19 questions): FORM, SCOPE, CONTENT, EVAL, EVAL_TYPES, EVAL_EMPHASIS and the
   instruction templates in page_questions() / type_questions().
test_t002.py::test_proxy_text_is_verbatim re-checks every string against the source files.
"""

SOURCE_UNCLEAR2 = "H:/My Drive/Research/G3O/agent-workspace/2026-10-27-unclear-screen/unclear2.py"
SOURCE_PILOT = ("H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/"
                "index-design/pilot/pilot.py")

VERDICT = {'confirms_activity': 'The page documents a specific generative-AI activity AT THIS institution: its own GenAI tool, '
                      'pilot, policy or guidance on GenAI, procurement, deployment, or institution-directed staff '
                      'GenAI training. The text must be explicitly generative AI (LLMs, ChatGPT, Copilot, Gemini, AI '
                      'chatbots, AI-generated content or equivalents) and tied to this institution, not only to a '
                      'national programme or another body. The activity must be carried out or adopted by the named '
                      'institution itself. Exclude activity by a parent, higher-level or neighbouring body (e.g. a '
                      'district, county, regency, region, consortium or city department when the named institution '
                      'is a village, ward or sub-unit), by a similarly named organisation or company, and pages by '
                      "vendors that only use the place name. Generic 'AI', 'artificial intelligence', 'smart' "
                      'systems, automation, analytics, prediction, transcription, translation, image or video '
                      'recognition, or traditional machine-learning tools do not count unless the page says the tool '
                      'generates text, images, audio, code or other content, or names a generative product or model '
                      '(e.g. ChatGPT, Copilot, Gemini, Claude, an LLM, an AI chatbot or AI assistant).',
 'ambiguous_genai': 'The page mentions AI at this institution, but it cannot be settled whether it is generative AI '
                    "(e.g. a generic 'AI strategy', 'AI tools', analytics, traditional machine learning).",
 'ambiguous_attribution': 'The page mentions generative AI, but it cannot be settled whether THIS institution is '
                          'involved (e.g. a country-wide or regional GenAI initiative without confirmation that this '
                          'institution takes part, or a page about a similarly named body).',
 'other_body': 'The page documents a generative-AI activity, but it clearly belongs to a different body, not the '
               'named institution: a parent, higher-level or neighbouring body (e.g. a district, county, regency, '
               'region, consortium or city department when the named institution is a village, ward or sub-unit), a '
               'similarly named organisation or company, or a vendor or marketing page that only uses the place '
               'name.',
 'event_only': 'The only GenAI content is a public-facing event, workshop, seminar, showcase or educational '
               'programme, with no documented adoption, procurement, deployment or governance by the institution '
               'itself (WS10 D1: not a qualifying activity).',
 'background_only': 'The page gives only general context (national AI strategy, vendor overview, news about GenAI in '
                    'general) and documents no activity at this institution.',
 'no_genai': 'The page contains no generative-AI content relevant to this institution.'}

EVAL_SET = ('results_reported', 'conducted_no_results', 'required_or_planned')

FORM = {'register_cross_institution': 'CX-10: the page is, or is one entry in, a structured list of AI or algorithmic '
                               'systems kept by a government body, with several entries in a common format '
                               '(inventory, register, catalogue, algorithmic transparency record in a standard '
                               'template), and the list covers more than one institution.',
 'register_single_institution': "CX-10b: as above, but the list covers one institution only (e.g. a city's own table "
                                'of its AI tools).',
 'mandated_report': 'CX-12/13: a document produced to meet a reporting obligation (statutory annual-report section, '
                    'compliance or transparency report under a rule). The obligation may be named on the page or '
                    "inferred from the document's genre (e.g. an annual report).",
 'formal_record': 'CX-14: an official one-off document of record from a government body: adopted policy or guidance, '
                  'legislation, council or board minutes or resolutions, budget documents, procurement notice or '
                  'award, audit or inspection report, response to a freedom-of-information request.',
 'informal_official': "CX-15: a government body's own communication with no reporting obligation and no standard "
                      'format: press release, news item, blog, social post, speech, event page, service or FAQ page.',
 'third_party': 'CX-16: not published by a government body: news, vendor, academic, NGO or policy organization. A '
                'register entry quoted in a news article is third_party.',
 'unknown': "CX-17: the page's kind cannot be determined from its text."}

SCOPE = {'whole_of_government': 'CX-21: the listing or document the page belongs to covers institutions across the '
                        'government (all central agencies, or all units of a level).',
 'multi_institution': 'CX-22: it covers several institutions, but not government-wide (a sector, a region, a group '
                      'of agencies).',
 'single_institution': 'CX-23: it covers one institution only.',
 'unknown': 'CX-24: coverage cannot be determined from the page.'}

CONTENT = {'content_purpose': 'what the GenAI tool or activity is used for',
 'content_tool_or_model': 'the GenAI product or model is named',
 'content_vendor': 'the supplier or vendor is named',
 'content_data': 'the data inputs or data handled are described',
 'content_users': 'who uses it or who is affected is described',
 'content_status_date': 'the deployment status or a date is stated',
 'content_contact': 'any contact point (person, unit, email, phone), including press or vendor contacts and site '
                    'footers',
 'content_human_oversight': 'human review or oversight of GenAI outputs is described',
 'content_risk_assessment': 'a risk or impact assessment is described',
 'content_user_notification': 'a notice or label telling users that they are interacting with GenAI or that content '
                              'is AI-generated is described (a page merely announcing that the institution uses '
                              'GenAI is NOT such a notice)'}

EVAL = {'results_reported': 'CX-30: the page states that this activity was tested, evaluated, audited or monitored AND '
                     'reports a result (a metric, a finding or a conclusion). A performance figure counts only if '
                     'the page also describes the evaluation activity behind it (CX-36).',
 'conducted_no_results': 'CX-31: the page states that an evaluation, test, audit, pilot review or monitoring took '
                         'place or is in place, but reports no result.',
 'required_or_planned': 'CX-32: the page states that an evaluation is required (by a rule) or planned, with no '
                        'evidence that it has happened. A policy that requires evaluation of GenAI tools takes this '
                        'value, and so does a clause requiring periodic review of the GenAI policy itself (CX-32c). '
                        'A requirement to carry out a risk or impact assessment is NOT this value (CX-32b).',
 'unclear': 'CX-33: the page makes an evaluative statement, but its subject, or whether it concerns this GenAI '
            'activity, cannot be settled.',
 'not_documented': 'CX-34/35: no evaluation statement about this activity, including a page saying no evaluation was '
                   'done. A pilot stage alone, a usage count, or a vendor performance claim with no institution or '
                   'independent evaluator named is not_documented. A risk or impact assessment alone is '
                   'not_documented unless it reports testing or measured performance (CX-37-39).'}

EVAL_TYPES = {'evaluation_type_pre_deployment_testing': 'testing before deployment',
 'evaluation_type_pilot_evaluation': 'evaluation of a pilot or trial',
 'evaluation_type_independent_audit': 'an audit or evaluation by an independent body',
 'evaluation_type_ongoing_monitoring': 'ongoing monitoring of the tool in use',
 'evaluation_type_user_feedback': 'user feedback or satisfaction surveys',
 'evaluation_type_bias_or_safety_testing': 'bias, fairness or safety testing'}

EVAL_EMPHASIS = (' Rules: consider only evaluation of THIS activity and its own tool; an evaluation of a different tool or activity '
 'does not count (CX-02). A trial run or reported by a vendor counts only if the institution or an independent body '
 'is named as the evaluator (CX-38). Starting or announcing a pilot is not an evaluation (CX-39). A risk or impact '
 'assessment is not an evaluation unless it reports testing or measured performance (CX-37, CX-32b). A performance '
 'figure counts only if the page describes the evaluation behind it (CX-36).')
# Instruction strings, copied from the source call sites (unclear2.py:84-85; pilot.py:193, 196, 199, 203, 210).
VERDICT_INSTRUCTIONS = ("Code this PAGE for the named institution only, using only what the page says. Does it document a "
                        "generative-AI activity at this institution? If several values fit, take the first in this order.")
FORM_INSTRUCTIONS = "Code the source PAGE (not the activity, not what it quotes), using only what the page says. What kind of document is this page? If several values fit, take the first in this order."
SCOPE_INSTRUCTIONS = "Code the source PAGE. How many institutions does the listing or document this page belongs to cover?"
EVAL_INSTRUCTIONS = "Code this page for the named GenAI activity only. Does the page document an evaluation of this activity? If several values fit, take the first in this order." + EVAL_EMPHASIS
CONTENT_INSTRUCTIONS_TEMPLATE = "Code the source PAGE. Does the page state this about the GenAI activity: {v}? yes = stated on the page."
CONTENT_CRITERIA = {"yes": "stated on the page", "no": "not stated on the page"}
TYPE_INSTRUCTIONS_TEMPLATE = "The page documents an evaluation, or a requirement or plan for one, of the named GenAI activity. Does it document an evaluation of this type: {v}?"
TYPE_CRITERIA = {"yes": "documented on the page", "no": "not documented"}

VERDICT_ORDER = list(VERDICT)  # unclear2.py ORDER: combine chunks by the first value in this order
GENAI_BEARING = ("confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only")
