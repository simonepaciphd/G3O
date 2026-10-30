# Round-4 drafts of the empty value definitions (DRAFT, agent wording)

PI, chat, 2026-10-30, verbatim: "a (subagent), accept all" (planning/t010/t010-rulings.md). Drafted by Claude Code, claude-opus-5-5, drafting subagent (fork) of integrator session 20261030-claude-v2-2b8200388885f8f9, 2026-10-30. Every text is for your line-edit; nothing is signed.

136 drafts; 13 flagged `no_source`; confidence {'high': 44, 'medium': 86, 'low': 6}.

Source keys: **R1** = planning/t010/codebook-review/codebook-rulings-round1.json; **R2** = planning/t010/codebook-review/codebook-rulings-round2.json; **R3** = planning/t010/codebook-review/round3/codebook-rulings-round3.json (option text questions-r3.json); **FO** = planning/t010/drafts/final-open.json; **CB** = codebook/codebook.yaml (worktree G3O-integrator); **SPEC** = planning/SPEC.md v001.7; **PILOT** = C:/Users/spaci/repos/g3o-website/planning/index-design/pilot/pilot.py (frozen CX-01.2 instrument); **CONTACT** = C:/Users/spaci/repos/g3o-website/planning/index-design/pilot/contact.py (frozen CX-01.2 instrument); **CX** = H:/My Drive/Research/G3O/archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/codebook-extension-proposal.md (CX-01.2); **V25** = C:/Users/spaci/worktrees/G3O-integrator/g3o/extract/prompts/output_contract.md (v2.5, 375f1ff); **V26** = C:/Users/spaci/repos/G3O ref 052fcb2 (v2.6); **PROC** = H:/My Drive/Research/G3O/subprojects/procurement-pipeline/config/schema/institution_link.schema.json; **COFOG** = UN Classification of the Functions of Government (COFOG), top-level divisions 01-10 — from general knowledge; the official text was not fetched in this session


## vocabularies.provenance

- `from_metadata` — The value comes from the page's metadata or its web address, or is the date the page was fetched; it is not read from the page text.  
  _confidence medium; sources: R2 n=57 (five shared values); R3 shared-01 a (metadata, web address and access date map to from metadata)_
- `looked_up` — The value was found in a source other than the page itself, such as a web archive's record of when the page first appeared.  
  _confidence medium; sources: R2 n=57; R3 shared-01 a (archive upper bound maps to looked up)_  
  Note: The only ruled example is the archive date; 'a source other than the page' generalises it.
- `derived` — The value is computed by a rule from other coded values; it is not stated on the page or looked up.  
  _confidence medium; sources: R2 n=57; SPEC R-002 (page description items derived from activity codes)_

## core.page_complete

- `yes` — The page refers the reader to another page or document for more information about a GenAI activity it mentions, so the page is incomplete (see the note on the name).  
  _confidence high; sources: R1 X17 (question wording); FO W04 (yes means incomplete); R3 page-01 c_
- `no` — The page does not refer the reader elsewhere for more information about any GenAI activity it mentions.  
  _confidence high; sources: R1 X17 (question wording); FO W04 (yes means incomplete); R3 page-01 c_

## core.content_contact_named

- `yes` — The page gives a named person, office or unit as responsible for the activity or for questions about it; a named official with no contact details counts.  
  _confidence high; sources: CONTACT L30 contact_w4a_named; L42-43 (yes = present on the page); CX CX-51 (w4, C1 = a)_
- `no` — The page names no person, office or unit as responsible for the activity or for questions about it. Pages whose verdict shows no GenAI also take this value.  
  _confidence high; sources: CONTACT L42-43 (no = not present on the page); FO F07 a; FO W03 (other pages take no)_

## core.content_contact_details

- `yes` — The page gives contact details anywhere on it: an email address, phone number, postal address or contact form, including press or vendor contacts and site footers.  
  _confidence high; sources: CONTACT L31 contact_w4b_details; L42-43; CX CX-51 (w4); R1 X06 (header and footer text given for this item)_
