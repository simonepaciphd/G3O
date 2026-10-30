"""Write the round-4 agent drafts of the empty value definitions (T-010 wording review).

PI ruling 2026-10-30, chat: "a (subagent), accept all" (planning/t010/t010-rulings.md).
Every text below is an agent draft for the PI's line-edit; nothing here is signed.
Reads the codebook to find the empty slots (marker "no approved wording — PI to write");
writes planning/t010/drafts/definitions-r4.json and definitions-r4.md. Fails if a draft is
missing, extra, or aimed at a slot that is not empty.

Run: python make_definitions.py
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
T010 = HERE.parent.parent
CB_PATH = Path("C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml")
OUT_JSON = T010 / "drafts" / "definitions-r4.json"
OUT_MD = T010 / "drafts" / "definitions-r4.md"
EMPTY = "no approved wording"

# Source shorthands (expanded in the output).
SRC = {
    "R1": "planning/t010/codebook-review/codebook-rulings-round1.json",
    "R2": "planning/t010/codebook-review/codebook-rulings-round2.json",
    "R3": "planning/t010/codebook-review/round3/codebook-rulings-round3.json (option text questions-r3.json)",
    "FO": "planning/t010/drafts/final-open.json",
    "CB": "codebook/codebook.yaml (worktree G3O-integrator)",
    "SPEC": "planning/SPEC.md v001.7",
    "PILOT": "C:/Users/spaci/repos/g3o-website/planning/index-design/pilot/pilot.py (frozen CX-01.2 instrument)",
    "CONTACT": "C:/Users/spaci/repos/g3o-website/planning/index-design/pilot/contact.py (frozen CX-01.2 instrument)",
    "CX": "H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/codebook-extension-proposal.md (CX-01.2)",
    "V25": "C:/Users/spaci/worktrees/G3O-integrator/g3o/extract/prompts/output_contract.md (v2.5, 375f1ff)",
    "V26": "C:/Users/spaci/repos/G3O ref 052fcb2 (v2.6)",
    "PROC": "H:/My Drive/Research/G3O/subprojects/procurement-pipeline/config/schema/institution_link.schema.json",
    "COFOG": "UN Classification of the Functions of Government (COFOG), top-level divisions 01-10 — from general knowledge; the official text was not fetched in this session",
}

ALL02 = "R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown)"
CHECK8 = ("The code `unknown` is also a reserved missing-answer label; template check 8 says a value code "
          "never equals one. You may want this value dropped in favour of the reserved label.")


def d(text, sources, conf, no_source=False, decide=None, notes=None):
    return {"text": text, "sources": sources, "confidence": conf, "no_source": no_source,
            "pi_must_decide": decide, "notes": notes}


def unknown_def(thing, extra_src=()):
    return d(f"The page mentions {thing} but does not let it be settled.", [ALL02, *extra_src], "high",
             notes=CHECK8)


def yes_no(yes_text, no_text, sources, conf="high", notes=None):
    return {"yes": d(yes_text, sources, conf, notes=notes), "no": d(no_text, sources, conf, notes=notes)}


EVAL_SRC = ["PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented')",
            "CX CX-41", "CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)"]
EVAL_NOTE = "On the published side, `no` maps to the reserved label \"not documented\" (questionnaire map row)."


def eval_pair(phrase):
    return yes_no(f"The page documents an evaluation of this type for the activity: {phrase}.",
                  f"The page does not document an evaluation of this type ({phrase}) for the activity.",
                  EVAL_SRC, notes=EVAL_NOTE)


FUNC_SRC = ["R1 C11 (function items, yes/no, any-yes across parts)", "V25 L193-202 §4.5 interaction_type definitions and examples"]


def func_pair(phrase):
    return yes_no(f"The page states that the tool is used for {phrase}.",
                  f"The page does not state that the tool is used for {phrase}.",
                  FUNC_SRC, conf="medium")


SEG_NOTE = ("Direction: the pair is read in order (first passage, second passage); the reverse values make that "
            "order necessary (R3 activity-16 b), but no text says which passage is 'first'.")

DRAFTS = {
    # ---- shared list: how we know -------------------------------------------------------------
    ("vocabularies.provenance", "from_metadata"): d(
        "The value comes from the page's metadata or its web address, or is the date the page was fetched; it is not read from the page text.",
        ["R2 n=57 (five shared values)", "R3 shared-01 a (metadata, web address and access date map to from metadata)"], "medium"),
    ("vocabularies.provenance", "looked_up"): d(
        "The value was found in a source other than the page itself, such as a web archive's record of when the page first appeared.",
        ["R2 n=57", "R3 shared-01 a (archive upper bound maps to looked up)"], "medium",
        notes="The only ruled example is the archive date; 'a source other than the page' generalises it."),
    ("vocabularies.provenance", "derived"): d(
        "The value is computed by a rule from other coded values; it is not stated on the page or looked up.",
        ["R2 n=57", "SPEC R-002 (page description items derived from activity codes)"], "medium"),

    # ---- page items ----------------------------------------------------------------------------
    **{("core.page_complete", k): v for k, v in yes_no(
        "The page refers the reader to another page or document for more information about a GenAI activity it mentions, so the page is incomplete (see the note on the name).",
        "The page does not refer the reader elsewhere for more information about any GenAI activity it mentions.",
        ["R1 X17 (question wording)", "FO W04 (yes means incomplete)", "R3 page-01 c"]).items()},
    ("core.content_contact_named", "yes"): d(
        "The page gives a named person, office or unit as responsible for the activity or for questions about it; a named official with no contact details counts.",
        ["CONTACT L30 contact_w4a_named; L42-43 (yes = present on the page)", "CX CX-51 (w4, C1 = a)"], "high"),
    ("core.content_contact_named", "no"): d(
        "The page names no person, office or unit as responsible for the activity or for questions about it. Pages whose verdict shows no GenAI also take this value.",
        ["CONTACT L42-43 (no = not present on the page)", "FO F07 a; FO W03 (other pages take no)"], "high"),
    ("core.content_contact_details", "yes"): d(
        "The page gives contact details anywhere on it: an email address, phone number, postal address or contact form, including press or vendor contacts and site footers.",
        ["CONTACT L31 contact_w4b_details; L42-43", "CX CX-51 (w4)", "R1 X06 (header and footer text given for this item)"], "high"),
    ("core.content_contact_details", "no"): d(
        "No contact details appear anywhere on the page, including its header and footer. Pages whose verdict shows no GenAI also take this value.",
        ["CONTACT L42-43", "R1 X06", "FO F07 a; FO W03"], "high"),

    # ---- links between passages on one page (per pair) ------------------------------------------
    ("core.activity_segment", "same_activity"): d(
        "The two passages describe the same activity: the same action by the same actor on the same tool or instrument.",
        ["CB shared_rules core.rule.activity_unit (SPEC R-017)", "SPEC R-017 list"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "component_of_program"): d(
        "The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.",
        ["CB core.rule.activity_unit", "R3 activity-16 b, activity-17 a"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "has_component"): d(
        "The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.",
        ["R3 activity-16 b (reverse value)", "CB core.rule.activity_unit"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "shared_participation"): d(
        "The two passages describe one joint action in which several bodies take part.",
        ["SPEC R-017 list", "V26 052fcb2:g3o/extract/prompts/system_prompt.md L44-46 ('For a shared action, list explicit participants')"], "low",
        no_source=True, decide="No text defines this link or says whether it merges the two passages. Please word it and say whether it merges.",
        notes=SEG_NOTE),
    ("core.activity_segment", "governs"): d(
        "The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.",
        ["CB core.rule.activity_unit ('linked by a \"governs\" relation')", "R3 activity-17 a (governs wins)"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "governed_by"): d(
        "The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.",
        ["R3 activity-16 b (reverse value)", "R3 activity-17 a"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "distinct_action"): d(
        "The two passages describe different activities, and none of the other links applies.",
        ["SPEC R-017 list", "V26 validate output_contract.md §9 (allowed relations)"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "unresolved"): d(
        "The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.",
        ["SPEC R-005 (unresolved relations never merge)", "V26 validate output_contract.md §8-9"], "medium", notes=SEG_NOTE),
    ("core.activity_segment", "not_an_activity"): d(
        "The passage does not describe an activity as the activity rule defines one.",
        ["R1 C07 ('not an activity' answer per span)", "SPEC R-017 ('plus not-an-activity within a page')"], "low",
        no_source=True, decide="Links are now coded per pair of passages (activity-18 b), but this value describes one passage. Please say how it is used in a pair (for example: either passage is not an activity).",
        notes=SEG_NOTE),

    # ---- whose activity: relationship part ---------------------------------------------------
    ("core.observed_actor_relationship", "this_institution"): d(
        "The searched institution itself carries out or adopts the activity.",
        ["CB core.page_verdict confirms_activity ('carried out or adopted by the named institution itself')", "R3 activity-14 b"], "medium"),
    ("core.observed_actor_relationship", "unit_of_institution"): d(
        "An organisational unit of the searched institution (a department, office or service) carries out the activity; it counts for the institution.",
        ["CB shared_rules core.rule.attribution_grain (R1 C04)", "R3 activity-14 b"], "high"),
    ("core.observed_actor_relationship", "joint_participant"): d(
        "The activity is a joint one, and the page names the searched institution as a participant.",
        ["CB core.rule.attribution_grain (joint rule)", "R3 activity-14 b"], "high"),
    ("core.observed_actor_relationship", "other"): d(
        "The activity belongs to another body: a parent, sibling or neighbouring body, a separate court, board or authority, a similarly named organisation, or a vendor. The searched institution's role is still asked.",
        ["CB core.page_verdict other_body", "CB core.rule.attribution_grain", "deltas/RC-D-003.md:262 (role asked when other)"], "medium"),
    ("core.observed_actor_relationship", "unresolved"): d(
        "The page does not settle whose activity this is. The role of the searched institution is not asked.",
        ["R3 activity-14 b", "deltas/RC-D-003.md:262 (role skipped only when unresolved)"], "medium"),
    # role part
    ("core.observed_actor_relationship", "contracting_authority"): d(
        "The searched institution buys or contracts for the tool or service in its own name.",
        ["R2 n=4", "PROC L31-33 (role enum)", "planning/t010/codebook-review/review-cross-pipeline.json L81"], "medium",
        notes="The procurement schema gives the codes but no definition; this gloss is the ordinary procurement meaning."),
    ("core.observed_actor_relationship", "beneficiary"): d(
        "Another body runs or buys the activity for the searched institution, and the page names the searched institution as benefiting.",
        ["SPEC R-014 ('beneficiary' only when the page names it)", "R2 n=4, n=23"], "high"),
    ("core.observed_actor_relationship", "central_purchasing_body"): d(
        "The searched institution buys or sets up a contract or framework on behalf of other bodies.",
        ["PROC L5 ('a central purchasing body buying on behalf of a department'), L33 (framework establishment)", "R2 n=4"], "medium"),
    ("core.observed_actor_relationship", "unit"): d(
        "The searched institution takes part as a unit of the body that carries out the activity.",
        ["R2 n=4 (role list includes 'unit')", "R3 activity-14 b"], "low", no_source=True,
        decide="No text defines the roles 'unit' and 'joint'. They also repeat the relationship values 'unit of institution' and 'joint participant' (the overlap round 3 noted). Please say what each adds, or drop them."),
    ("core.observed_actor_relationship", "joint"): d(
        "The searched institution takes part as one of several joint participants.",
        ["R2 n=4 (role list includes 'joint')", "R3 activity-14 b"], "low", no_source=True,
        decide="See 'unit': undefined and overlaps the relationship value 'joint participant'."),

    # ---- action type ---------------------------------------------------------------------------
    ("core.action_type", "deployment"): d(
        "The institution puts a GenAI tool to use, or tries one out, for its own work or for the public. The stage and the purchase status are coded separately.",
        ["R1 A02", "R2 n=11 c (stage and procurement status carry proposals and purchases)"], "medium"),
    ("core.action_type", "governance"): d(
        "The institution issues or applies a rule on GenAI use: a policy, guidance, approved-tool list, order or standard. A body that sets or oversees such rules also counts.",
        ["R1 A02, A03", "R3 activity-04 d"], "medium"),
    ("core.action_type", "staff_training"): d(
        "The institution trains its own staff to use GenAI.",
        ["R1 A02", "CB core.page_verdict confirms_activity ('institution-directed staff GenAI training')"], "high"),
    ("core.action_type", "program"): d(
        "A container activity whose named components are each their own activity, linked to it. Used only when the page names the components.",
        ["R2 n=11 c ('a container used only with named components')", "CB core.rule.activity_unit"], "high"),
    ("core.action_type", "unknown"): unknown_def("the activity", ["R1 A02"]),

    # ---- purchase status -----------------------------------------------------------------------
    ("core.procurement_status", "none_documented"): d(
        "The page documents the activity but no purchase step for it.",
        ["R1 C09"], "medium",
        notes="This value is close to the reserved label \"not documented\"; you may want to say how the two differ."),
    ("core.procurement_status", "tender_or_rfp"): d(
        "The institution has issued a call for tenders, a request for proposals or a similar invitation to bid for the tool or service.",
        ["R1 C09"], "medium"),
    ("core.procurement_status", "award_or_contract"): d(
        "A contract, award or licence agreement for the tool or service is reported as made.",
        ["R1 C09"], "medium"),
    ("core.procurement_status", "payment_or_subscription"): d(
        "The page records a payment, invoice or subscription for the tool or service. On its own this does not show use; the stage is then unknown unless use is shown.",
        ["R1 C09", "R2 n=14", "V26 052fcb2:g3o/extract/prompts/system_prompt.md ('payment is procurement, not production')"], "high"),
    ("core.procurement_status", "unknown"): unknown_def("a purchase of the tool or service", ["R1 C09"]),

    # ---- model origin / build arrangement ------------------------------------------------------
    ("core.model_origin", "commercial"): d(
        "The model comes from a commercial provider (for example OpenAI, Microsoft, Google or Anthropic) and is used through its product, licence or programming interface.",
        ["R1 C10", "V25 L182 proprietary_vendor"], "medium"),
    ("core.model_origin", "open_weight"): d(
        "The model's weights are openly released (for example Llama, Mistral or Falcon), whether the institution or a provider runs it.",
        ["R1 C10", "V25 L183 open_source"], "medium"),
    ("core.model_origin", "government_developed"): d(
        "The model was developed by or for a government (for example France's Albert or Germany's OpenGPT-X), including by the institution's own team.",
        ["R1 C10", "V25 L184 sovereign_model, L185 in_house"], "medium",
        notes="v2.5 kept 'in house' apart from 'sovereign'; this draft folds both into one value. You may want them kept apart."),
    ("core.model_origin", "unknown"): unknown_def("the model behind the tool", ["R1 C10"]),
    ("core.build_arrangement", "off_the_shelf_product"): d(
        "The institution uses a ready-made product as supplied (for example a commercial chat assistant or an office-suite assistant), set up but not built on.",
        ["R1 C10"], "medium"),
    ("core.build_arrangement", "custom_application_on_external_model"): d(
        "The institution, or a contractor for it, built its own application (a chatbot, assistant or workflow) on a model it did not train.",
        ["R1 C10"], "medium"),
    ("core.build_arrangement", "model_trained_or_fine_tuned_by_institution"): d(
        "The institution, or a contractor for it, trained or fine-tuned the model itself. Internal use alone does not show this.",
        ["R1 C10", "V26 052fcb2:g3o/extract/prompts/system_prompt.md ('internal use does not prove in-house development')"], "medium"),
    ("core.build_arrangement", "unknown"): unknown_def("how the tool was built", ["R1 C10"]),

    # ---- interface -----------------------------------------------------------------------------
    ("core.interface", "conversational"): d(
        "Users type or speak to the tool in a chat or question-and-answer exchange, as with a chatbot or assistant window.",
        ["R2 n=20 b", "V25 L193 chatbot ('Conversational interface for Q&A, navigation, or retrieval')"], "medium"),
    ("core.interface", "backend_or_api"): d(
        "The tool runs behind the scenes, or other software calls it through a programming interface; users do not talk to it directly.",
        ["R2 n=20 b", "R1 C11"], "medium"),
    ("core.interface", "other_interface"): d(
        "Users reach the tool in another way than a chat exchange or a back-end connection.",
        ["R2 n=20 b ('other interface')"], "low",
        notes="Kept minimal: the ruling names the value only. Integrated versus standalone is carried by deployment mode (R2 n=20 b), not here."),

    # ---- functions -----------------------------------------------------------------------------
    **{(f"core.function_{f}", k): v for f, phrase in [
        ("drafting_writing", "drafting or writing text, such as memos, letters, press releases or social media posts"),
        ("summarization", "summarising documents, reports or meetings"),
        ("translation", "translating text or speech between languages"),
        ("search_retrieval", "finding information, such as answering questions from documents or searching the institution's own records"),
        ("code", "writing, reviewing or fixing software code"),
        ("image_audio_video", "creating or editing images, audio or video"),
        ("extraction_classification", "pulling information out of documents or forms, or sorting and classifying them"),
        ("analysis_recommendation", "analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks"),
    ] for k, v in func_pair(phrase).items()},

    # ---- deployment mode / audiences -----------------------------------------------------------
    ("core.deployment_mode", "unknown"): unknown_def("whether the tool is separate or built into existing software", ["R1 C14"]),
    ("core.target_users", "internal_staff"): d(
        "Only the institution's own staff use the tool.",
        ["R1 C15", "V25 L104 ('Who interacts with the GenAI system')"], "medium"),
    ("core.target_users", "public"): d(
        "People outside the institution use the tool: members of the public, residents or businesses.",
        ["R1 C15", "V25 L104"], "medium"),
    ("core.target_users", "both"): d(
        "Both the institution's staff and people outside it use the tool. On long pages, one part naming staff and another the public also gives this value.",
        ["V25 L104", "FO F03 a", "R3 activity-22 b"], "high"),
    ("core.target_users", "unknown"): unknown_def("who uses the tool", ["R1 C15"]),
    ("core.governed_population", "internal_personnel"): d(
        "The rule applies to the institution's own staff and officials.",
        ["R1 A04"], "medium"),
    ("core.governed_population", "external_users"): d(
        "The rule applies to people or bodies outside the institution, such as the public or the parties it regulates.",
        ["R1 A04"], "medium"),
    ("core.governed_population", "both"): d(
        "The rule applies both to the institution's own staff and to people or bodies outside it. On long pages, one part naming each also gives this value.",
        ["R1 A04", "FO F03 a", "R3 activity-22 b"], "high"),
    ("core.governed_population", "unknown"): unknown_def("whom the rule applies to", ["R1 A04"]),

    # ---- governance form / direction -----------------------------------------------------------
    ("core.governance_form", "dedicated_genai_or_ai_policy_or_guideline"): d(
        "A policy, guideline, code of practice or acceptable-use rule whose main subject is generative AI or AI.",
        ["R1 A03", "CB core.activity_type policy_guidance (v2.5)"], "medium"),
    ("core.governance_form", "approved_tool_list_or_endorsement"): d(
        "A list of approved or permitted GenAI tools, or an official endorsement of a named tool.",
        ["R1 A03"], "medium"),
    ("core.governance_form", "clause_in_instrument_on_other_subject"): d(
        "A clause on GenAI inside a rule, policy or guidance whose main subject is something else (for example IT security or records management).",
        ["R1 A03"], "medium"),
    ("core.governance_form", "court_or_regulatory_order"): d(
        "An order, decision or practice direction on GenAI use issued by a court or a regulator.",
        ["R1 A03"], "medium"),
    ("core.governance_form", "procurement_standard"): d(
        "A standard or requirement for buying GenAI tools or services, such as purchasing criteria or contract terms.",
        ["R1 A03", "CB core.activity_type policy_guidance ('procurement standards', v2.5)"], "medium"),
    ("core.governance_form", "unknown"): unknown_def("the form of the rule", ["R1 A03"]),
    ("core.governance_direction", "prohibits"): d(
        "The rule bans the GenAI use it covers, with no use allowed.",
        ["R2 n=58", "R3 activity-11 a (any mix of ban and permission is restricts with conditions)"], "medium"),
    ("core.governance_direction", "restricts_with_conditions"): d(
        "The rule allows use only under conditions (for example approval, training, limits on data, or human review), or bans some uses and allows others. On long pages, a ban in one part and a permission in another also give this value.",
        ["R2 n=58", "R3 activity-11 a"], "high"),
    ("core.governance_direction", "permits"): d(
        "The rule allows the use without conditions.",
        ["R3 activity-11 a ('Permits only when use is allowed without conditions')"], "high"),
    ("core.governance_direction", "requires"): d(
        "The rule makes GenAI use mandatory for some task or for some staff.",
        ["R3 activity-10 b (situation: 'a binding duty to use GenAI')"], "medium"),
    ("core.governance_direction", "promotes"): d(
        "The rule encourages or supports GenAI use without making it mandatory.",
        ["R3 activity-10 b (situation: 'encouragement')"], "medium"),

    # ---- service area (COFOG top level) ----------------------------------------------------------
    ("core.service_domain", "general_public_services"): d(
        "Running government itself: executive and legislative bodies, financial, fiscal and tax affairs, foreign affairs, and general administration and internal services. The earlier value 'general administration' is coded here.",
        ["R3 activity-12 b", "COFOG division 01", "FO F09 a"], "medium",
        notes="Check every COFOG gloss against the official text before signing."),
    ("core.service_domain", "defence"): d("Military and civil defence.", ["R3 activity-12 b", "COFOG division 02"], "medium"),
    ("core.service_domain", "public_order_safety"): d(
        "Police, fire protection, the courts and prisons.", ["R3 activity-12 b", "COFOG division 03"], "medium"),
    ("core.service_domain", "economic_affairs"): d(
        "Economic, commercial and labour affairs; agriculture, forestry and fishing; fuel and energy; industry and construction; transport; communication.",
        ["R3 activity-12 b", "COFOG division 04"], "medium"),
    ("core.service_domain", "environmental_protection"): d(
        "Waste and waste-water management, pollution control, and the protection of biodiversity and landscape.",
        ["R3 activity-12 b", "COFOG division 05"], "medium"),
    ("core.service_domain", "housing_community_amenities"): d(
        "Housing and community development, water supply and street lighting.",
        ["R3 activity-12 b", "COFOG division 06"], "medium"),
    ("core.service_domain", "health"): d(
        "Medical products, outpatient and hospital services, and public health services.",
        ["R3 activity-12 b", "COFOG division 07"], "medium"),
    ("core.service_domain", "recreation_culture_religion"): d(
        "Recreation and sport, culture, broadcasting and publishing, and religious and other community services.",
        ["R3 activity-12 b", "COFOG division 08"], "medium"),
    ("core.service_domain", "education"): d(
        "Education at every level, from pre-primary to university, and services that support it.",
        ["R3 activity-12 b", "COFOG division 09"], "medium"),
    ("core.service_domain", "social_protection"): d(
        "Support in sickness and disability, old age, for survivors, families and children, in unemployment, for housing, and against social exclusion.",
        ["R3 activity-12 b", "COFOG division 10"], "medium"),
    ("core.service_domain", "other"): d(
        "An area that fits none of the ten areas above.",
        ["R3 activity-13 a ('Activities that fit no area get \"other\"')"], "high",
        notes="The value has no label yet (fold-log round 3 §4 item 9)."),

    # ---- how GenAI was established -------------------------------------------------------------
    ("core.genai_mechanism_basis", "named_genai_product_or_model"): d(
        "The page names a generative product or model, such as ChatGPT, Copilot, Gemini, Claude or a named language model.",
        ["R1 A01", "CB core.page_verdict confirms_activity (named products)"], "high"),
    ("core.genai_mechanism_basis", "explicit_genai_label"): d(
        "The page calls the tool generative AI, a large language model or the like, without naming a product.",
        ["R1 A01", "CB core.page_verdict confirms_activity ('explicitly generative AI')"], "medium"),
    ("core.genai_mechanism_basis", "generative_capability_described"): d(
        "The page says the tool generates text, images, audio, code or other content, without naming a product or using a generative-AI label.",
        ["R1 A01", "CB core.page_verdict confirms_activity ('says the tool generates text, images, audio, code or other content')"], "high"),
    ("core.genai_mechanism_basis", "ai_chatbot_or_assistant_label_only"): d(
        "The only signal is that the page calls the tool an 'AI chatbot' or 'AI assistant'; under the GenAI boundary rule this counts as generative.",
        ["R1 A01, C02", "CB shared_rules core.rule.genai_boundary (SPEC R-016)"], "high",
        notes="No order is stated for an activity where several of these four fit."),

    # ---- scale unit ----------------------------------------------------------------------------
    ("core.deployment_scale_unit", "licences_or_seats"): d(
        "The number counts licences, seats or accounts bought or issued.", ["R1 A09"], "medium"),
    ("core.deployment_scale_unit", "users"): d(
        "The number counts people who use the tool.", ["R1 A09"], "medium"),
    ("core.deployment_scale_unit", "interactions"): d(
        "The number counts uses of the tool, such as questions answered, conversations held or documents handled.",
        ["R1 A09", "CX CX-40 example 4 ('the chatbot has answered 40,000 questions')"], "medium"),
    ("core.deployment_scale_unit", "units_or_departments"): d(
        "The number counts offices, departments, schools or other units that use the tool.", ["R1 A09"], "medium"),
    ("core.deployment_scale_unit", "none"): d(
        "A number is stated, but it counts none of these units.",
        ["R1 A09", "CB core.deployment_scale_unit gate (asked when a number is stated)"], "medium"),

    # ---- evaluation types (frozen wording) -------------------------------------------------------
    **{(f"core.evaluation_type_{t}", k): v for t, phrase in [
        ("pre_deployment_testing", "testing before deployment"),
        ("pilot_evaluation", "evaluation of a pilot or trial"),
        ("independent_audit", "an audit or evaluation by an independent body"),
        ("ongoing_monitoring", "ongoing monitoring of the tool in use"),
        ("user_feedback", "user feedback or satisfaction surveys"),
        ("bias_or_safety_testing", "bias, fairness or safety testing"),
    ] for k, v in eval_pair(phrase).items()},

    # ---- quote check -----------------------------------------------------------------------------
    ("core.support_entailment", "true"): d(
        "The quoted text states that the field has the given value.",
        ["R1 X35 (question 'Does this text state that <field> is <value>?')"], "high"),
    ("core.support_entailment", "false"): d(
        "The quoted text does not state that the field has the given value. The answer's support status becomes 'downgraded: quote does not state the value'.",
        ["R1 X35", "SPEC R-041 (spelling downgraded_quote_not_stating_value, all-11)"], "high"),

    # ---- links between activities across pages (institution level) ------------------------------
    ("core.activity_relation_cross_page", "same_activity"): d(
        "The two activity records describe the same activity: the same action by the same actor on the same tool or instrument. Only records joined by this link are merged.",
        ["CB core.rule.activity_unit", "SPEC R-005 / R1 X30 (merging needs explicit same-activity links)"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "component_of_program"): d(
        "The first record's activity is a named component of the program in the second. Both stay separate activities, linked.",
        ["R3 activity-16 b, activity-17 a", "CB core.rule.activity_unit"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "has_component"): d(
        "The first record describes a program, and the second record's activity is one of its named components. Both stay separate activities, linked.",
        ["R3 activity-16 b", "CB core.rule.activity_unit"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "shared_participation"): d(
        "The two records describe one joint action in which several bodies take part.",
        ["SPEC R-017 list", "V26 validate output_contract.md §9"], "low", no_source=True,
        decide="As within a page: no text defines this link or says whether it merges the two records.",
        notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "governs"): d(
        "The first record's activity is a policy or other governance instrument that sets rules for the activity in the second. When a pair fits both this link and a component link, this link is used.",
        ["CB core.rule.activity_unit", "R3 activity-17 a"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "governed_by"): d(
        "The second record's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.",
        ["R3 activity-16 b, activity-17 a"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "distinct_action"): d(
        "The two records describe different activities, and none of the other links applies. The value is stored with a rule note.",
        ["SPEC R-017 list", "R3 institution-02 a ('Store the distinct value with a rule note')"], "medium", notes=SEG_NOTE.replace("passage", "record")),
    ("core.activity_relation_cross_page", "unresolved"): d(
        "The sources do not settle whether the two records describe the same activity. They are never merged.",
        ["SPEC R-005 ('distinct/unresolved relations never merge')", "V26 validate output_contract.md §8-9"], "high", notes=SEG_NOTE.replace("passage", "record")),

    # ---- actor's own role (internal) -----------------------------------------------------------
    **{("core.observed_actor_role", c): d(t, ["R3 activity-15 a (kept as before, internal)", "V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)"], "medium",
                                          no_source=True,
                                          decide="The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.")
       for c, t in [
           ("institutional_actor", "The actor seen on the page carries out or adopts the activity as an institution."),
           ("issuer", "The actor issued the policy, rule, guidance or document."),
           ("participant", "The actor takes part in an activity that someone else runs."),
           ("external_speaker", "The actor speaks or presents about GenAI, for example at an event, without carrying out the activity."),
           ("service_provider", "The actor supplies the tool or service, as a vendor, contractor or developer."),
           ("event_host", "The actor hosts or organises an event about GenAI."),
       ]},

    # ---- second reason ----------------------------------------------------------------------------
    ("core.support_status_second_reason", "downgraded_no_quote"): d(
        "The answer also failed because it has no supporting quote.",
        ["FO F10 a", "SPEC R-041"], "medium", no_source=True,
        decide="Under the approved order (quote check first, then the 0.8 bar), a missing quote is always the main reason, so this value seems never to occur as the second reason. Please confirm the value list or the order."),
    ("core.support_status_second_reason", "downgraded_low_confidence"): d(
        "The answer also failed because the classifier's certainty was below the 0.8 bar.",
        ["FO F10 a", "SPEC R-041"], "high"),
    ("core.support_status_second_reason", "downgraded_quote_not_stating_value"): d(
        "The answer also failed because its quote does not state the value.",
        ["FO F10 a", "SPEC R-041"], "medium", no_source=True,
        decide="Same as 'no quote': the quote-meaning check is part of the quote check, which comes first, so this seems never to be the second reason. Please confirm."),
}


def empty_slots(cb):
    """Yield (slot_path, owner, code, part) for every empty definition slot."""
    out = []

    def walk(x, p):
        if isinstance(x, dict):
            if str(x.get("marker", "")).startswith(EMPTY):
                out.append(p)
            for k, v in x.items():
                walk(v, p + (k,))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, p + (i,))
    walk(cb, ())
    res = []
    for p in out:
        node = cb
        for k in p[:-1]:
            node = node[k]
        owner = p[1] if p[0] == "items" else f"{p[0]}.{p[1]}"
        part = p[3] if (p[0] == "items" and p[2] == "values" and isinstance(p[3], str)) else None
        res.append(("/".join(map(str, p)), owner, node["code"], part))
    return res


def main():
    cb = yaml.safe_load(CB_PATH.read_text(encoding="utf-8"))
    slots = empty_slots(cb)
    keys = {(o, c) for _, o, c, _ in slots}
    if len(keys) != len(slots):
        sys.exit("two empty slots share (owner, code)")
    missing = keys - DRAFTS.keys()
    extra = DRAFTS.keys() - keys
    if missing or extra:
        sys.exit(f"missing drafts {sorted(missing)}; extra drafts {sorted(extra)}")
    entries = []
    for path, owner, code, part in slots:
        dr = DRAFTS[(owner, code)]
        entries.append({"slot": path, "item": owner, "code": code, "part": part, "origin": "agent draft r4",
                        "marker": "Agent draft (round 4) — PI to write or line-edit", **dr})
    doc = {
        "format": "t010-definitions-r4-v1",
        "status": "DRAFT — agent wording for PI line-edit; nothing signed",
        "draft_by": "Claude Code, claude-opus-5-5, drafting subagent (fork) of integrator session 20261030-claude-v2-2b8200388885f8f9",
        "date": "2026-10-30",
        "ruling": 'PI, chat, 2026-10-30, verbatim: "a (subagent), accept all" (planning/t010/t010-rulings.md)',
        "codebook": str(CB_PATH),
        "source_keys": SRC,
        "fold_note": "Keyed by codebook slot path; a later fold through build_skeleton.py takes `text` verbatim with origin 'agent draft r4', replaced by the PI's edit where she gives one.",
        "counts": {"drafts": len(entries), "no_source": sum(e["no_source"] for e in entries),
                   "confidence": {c: sum(e["confidence"] == c for e in entries) for c in ("high", "medium", "low")}},
        "entries": entries,
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = ["# Round-4 drafts of the empty value definitions (DRAFT, agent wording)", "",
          f"{doc['ruling']}. Drafted by {doc['draft_by']}, {doc['date']}. Every text is for your line-edit; nothing is signed.", "",
          f"{len(entries)} drafts; {doc['counts']['no_source']} flagged `no_source`; confidence {doc['counts']['confidence']}.", "",
          "Source keys: " + "; ".join(f"**{k}** = {v}" for k, v in SRC.items()), ""]
    cur = None
    for e in entries:
        if e["item"] != cur:
            cur = e["item"]
            md += ["", f"## {cur}", ""]
        part = f" ({e['part']})" if e["part"] else ""
        flag = " **[no_source]**" if e["no_source"] else ""
        md.append(f"- `{e['code']}`{part} — {e['text']}  \n  _confidence {e['confidence']}{flag}; sources: {'; '.join(e['sources'])}_"
                  + (f"  \n  PI must decide: {e['pi_must_decide']}" if e["pi_must_decide"] else "")
                  + (f"  \n  Note: {e['notes']}" if e["notes"] else ""))
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"drafts={len(entries)} no_source={doc['counts']['no_source']} {doc['counts']['confidence']} -> {OUT_JSON}")


if __name__ == "__main__":
    main()