- `no` — No contact details appear anywhere on the page, including its header and footer. Pages whose verdict shows no GenAI also take this value.  
  _confidence high; sources: CONTACT L42-43; R1 X06; FO F07 a; FO W03_

## core.activity_segment

- `same_activity` — The two passages describe the same activity: the same action by the same actor on the same tool or instrument.  
  _confidence medium; sources: CB shared_rules core.rule.activity_unit (SPEC R-017); SPEC R-017 list_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `component_of_program` — The first passage's activity is a named component of the program described in the second. Both stay separate activities, linked.  
  _confidence medium; sources: CB core.rule.activity_unit; R3 activity-16 b, activity-17 a_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `has_component` — The first passage describes a program, and the second passage's activity is one of its named components. Both stay separate activities, linked.  
  _confidence medium; sources: R3 activity-16 b (reverse value); CB core.rule.activity_unit_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `shared_participation` — The two passages describe one joint action in which several bodies take part.  
  _confidence low **[no_source]**; sources: SPEC R-017 list; V26 052fcb2:g3o/extract/prompts/system_prompt.md L44-46 ('For a shared action, list explicit participants')_  
  PI must decide: No text defines this link or says whether it merges the two passages. Please word it and say whether it merges.  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `governs` — The first passage's activity is a policy or other governance instrument that sets rules for the activity in the second (for example a policy and a tool it approves). When a pair fits both this link and a component link, this link is used.  
  _confidence medium; sources: CB core.rule.activity_unit ('linked by a "governs" relation'); R3 activity-17 a (governs wins)_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `governed_by` — The second passage's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.  
  _confidence medium; sources: R3 activity-16 b (reverse value); R3 activity-17 a_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `distinct_action` — The two passages describe different activities, and none of the other links applies.  
  _confidence medium; sources: SPEC R-017 list; V26 validate output_contract.md §9 (allowed relations)_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `unresolved` — The page does not settle whether the two passages describe the same activity or different ones. They are kept separate.  
  _confidence medium; sources: SPEC R-005 (unresolved relations never merge); V26 validate output_contract.md §8-9_  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.
- `not_an_activity` — The passage does not describe an activity as the activity rule defines one.  
  _confidence low **[no_source]**; sources: R1 C07 ('not an activity' answer per span); SPEC R-017 ('plus not-an-activity within a page')_  
  PI must decide: Links are now coded per pair of passages (activity-18 b), but this value describes one passage. Please say how it is used in a pair (for example: either passage is not an activity).  
  Note: Direction: the pair is read in order (first passage, second passage); the reverse values make that order necessary (R3 activity-16 b), but no text says which passage is 'first'.

## core.observed_actor_relationship

- `this_institution` (relationship) — The searched institution itself carries out or adopts the activity.  
  _confidence medium; sources: CB core.page_verdict confirms_activity ('carried out or adopted by the named institution itself'); R3 activity-14 b_
- `unit_of_institution` (relationship) — An organisational unit of the searched institution (a department, office or service) carries out the activity; it counts for the institution.  
  _confidence high; sources: CB shared_rules core.rule.attribution_grain (R1 C04); R3 activity-14 b_
- `joint_participant` (relationship) — The activity is a joint one, and the page names the searched institution as a participant.  
  _confidence high; sources: CB core.rule.attribution_grain (joint rule); R3 activity-14 b_
- `other` (relationship) — The activity belongs to another body: a parent, sibling or neighbouring body, a separate court, board or authority, a similarly named organisation, or a vendor. The searched institution's role is still asked.  
  _confidence medium; sources: CB core.page_verdict other_body; CB core.rule.attribution_grain; deltas/RC-D-003.md:262 (role asked when other)_
- `unresolved` (relationship) — The page does not settle whose activity this is. The role of the searched institution is not asked.  
  _confidence medium; sources: R3 activity-14 b; deltas/RC-D-003.md:262 (role skipped only when unresolved)_
- `contracting_authority` (searched_institution_role) — The searched institution buys or contracts for the tool or service in its own name.  
  _confidence medium; sources: R2 n=4; PROC L31-33 (role enum); planning/t010/codebook-review/review-cross-pipeline.json L81_  
  Note: The procurement schema gives the codes but no definition; this gloss is the ordinary procurement meaning.
- `beneficiary` (searched_institution_role) — Another body runs or buys the activity for the searched institution, and the page names the searched institution as benefiting.  
  _confidence high; sources: SPEC R-014 ('beneficiary' only when the page names it); R2 n=4, n=23_
- `central_purchasing_body` (searched_institution_role) — The searched institution buys or sets up a contract or framework on behalf of other bodies.  
  _confidence medium; sources: PROC L5 ('a central purchasing body buying on behalf of a department'), L33 (framework establishment); R2 n=4_
- `unit` (searched_institution_role) — The searched institution takes part as a unit of the body that carries out the activity.  
  _confidence low **[no_source]**; sources: R2 n=4 (role list includes 'unit'); R3 activity-14 b_  
  PI must decide: No text defines the roles 'unit' and 'joint'. They also repeat the relationship values 'unit of institution' and 'joint participant' (the overlap round 3 noted). Please say what each adds, or drop them.
- `joint` (searched_institution_role) — The searched institution takes part as one of several joint participants.  
  _confidence low **[no_source]**; sources: R2 n=4 (role list includes 'joint'); R3 activity-14 b_  
  PI must decide: See 'unit': undefined and overlaps the relationship value 'joint participant'.

## core.action_type

- `deployment` — The institution puts a GenAI tool to use, or tries one out, for its own work or for the public. The stage and the purchase status are coded separately.  
  _confidence medium; sources: R1 A02; R2 n=11 c (stage and procurement status carry proposals and purchases)_
- `governance` — The institution issues or applies a rule on GenAI use: a policy, guidance, approved-tool list, order or standard. A body that sets or oversees such rules also counts.  
  _confidence medium; sources: R1 A02, A03; R3 activity-04 d_
- `staff_training` — The institution trains its own staff to use GenAI.  
  _confidence high; sources: R1 A02; CB core.page_verdict confirms_activity ('institution-directed staff GenAI training')_
- `program` — A container activity whose named components are each their own activity, linked to it. Used only when the page names the components.  
  _confidence high; sources: R2 n=11 c ('a container used only with named components'); CB core.rule.activity_unit_
- `unknown` — The page mentions the activity but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 A02_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.procurement_status

- `none_documented` — The page documents the activity but no purchase step for it.  
  _confidence medium; sources: R1 C09_  
  Note: This value is close to the reserved label "not documented"; you may want to say how the two differ.
- `tender_or_rfp` — The institution has issued a call for tenders, a request for proposals or a similar invitation to bid for the tool or service.  
  _confidence medium; sources: R1 C09_
- `award_or_contract` — A contract, award or licence agreement for the tool or service is reported as made.  
  _confidence medium; sources: R1 C09_
- `payment_or_subscription` — The page records a payment, invoice or subscription for the tool or service. On its own this does not show use; the stage is then unknown unless use is shown.  
  _confidence high; sources: R1 C09; R2 n=14; V26 052fcb2:g3o/extract/prompts/system_prompt.md ('payment is procurement, not production')_
- `unknown` — The page mentions a purchase of the tool or service but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 C09_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.model_origin

- `commercial` — The model comes from a commercial provider (for example OpenAI, Microsoft, Google or Anthropic) and is used through its product, licence or programming interface.  
  _confidence medium; sources: R1 C10; V25 L182 proprietary_vendor_
- `open_weight` — The model's weights are openly released (for example Llama, Mistral or Falcon), whether the institution or a provider runs it.  
  _confidence medium; sources: R1 C10; V25 L183 open_source_
- `government_developed` — The model was developed by or for a government (for example France's Albert or Germany's OpenGPT-X), including by the institution's own team.  
  _confidence medium; sources: R1 C10; V25 L184 sovereign_model, L185 in_house_  
  Note: v2.5 kept 'in house' apart from 'sovereign'; this draft folds both into one value. You may want them kept apart.
- `unknown` — The page mentions the model behind the tool but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 C10_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.build_arrangement

- `off_the_shelf_product` — The institution uses a ready-made product as supplied (for example a commercial chat assistant or an office-suite assistant), set up but not built on.  
  _confidence medium; sources: R1 C10_
- `custom_application_on_external_model` — The institution, or a contractor for it, built its own application (a chatbot, assistant or workflow) on a model it did not train.  
  _confidence medium; sources: R1 C10_
- `model_trained_or_fine_tuned_by_institution` — The institution, or a contractor for it, trained or fine-tuned the model itself. Internal use alone does not show this.  
  _confidence medium; sources: R1 C10; V26 052fcb2:g3o/extract/prompts/system_prompt.md ('internal use does not prove in-house development')_
- `unknown` — The page mentions how the tool was built but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 C10_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.interface

- `conversational` — Users type or speak to the tool in a chat or question-and-answer exchange, as with a chatbot or assistant window.  
  _confidence medium; sources: R2 n=20 b; V25 L193 chatbot ('Conversational interface for Q&A, navigation, or retrieval')_
- `backend_or_api` — The tool runs behind the scenes, or other software calls it through a programming interface; users do not talk to it directly.  
  _confidence medium; sources: R2 n=20 b; R1 C11_
- `other_interface` — Users reach the tool in another way than a chat exchange or a back-end connection.  
  _confidence low; sources: R2 n=20 b ('other interface')_  
  Note: Kept minimal: the ruling names the value only. Integrated versus standalone is carried by deployment mode (R2 n=20 b), not here.

## core.function_drafting_writing

- `yes` — The page states that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for drafting or writing text, such as memos, letters, press releases or social media posts.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_summarization

- `yes` — The page states that the tool is used for summarising documents, reports or meetings.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for summarising documents, reports or meetings.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_translation

- `yes` — The page states that the tool is used for translating text or speech between languages.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for translating text or speech between languages.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_search_retrieval

- `yes` — The page states that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for finding information, such as answering questions from documents or searching the institution's own records.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_code

- `yes` — The page states that the tool is used for writing, reviewing or fixing software code.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for writing, reviewing or fixing software code.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_image_audio_video

- `yes` — The page states that the tool is used for creating or editing images, audio or video.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for creating or editing images, audio or video.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_extraction_classification

- `yes` — The page states that the tool is used for pulling information out of documents or forms, or sorting and classifying them.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for pulling information out of documents or forms, or sorting and classifying them.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.function_analysis_recommendation

- `yes` — The page states that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_
- `no` — The page does not state that the tool is used for analysing information or giving recommendations or scores to support human decisions, such as case triage or eligibility checks.  
  _confidence medium; sources: R1 C11 (function items, yes/no, any-yes across parts); V25 L193-202 §4.5 interaction_type definitions and examples_

## core.deployment_mode

- `unknown` — The page mentions whether the tool is separate or built into existing software but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 C14_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.target_users

- `internal_staff` — Only the institution's own staff use the tool.  
  _confidence medium; sources: R1 C15; V25 L104 ('Who interacts with the GenAI system')_
- `public` — People outside the institution use the tool: members of the public, residents or businesses.  
  _confidence medium; sources: R1 C15; V25 L104_
- `both` — Both the institution's staff and people outside it use the tool. On long pages, one part naming staff and another the public also gives this value.  
  _confidence high; sources: V25 L104; FO F03 a; R3 activity-22 b_
- `unknown` — The page mentions who uses the tool but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 C15_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.governed_population

- `internal_personnel` — The rule applies to the institution's own staff and officials.  
  _confidence medium; sources: R1 A04_
- `external_users` — The rule applies to people or bodies outside the institution, such as the public or the parties it regulates.  
  _confidence medium; sources: R1 A04_
- `both` — The rule applies both to the institution's own staff and to people or bodies outside it. On long pages, one part naming each also gives this value.  
  _confidence high; sources: R1 A04; FO F03 a; R3 activity-22 b_
- `unknown` — The page mentions whom the rule applies to but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 A04_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.governance_form

- `dedicated_genai_or_ai_policy_or_guideline` — A policy, guideline, code of practice or acceptable-use rule whose main subject is generative AI or AI.  
  _confidence medium; sources: R1 A03; CB core.activity_type policy_guidance (v2.5)_
- `approved_tool_list_or_endorsement` — A list of approved or permitted GenAI tools, or an official endorsement of a named tool.  
  _confidence medium; sources: R1 A03_
- `clause_in_instrument_on_other_subject` — A clause on GenAI inside a rule, policy or guidance whose main subject is something else (for example IT security or records management).  
  _confidence medium; sources: R1 A03_
- `court_or_regulatory_order` — An order, decision or practice direction on GenAI use issued by a court or a regulator.  
  _confidence medium; sources: R1 A03_
- `procurement_standard` — A standard or requirement for buying GenAI tools or services, such as purchasing criteria or contract terms.  
  _confidence medium; sources: R1 A03; CB core.activity_type policy_guidance ('procurement standards', v2.5)_
- `unknown` — The page mentions the form of the rule but does not let it be settled.  
  _confidence high; sources: R3 all-02 a (silent page = not documented; mentioned but unsettled = unknown); R1 A03_  
  Note: The code `unknown` is also a reserved missing-answer label; template check 8 says a value code never equals one. You may want this value dropped in favour of the reserved label.

## core.governance_direction

- `prohibits` — The rule bans the GenAI use it covers, with no use allowed.  
  _confidence medium; sources: R2 n=58; R3 activity-11 a (any mix of ban and permission is restricts with conditions)_
- `restricts_with_conditions` — The rule allows use only under conditions (for example approval, training, limits on data, or human review), or bans some uses and allows others. On long pages, a ban in one part and a permission in another also give this value.  
  _confidence high; sources: R2 n=58; R3 activity-11 a_
- `permits` — The rule allows the use without conditions.  
  _confidence high; sources: R3 activity-11 a ('Permits only when use is allowed without conditions')_
- `requires` — The rule makes GenAI use mandatory for some task or for some staff.  
  _confidence medium; sources: R3 activity-10 b (situation: 'a binding duty to use GenAI')_
- `promotes` — The rule encourages or supports GenAI use without making it mandatory.  
  _confidence medium; sources: R3 activity-10 b (situation: 'encouragement')_

## core.service_domain

- `general_public_services` — Running government itself: executive and legislative bodies, financial, fiscal and tax affairs, foreign affairs, and general administration and internal services. The earlier value 'general administration' is coded here.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 01; FO F09 a_  
  Note: Check every COFOG gloss against the official text before signing.
- `defence` — Military and civil defence.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 02_
- `public_order_safety` — Police, fire protection, the courts and prisons.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 03_
- `economic_affairs` — Economic, commercial and labour affairs; agriculture, forestry and fishing; fuel and energy; industry and construction; transport; communication.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 04_
- `environmental_protection` — Waste and waste-water management, pollution control, and the protection of biodiversity and landscape.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 05_
- `housing_community_amenities` — Housing and community development, water supply and street lighting.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 06_
- `health` — Medical products, outpatient and hospital services, and public health services.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 07_
- `recreation_culture_religion` — Recreation and sport, culture, broadcasting and publishing, and religious and other community services.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 08_
- `education` — Education at every level, from pre-primary to university, and services that support it.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 09_
- `social_protection` — Support in sickness and disability, old age, for survivors, families and children, in unemployment, for housing, and against social exclusion.  
  _confidence medium; sources: R3 activity-12 b; COFOG division 10_
- `other` — An area that fits none of the ten areas above.  
  _confidence high; sources: R3 activity-13 a ('Activities that fit no area get "other"')_  
  Note: The value has no label yet (fold-log round 3 §4 item 9).

## core.genai_mechanism_basis

- `named_genai_product_or_model` — The page names a generative product or model, such as ChatGPT, Copilot, Gemini, Claude or a named language model.  
  _confidence high; sources: R1 A01; CB core.page_verdict confirms_activity (named products)_
- `explicit_genai_label` — The page calls the tool generative AI, a large language model or the like, without naming a product.  
  _confidence medium; sources: R1 A01; CB core.page_verdict confirms_activity ('explicitly generative AI')_
- `generative_capability_described` — The page says the tool generates text, images, audio, code or other content, without naming a product or using a generative-AI label.  
  _confidence high; sources: R1 A01; CB core.page_verdict confirms_activity ('says the tool generates text, images, audio, code or other content')_
- `ai_chatbot_or_assistant_label_only` — The only signal is that the page calls the tool an 'AI chatbot' or 'AI assistant'; under the GenAI boundary rule this counts as generative.  
  _confidence high; sources: R1 A01, C02; CB shared_rules core.rule.genai_boundary (SPEC R-016)_  
  Note: No order is stated for an activity where several of these four fit.

## core.deployment_scale_unit

- `licences_or_seats` — The number counts licences, seats or accounts bought or issued.  
  _confidence medium; sources: R1 A09_
- `users` — The number counts people who use the tool.  
  _confidence medium; sources: R1 A09_
- `interactions` — The number counts uses of the tool, such as questions answered, conversations held or documents handled.  
  _confidence medium; sources: R1 A09; CX CX-40 example 4 ('the chatbot has answered 40,000 questions')_
- `units_or_departments` — The number counts offices, departments, schools or other units that use the tool.  
  _confidence medium; sources: R1 A09_
- `none` — A number is stated, but it counts none of these units.  
  _confidence medium; sources: R1 A09; CB core.deployment_scale_unit gate (asked when a number is stated)_

## core.evaluation_type_pre_deployment_testing

- `yes` — The page documents an evaluation of this type for the activity: testing before deployment.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (testing before deployment) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.evaluation_type_pilot_evaluation

- `yes` — The page documents an evaluation of this type for the activity: evaluation of a pilot or trial.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (evaluation of a pilot or trial) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.evaluation_type_independent_audit

- `yes` — The page documents an evaluation of this type for the activity: an audit or evaluation by an independent body.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (an audit or evaluation by an independent body) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.evaluation_type_ongoing_monitoring

- `yes` — The page documents an evaluation of this type for the activity: ongoing monitoring of the tool in use.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (ongoing monitoring of the tool in use) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.evaluation_type_user_feedback

- `yes` — The page documents an evaluation of this type for the activity: user feedback or satisfaction surveys.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (user feedback or satisfaction surveys) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.evaluation_type_bias_or_safety_testing

- `yes` — The page documents an evaluation of this type for the activity: bias, fairness or safety testing.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).
- `no` — The page does not document an evaluation of this type (bias, fairness or safety testing) for the activity.  
  _confidence high; sources: PILOT L165-172 EVAL_TYPES and L208-211 type_questions (yes = 'documented on the page', no = 'not documented'); CX CX-41; CB vocabularies.missing.cx_mapping_row (`no` of evaluation_type_* maps to not documented)_  
  Note: On the published side, `no` maps to the reserved label "not documented" (questionnaire map row).

## core.support_entailment

- `true` — The quoted text states that the field has the given value.  
  _confidence high; sources: R1 X35 (question 'Does this text state that <field> is <value>?')_
- `false` — The quoted text does not state that the field has the given value. The answer's support status becomes 'downgraded: quote does not state the value'.  
  _confidence high; sources: R1 X35; SPEC R-041 (spelling downgraded_quote_not_stating_value, all-11)_

## core.activity_relation_cross_page

- `same_activity` — The two activity records describe the same activity: the same action by the same actor on the same tool or instrument. Only records joined by this link are merged.  
  _confidence medium; sources: CB core.rule.activity_unit; SPEC R-005 / R1 X30 (merging needs explicit same-activity links)_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `component_of_program` — The first record's activity is a named component of the program in the second. Both stay separate activities, linked.  
  _confidence medium; sources: R3 activity-16 b, activity-17 a; CB core.rule.activity_unit_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `has_component` — The first record describes a program, and the second record's activity is one of its named components. Both stay separate activities, linked.  
  _confidence medium; sources: R3 activity-16 b; CB core.rule.activity_unit_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `shared_participation` — The two records describe one joint action in which several bodies take part.  
  _confidence low **[no_source]**; sources: SPEC R-017 list; V26 validate output_contract.md §9_  
  PI must decide: As within a page: no text defines this link or says whether it merges the two records.  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `governs` — The first record's activity is a policy or other governance instrument that sets rules for the activity in the second. When a pair fits both this link and a component link, this link is used.  
  _confidence medium; sources: CB core.rule.activity_unit; R3 activity-17 a_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `governed_by` — The second record's activity is a policy or other governance instrument that sets rules for the activity in the first. When a pair fits both this link and a component link, this link is used.  
  _confidence medium; sources: R3 activity-16 b, activity-17 a_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `distinct_action` — The two records describe different activities, and none of the other links applies. The value is stored with a rule note.  
  _confidence medium; sources: SPEC R-017 list; R3 institution-02 a ('Store the distinct value with a rule note')_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.
- `unresolved` — The sources do not settle whether the two records describe the same activity. They are never merged.  
  _confidence high; sources: SPEC R-005 ('distinct/unresolved relations never merge'); V26 validate output_contract.md §8-9_  
  Note: Direction: the pair is read in order (first record, second record); the reverse values make that order necessary (R3 activity-16 b), but no text says which record is 'first'.

## core.observed_actor_role

- `institutional_actor` — The actor seen on the page carries out or adopts the activity as an institution.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.
- `issuer` — The actor issued the policy, rule, guidance or document.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.
- `participant` — The actor takes part in an activity that someone else runs.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.
- `external_speaker` — The actor speaks or presents about GenAI, for example at an event, without carrying out the activity.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.
- `service_provider` — The actor supplies the tool or service, as a vendor, contractor or developer.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.
- `event_host` — The actor hosts or organises an event about GenAI.  
  _confidence medium **[no_source]**; sources: R3 activity-15 a (kept as before, internal); V26 052fcb2:g3o/common/evidence_review.py L44-46 (role codes)_  
  PI must decide: The earlier data gave only the code names, with no definitions; these glosses read the names. Please word or approve each.

## core.support_status_second_reason

- `downgraded_no_quote` — The answer also failed because it has no supporting quote.  
  _confidence medium **[no_source]**; sources: FO F10 a; SPEC R-041_  
  PI must decide: Under the approved order (quote check first, then the 0.8 bar), a missing quote is always the main reason, so this value seems never to occur as the second reason. Please confirm the value list or the order.
- `downgraded_low_confidence` — The answer also failed because the classifier's certainty was below the 0.8 bar.  
  _confidence high; sources: FO F10 a; SPEC R-041_
- `downgraded_quote_not_stating_value` — The answer also failed because its quote does not state the value.  
  _confidence medium **[no_source]**; sources: FO F10 a; SPEC R-041_  
  PI must decide: Same as 'no quote': the quote-meaning check is part of the quote check, which comes first, so this seems never to be the second reason. Please confirm.
