"""Draft the v2.5 <-> v2.7 translation table (T-010, PI ruling S1 b, 2026-10-30) and its review page.

Fills, as a DRAFT for the PI's review, the 33 open `translation_v25` leaves of the codebook (32 items).
Writes drafts/translation-r4.json and .md, and beside this script translation-review.json, .map.json
and the built .html (decision-page builder). Reads the codebook only to check the leaves; never writes it.
Run: python build_translation.py
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
T010 = HERE.parent.parent
DRAFTS = T010 / "drafts"
CODEBOOK = Path("C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml")
BUILDER = Path("C:/Users/spaci/repos/ai-os-private/personal/skills/_assets/decision-page/build_decision_page.py")
TODAY = "2026-10-30"
PREPARED_BY = {"harness": "Claude Code", "model": "claude-opus-5-5",
               "session": "translation-drafting subagent of integrator session 20261030-claude-v2-2b8200388885f8f9"}

# Source shorthands (kept out of the text the PI reads; they go to the JSON and the map file).
V25 = "v2.5 contract, G3O 375f1ff g3o/extract/prompts/output_contract.md"
CP = "G3O 375f1ff g3o/common/contract.py"
R1 = "codebook-review/codebook-rulings-round1.json"
R2 = "codebook-review/codebook-rulings-round2.json"
CB = "codebook.yaml (approved final draft, sha256 9ddf5a09)"


def cell(v27, v25, src, conf, no_source=False, note=""):
    return {"v27": v27, "v25": v25, "source": src, "confidence": conf, "no_source": no_source, "note": note}


def rev(v25, v27, src, conf, no_source=False, note=""):
    return {"v25": v25, "v27": v27, "source": src, "confidence": conf, "no_source": no_source, "note": note}


NA = None  # unmappable cell

ENTRIES = [
    {"item": "core.page_verdict", "name": "Page verdict", "column": "genai_evidence", "leaves": ["map", "unmappable"],
     "plain": "The old four-value evidence column becomes the nine-value page verdict.",
     "cells": [
         cell("confirms_activity", "confirms_activity", f"{V25} §4.7; SPEC R-015", "high"),
         cell("ambiguous_genai", "ambiguous", f"{V25} §4.7 'Source mentions AI but unclear whether generative AI'", "high"),
         cell("ambiguous_attribution", "ambiguous", f"{V25} §4.7 '...or mentions GenAI but unclear whether this institution is involved'; §4.2 country-wide rule", "high"),
         cell("background_only", "background_only", f"{V25} §4.7", "high"),
         cell("confirms_absence", "confirms_absence", "SPEC R-015 ('v2.5 confirms_absence')", "high"),
         cell("no_genai", "confirms_absence", f"{V25} §4.7 defines confirms_absence as 'The supplied page text contains no GenAI evidence relevant to this institution', the v2.7 no_genai meaning", "medium",
              note="Both v2.7 values collapse into the old absence code."),
         cell("other_body", NA, f"{V25} has no other-body value; {R1} C04 (attribution rule)", "medium", True,
              "Old rules sent such pages to 'ambiguous' or 'background only' depending on the reading; no fixed choice."),
         cell("event_only", NA, "codebook rule core.rule.ws10_event (event rule new in v2.7)", "medium", True,
              "Old rules could code an event page as an activity or as background; no fixed choice."),
         cell("not_assessable", NA, f"SPEC R-015 (set mechanically when a page was not reviewed); {CP} L169 (four values)", "high",
              note="The old version wrote no row for an unreviewed page."),
     ],
     "reverse": [
         rev("confirms_activity", "confirms_activity", f"{V25} §4.7", "medium", note="Old positives may include pages v2.7 codes as event only or other body."),
         rev("ambiguous", NA, f"{V25} §4.7", "high", note="Splits into the two v2.7 ambiguous values; the old row does not say which."),
         rev("background_only", "background_only", f"{V25} §4.7", "medium", note="May include pages v2.7 codes as other body."),
         rev("confirms_absence", NA, f"{V25} §4.7; SPEC R-015", "medium", note="The old meaning is v2.7 'no GenAI', but a page stating absence also took it."),
     ],
     "v27_new": ["other_body", "event_only", "not_assessable"],
     "notes": ["Old rows stay unconverted (SPEC R-015); the reverse column is for reading old rows only."]},

    {"item": "core.source_type", "name": "Source type", "column": "source_type", "leaves": ["map"],
     "plain": "Same codes and definitions; two old codes are now set automatically.",
     "cells": [cell(c, c, f"{V25} §4.6; codebook value texts copy it", "high") for c in
               ["news_major", "news_trade", "vendor", "academic", "policy_org", "social_media", "procurement_tender", "other"]],
     "reverse": [rev(c, c, f"{V25} §4.6", "high") for c in
                 ["news_major", "news_trade", "vendor", "academic", "policy_org", "social_media", "procurement_tender", "other"]] + [
         rev("official_gov", "official_gov (set from the domain field)", f"{CB} source_type rule 1 (r2#25)", "medium",
             note="Not a classifier value in v2.7; pages typed from the domain keep the code in the same column."),
         rev("archive", "archive (set from the address)", f"{CB} source_type rule 1 (r2#25)", "medium",
             note="Not a classifier value in v2.7; pages typed from the address keep the code in the same column."),
     ],
     "v27_new": [],
     "notes": ["'Other' no longer carries an explanation in the snippet, since snippets are now verbatim only."]},

    {"item": "core.source_title", "name": "Source title", "column": "source_title", "leaves": ["map"], "map_value": "identity",
     "plain": "Same text column; v2.7 takes the title from the page instead of the model.",
     "cells": [cell("(title text)", "(same text)", f"{V25} col 30; {CB} source_title rule", "medium",
                    note="Method change: model-written 'as it appears' in v2.5, page title or first heading in v2.7.")],
     "reverse": [rev("(title text)", "(same text)", f"{V25} col 30", "medium")], "v27_new": [], "notes": []},

    {"item": "core.source_language", "name": "Source language", "column": "source_language", "leaves": ["map"],
     "plain": "Two-letter language tags carry over; tags the old column could not hold do not.",
     "map_value": {"<two-letter tag>": "<same tag>"},
     "unmappable_value": ["<tag with a script subtag>", "<three-letter tag>", "mul"],
     "cells": [
         cell("<two-letter tag>", "<same tag>", f"{CP} L104 LANG_PATTERN '^[a-z]{{2}}$'; {CB} source_language rule", "high"),
         cell("<tag with a script subtag> (e.g. uz-latn)", NA, f"{CP} L104 vs L113 LANGS_PATTERN", "high",
              note="Not stripped to the base tag: the script was ruled a different search instrument (contract.py L110)."),
         cell("<three-letter tag>", NA, f"{CP} L104", "high"),
         cell("mul", NA, f"{CB} source_language rule ('mul' when no language exceeds a set share)", "high"),
     ],
     "reverse": [rev("<two-letter tag>", "<same tag>", f"{CP} L104", "high", note="Old tags were judged by the model; v2.7 uses a pinned language-ID library.")],
     "v27_new": ["script-subtag tags", "three-letter tags", "mul"], "notes": []},

    {"item": "core.source_snippet", "name": "Supporting snippet", "column": "source_snippet", "leaves": ["map"], "map_value": "identity",
     "plain": "Same text column; old snippets may be paraphrased or translated.",
     "cells": [cell("(verbatim supporting text)", "(same text)", f"{V25} col 37; {CB} source_snippet rules (verbatim only, r2#35)", "medium")],
     "reverse": [rev("(snippet text)", "(same text, labelled)", f"{V25} col 37", "medium",
                     note="Old snippets could be a close paraphrase or an English translation with the original in brackets; they are not all verbatim.")],
     "v27_new": [], "notes": []},

    {"item": "core.source_credibility", "name": "Source credibility", "column": "source_credibility", "leaves": ["map"],
     "plain": "Same three codes on the same ladder; v2.7 sets them by a fixed rule.",
     "cells": [cell(c, c, f"{V25} §4.8; {CB} source_credibility rule", "medium") for c in ["high", "medium", "low"]],
     "reverse": [rev(c, c, f"{V25} §4.8", "medium") for c in ["high", "medium", "low"]],
     "v27_new": [], "notes": ["v2.5: the model applied a hierarchy; v2.7: a fixed map from source type, plus 'low' when the publication date is unknown."]},

    {"item": "core.adoption_stage", "name": "Adoption stage", "column": "adoption_stage", "leaves": ["map"],
     "plain": "Same five stages, same definitions.",
     "cells": [cell(c, c, f"{V25} §4.3; codebook value texts copy it", "high") for c in
               ["proposed", "announced", "pilot", "production", "discontinued"]],
     "reverse": [rev(c, c, f"{V25} §4.3", "high") for c in ["proposed", "announced", "pilot", "production", "discontinued"]],
     "v27_new": [], "notes": ["Series break: a purchase record without shown use is 'unknown' in v2.7 (its purchase status says what was bought); v2.5 may have given it a stage."]},

    {"item": "core.model_origin", "name": "Model origin", "column": "access_type", "leaves": ["map"],
     "plain": "The old access-type column is split into model origin and build arrangement; the crosswalk is partial.",
     "map_value": {"commercial": "proprietary_vendor", "open_weight": "open_source"},
     "unmappable_value": ["government_developed"],
     "condition": "When build arrangement is model_trained_or_fine_tuned_by_institution, the old column is not filled (old rules would give mixed or in_house).",
     "cells": [
         cell("commercial", "proprietary_vendor", f"{V25} §4.4 (same examples: OpenAI, Microsoft, Google, Anthropic)", "high"),
         cell("open_weight", "open_source", f"{V25} §4.4 (same examples: Llama, Mistral, Falcon)", "high"),
         cell("government_developed", NA, f"{V25} §4.4 sovereign_model and in_house; {CB} government_developed definition", "medium", True,
              "The v2.7 value covers both old 'sovereign model' and old 'in house'."),
         cell("(any origin) with build arrangement = trained or fine-tuned by the institution", NA, f"{V25} §4.4 mixed example 'proprietary API fine-tuned in-house'", "medium", True,
              "The old column would say 'mixed' or 'in house', not the origin."),
     ],
     "reverse": [
         rev("proprietary_vendor", "commercial", f"{V25} §4.4", "high"),
         rev("open_source", "open_weight", f"{V25} §4.4", "high"),
         rev("sovereign_model", "government_developed", f"{V25} §4.4; {CB} (same examples: Albert, OpenGPT-X)", "high"),
         rev("in_house", "government_developed", f"{CB} government_developed ('including by the institution's own team')", "medium"),
         rev("mixed", NA, f"{V25} §4.4", "high"),
         rev("unknown", "unknown", f"{V25} §4.4", "high"),
     ],
     "v27_new": [], "notes": ["Round 1 recorded that this split breaks the series and the crosswalk is only partial."]},

    {"item": "core.build_arrangement", "name": "Build arrangement", "column": "access_type", "leaves": ["map"],
     "plain": "New dimension; nothing in v2.7 fills the old column from it.",
     "map_value": {}, "unmappable_value": ["off_the_shelf_product", "custom_application_on_external_model", "model_trained_or_fine_tuned_by_institution"],
     "cells": [cell(c, NA, f"{V25} §4.4 (no build dimension); {R1} C10", "high") for c in
               ["off_the_shelf_product", "custom_application_on_external_model", "model_trained_or_fine_tuned_by_institution"]],
     "reverse": [
         rev("in_house", "model_trained_or_fine_tuned_by_institution", f"{V25} §4.4 'Built by the institution's own team, not based on a major external foundation model'", "medium"),
         rev("mixed", NA, f"{V25} §4.4", "high"),
         rev("(other old codes)", NA, f"{V25} §4.4", "high", note="The old code says nothing about how the tool was built."),
     ],
     "v27_new": ["off_the_shelf_product", "custom_application_on_external_model", "model_trained_or_fine_tuned_by_institution"], "notes": []},

    {"item": "core.interface", "name": "Interface", "column": "interaction_type", "leaves": ["map"],
     "plain": "Ruled in round 2: the old interaction-type column has no fixed mapping and shows 'not asked' on v2.7 rows.",
     "map_value": {}, "unmappable_value": ["conversational", "backend_or_api", "other_interface"],
     "cells": [cell(c, NA, f"{R2} n=46 (R2P22); SPEC R-051", "high") for c in ["conversational", "backend_or_api", "other_interface"]],
     "reverse": [
         rev("chatbot", "conversational", f"{V25} §4.5 ('Conversational interface for Q&A, navigation, or retrieval')", "medium"),
         rev("not_applicable", "not_asked", f"{V25} §4.5 (policy activities with no tool); codebook applicability table (policy_guidance: not asked)", "medium"),
         rev("unknown", "unknown", f"{V25} §4.5", "high"),
         rev("(other old codes)", NA, f"{V25} §4.5", "high", note="They name a function, not how users reach the tool."),
     ],
     "v27_new": ["conversational", "backend_or_api", "other_interface"], "notes": []},
]

FUNCS = [
    ("core.function_drafting_writing", "Function: drafting and writing", None,
     "Old 'content creation' and 'document processing' each mix drafting with other functions."),
    ("core.function_summarization", "Function: summarising", None, "Old 'document processing' mixes summarising, extraction, classification and generation."),
    ("core.function_translation", "Function: translation", "translation", ""),
    ("core.function_search_retrieval", "Function: search and retrieval", "search_retrieval", ""),
    ("core.function_code", "Function: code", "code_generation", ""),
    ("core.function_image_audio_video", "Function: images, audio and video", None, "Old 'content creation' mixes text and multimedia."),
    ("core.function_extraction_classification", "Function: extraction and classification", None, "Old 'document processing' mixes several functions."),
    ("core.function_analysis_recommendation", "Function: analysis and recommendation", "decision_support", ""),
]
for iid, name, old, why in FUNCS:
    reverse = ([rev(old, "yes", f"{V25} §4.5 (same definition)", "high")] if old else
               [rev("(no single old code)", NA, f"{V25} §4.5", "medium", note=why)])
    reverse.append(rev("(any other old code)", NA, f"{V25} §4.5 ('Primary mode of human-AI interaction')", "high",
                       note="Never 'no': the old column recorded only the primary mode."))
    ENTRIES.append({
        "item": iid, "name": name, "column": "interaction_type", "leaves": ["map"],
        "plain": "The old single 'primary mode' column cannot be filled from a set of yes/no functions (round 2).",
        "map_value": {}, "unmappable_value": ["yes", "no"],
        "cells": [cell(c, NA, f"{R2} n=46 (R2P22); {R1} C11", "high") for c in ["yes", "no"]],
        "reverse": reverse, "v27_new": [], "notes": []})

ENTRIES += [
    {"item": "core.contracting_party", "name": "Contracting party", "column": "vendor", "leaves": ["map"],
     "plain": "Not used to fill the old vendor column.",
     "map_value": {}, "unmappable_value": ["(contracting party text)"],
     "cells": [cell("(contracting party text)", NA, f"{R1} C13 (old vendor = the supplier of the product); {CB} contracting_party rule 2 ('in purchase records is the contracting party')", "medium", True,
                    "The two rulings read the old vendor column differently; filling it from the contracting party could mix two meanings.")],
     "reverse": [rev("(vendor text)", NA, f"{V25} col 17", "medium", note="Old rows do not say whether the vendor was the contracting party.")],
     "v27_new": ["contracting party"], "notes": []},

    {"item": "core.developer", "name": "Developer", "column": "vendor", "leaves": ["map"],
     "plain": "The old vendor column takes the developer the page names; a developer found by lookup does not fill it.",
     "map_value": {"(developer text, basis stated)": "(same text)"}, "unmappable_value": ["(developer text, basis lookup)"],
     "cells": [
         cell("(developer text, basis stated)", "(same text)", f"{CB} developer rule 2 (= the round-1 vendor definition)", "medium"),
         cell("(developer text, basis lookup)", NA, f"{CB} contracting_party rule 2 ('the lookup stops filling vendor')", "high"),
     ],
     "reverse": [
         rev("(vendor text)", "(developer text, basis stated)", f"{V25} col 17 ('Vendor or provider. For in-house tools: the institution or its parent agency')", "medium"),
         rev("unknown", "unknown", f"{V25} col 17", "high"),
     ],
     "v27_new": ["developer found by lookup"], "notes": []},

    {"item": "core.deployment_mode", "name": "Deployment mode", "column": "deployment_mode", "leaves": ["map"],
     "plain": "Same two codes, same definitions.",
     "cells": [cell(c, c, f"{V25} col 18; {CB} deployment_mode instruction", "high") for c in ["integrated", "standalone"]],
     "reverse": [rev(c, c, f"{V25} col 18", "high") for c in ["integrated", "standalone", "unknown"]],
     "v27_new": [], "notes": []},

    {"item": "core.year_pilot_start", "name": "Year the pilot started", "column": "year_deployed", "leaves": ["map"],
     "plain": "Ruled in round 2: the old deployment year is the earlier of the pilot and production years.",
     "map_value": {"rule": "year_deployed = the earlier of year_pilot_start and year_production_start; if only one is a year, that year; if neither, unknown"},
     "cells": [
         cell("(year)", "earlier of the two years", f"{R2} n=46 (R2P22); SPEC R-051", "high"),
         cell("(only one of the two is a year)", "that year", f"{R2} n=46 (reading of 'the earlier of')", "medium"),
         cell("(neither is a year)", "unknown", f"{V25} col 21", "medium"),
     ],
     "reverse": [rev("(year)", NA, f"{R1} C17 (split)", "high", note="The old year does not say whether it was a pilot or a production start.")],
     "v27_new": [], "notes": ["For governance activities both years are 'not asked'; the old column then shows 'not asked' with a version label."]},

    {"item": "core.year_production_start", "name": "Year production started", "column": "year_deployed", "leaves": ["map"],
     "plain": "Same rule as the pilot year: the old deployment year is the earlier of the two.",
     "map_value": {"rule": "year_deployed = the earlier of year_pilot_start and year_production_start; if only one is a year, that year; if neither, unknown"},
     "cells": [cell("(year)", "earlier of the two years", f"{R2} n=46 (R2P22); SPEC R-051", "high")],
     "reverse": [rev("(year)", NA, f"{R1} C17 (split)", "high", note="The old year does not say whether it was a pilot or a production start.")],
     "v27_new": [], "notes": []},

    {"item": "core.outcome_kind", "name": "Kind of outcome reported", "column": "reported_outcomes", "leaves": ["map"],
     "plain": "'None reported' carries over; otherwise the old text column takes the quoted outcome text.",
     "map_value": {"none_reported": "none_reported"}, "via": {"quantified": "core.reported_outcomes", "qualitative": "core.reported_outcomes"},
     "cells": [
         cell("none_reported", "none_reported", f"{V25} col 26", "high"),
         cell("quantified", "(the quoted outcome text)", f"{V25} col 26 (a text column); {CB} reported_outcomes", "medium", note="The kind itself has no old code."),
         cell("qualitative", "(the quoted outcome text)", f"{V25} col 26; {CB} reported_outcomes", "medium", note="The kind itself has no old code."),
     ],
     "reverse": [
         rev("none_reported (and other 'nothing found' spellings)", "none_reported", f"{CB} reported_outcomes rule 1 (legacy normalisation)", "high"),
         rev("(outcome text)", NA, f"{V25} col 26", "high", note="Whether it was measured or described needs a reading of the text."),
     ],
     "v27_new": ["quantified", "qualitative"], "notes": []},

    {"item": "core.incident_kind", "name": "Kind of incident reported", "column": "reported_incidents", "leaves": ["map"],
     "plain": "As for outcomes; the new 'possibly discontinued' value goes to the old uncertainty flag, not to this column.",
     "map_value": {"none_reported": "none_reported"}, "via": {"quantified": "core.reported_incidents", "qualitative": "core.reported_incidents"},
     "unmappable_value": ["discontinuation_uncertain"],
     "cells": [
         cell("none_reported", "none_reported", f"{V25} col 27", "high"),
         cell("quantified", "(the quoted incident text)", f"{V25} col 27; {CB} reported_incidents", "medium"),
         cell("qualitative", "(the quoted incident text)", f"{V25} col 27; {CB} reported_incidents", "medium"),
         cell("discontinuation_uncertain", NA, f"{R2} n=38 (folded from the old flag); {CB} incident_kind rule 'ignores stops unless a problem is reported'", "medium", True,
              "Not written to the old incident column (neither 'none reported' nor text); it sets the old flag 'discontinued uncertain' instead."),
     ],
     "reverse": [
         rev("none_reported (and other 'nothing found' spellings)", "none_reported", f"{CB} reported_incidents rule 1", "high"),
         rev("(incident text)", NA, f"{V25} col 27", "high", note="Whether it was measured or described needs a reading."),
     ],
     "v27_new": ["quantified", "qualitative", "discontinuation_uncertain"], "notes": []},

    {"item": "core.reported_outcomes", "name": "Reported outcomes (quoted text)", "column": "reported_outcomes", "leaves": ["map"],
     "plain": "The quoted outcome passages fill the old text column, joined, in full.",
     "map_value": {"rule": "the verbatim spans joined with ' | ', in full; 'none_reported' when the outcome kind is none_reported"},
     "cells": [
         cell("(verbatim spans)", "(spans joined with ' | ', in full)", f"{V25} col 26; SPEC R-043 (full text in the API)", "medium", True,
              "The separator and dropping the old 200-character limit are choices; the alternative is to cut at 200 characters as before."),
     ],
     "reverse": [rev("(outcome text)", "(one span)", f"{V25} col 26", "medium", note="Old text was not required to be verbatim.")],
     "v27_new": [], "notes": []},

    {"item": "core.reported_incidents", "name": "Reported incidents (quoted text)", "column": "reported_incidents", "leaves": ["map"],
     "plain": "The quoted incident passages fill the old text column, joined, in full.",
     "map_value": {"rule": "the verbatim spans joined with ' | ', in full; 'none_reported' when the incident kind is none_reported"},
     "cells": [
         cell("(verbatim spans)", "(spans joined with ' | ', in full)", f"{V25} col 27; SPEC R-043", "medium", True,
              "As for outcomes: separator and length are choices."),
     ],
     "reverse": [rev("(incident text)", "(one span)", f"{V25} col 27", "medium", note="Old text was not required to be verbatim.")],
     "v27_new": [], "notes": []},

    {"item": "core.uncertainty_flags", "name": "Uncertainty flags", "column": "uncertainty_flags", "leaves": ["map"],
     "plain": "Two kept flags carry over; retired flags are not recomputed for the old column.",
     "map_value": {"stage_ambiguous": "stage_ambiguous", "incident_kind = discontinuation_uncertain": "discontinued_uncertain"},
     "unmappable_value": ["identity_unresolved"],
     "cells": [
         cell("stage_ambiguous", "stage_ambiguous", f"{R2} n=38 (kept)", "high"),
         cell("(incident kind = possibly discontinued)", "discontinued_uncertain", f"{R2} n=38 (folded into the incident question); respelling all-11", "high"),
         cell("identity_unresolved", NA, f"{R2} n=38; {R1} X24 (new, for consolidation links)", "high"),
         cell("(retired old flags)", NA, f"{R2} n=38 (retire flags that mirror a column); {R1} X24 ('compute each flag from codes')", "medium", True,
              "Round 1 said flags are computed from codes, round 2 retired the ones that mirror a column. Default: not recomputed; the mirrored columns carry the information."),
     ],
     "reverse": [
         rev("stage_ambiguous", "stage_ambiguous", f"{R2} n=38", "high"),
         rev("discontinued_uncertain", "incident kind: discontinuation_uncertain", f"{R2} n=38", "high"),
         rev("genai_vs_traditional_ai", "(reads as page verdict: ambiguous_genai)", f"{V25} §4.10; {R2} n=38", "medium"),
         rev("institution_attribution", "(reads as page verdict: ambiguous_attribution)", f"{V25} §4.10; {R2} n=38", "medium"),
         rev("date_uncertain", "(reads as year: unknown)", f"{V25} §4.10; {R2} n=38", "medium"),
         rev("vendor_undisclosed", "(reads as developer: not documented)", f"{V25} §4.10; {R2} n=38", "medium"),
         rev("scope_unclear", "(reads as target users: unknown)", f"{V25} §4.10; {R2} n=38", "medium"),
         rev("source_language_barrier", NA, f"{R2} n=39 (dropped everywhere)", "high"),
     ],
     "v27_new": ["identity_unresolved"], "notes": []},

    {"item": "core.has_genai_activity", "name": "Institution has GenAI activity", "column": "has_genai_activity", "leaves": ["map"],
     "plain": "Same three codes; v2.7's 'no' is stricter, and old 'no' results are labelled as produced by the old rule.",
     "cells": [cell(c, c, f"{V25} §4.1; {CB} has_genai_activity rules", "high") for c in ["yes", "no", "unclear"]],
     "reverse": [rev("yes", "yes", f"{V25} §4.1", "high"), rev("unclear", "unclear", f"{V25} §4.1", "high"),
                 rev("no", "no (labelled: produced by the v2.5 rule)", f"{R2} n=45 (R2P21); SPEC R-059 (verdict_rule)", "high")],
     "v27_new": [], "notes": []},

    {"item": "core.confidence", "name": "Confidence", "column": "confidence", "leaves": ["map"],
     "plain": "Same three codes, but a different rule and level; not carried over by default.",
     "map_value": {}, "unmappable_value": ["high", "medium", "low"],
     "cells": [cell(c, NA, f"{V25} §4.9 (model's confidence in the row's coded values); {CB} confidence rule (per source from credibility and quote support; per activity by consolidation)", "medium", True,
                    "The codes match but the measure changed; the alternative is to carry the codes with a version label.") for c in ["high", "medium", "low"]],
     "reverse": [rev(c, NA, f"{V25} §4.9", "medium", True, "Different measure.") for c in ["high", "medium", "low"]],
     "v27_new": [], "notes": []},

    {"item": "core.institution_summary", "name": "Institution summary", "column": "institution_summary", "leaves": ["map"], "map_value": "identity",
     "plain": "Same text column; v2.7 writes it from the codes instead of the model.",
     "cells": [cell("(summary text)", "(same text)", f"{V25} col 9; {CB} institution_summary rule", "medium")],
     "reverse": [rev("(summary text)", "(same text, labelled)", f"{V25} col 9", "medium")], "v27_new": [], "notes": []},

    {"item": "core.codebook_release", "name": "Codebook release", "column": "contract_version", "leaves": ["map"],
     "plain": "The old version column holds the codebook release label on v2.7 rows; old rows keep theirs.",
     "map_value": {"(codebook release label)": "(same label in contract_version)"},
     "cells": [cell("(codebook release label, e.g. 2.7)", "(same label)", "SPEC R-050 (the codebook release replaces contract_version)", "high")],
     "reverse": [rev("(old contract version, e.g. v2.5)", "(kept as is)", "SPEC R-050 ('v2.5 rows keep their contract version')", "high")],
     "v27_new": [], "notes": []},
]

MISSING = {
    "id": "missing-labels", "name": "Missing labels (every coded item above)",
    "plain": "How v2.7's reserved missing labels appear in the old columns.",
    "cells": [
        cell("_NA_", "_NA_", f"{V25} §3.2 Group D rule", "high"),
        cell("unknown", "unknown", f"{V25} §6 check 2", "high"),
        cell("not_documented", "unknown", f"{V25} §4.3-4.5 ('unknown: cannot determine'); §6 check 2", "medium", True,
             "The old columns had no 'not documented' (except the safeguard items), so 'unknown' covered silent pages too. Alternative: leave it unmapped."),
        cell("not_asked", "not asked (shown with a version label)", f"SPEC R-051; {R2} n=46", "high"),
    ],
}


def default_value(e):
    """The fold-ready value for the codebook's translation_v25 leaves."""
    if "map_value" in e:
        m = e["map_value"]
    else:
        m = {c["v27"]: c["v25"] for c in e["cells"] if c["v25"] is not None}
    out = {"map": m}
    if "unmappable" in e["leaves"] or "unmappable_value" in e:
        out["unmappable"] = e.get("unmappable_value", [c["v27"] for c in e["cells"] if c["v25"] is None])
    for k in ("condition", "via"):
        if k in e:
            out[k] = e[k]
    return out


def check_leaves():
    cb = yaml.safe_load(CODEBOOK.read_text(encoding="utf-8"))
    open_leaves = {(iid, k) for iid, it in cb["items"].items() if isinstance(it.get("translation_v25"), dict)
                   for k, v in it["translation_v25"].items() if v == "open"}
    mine = {(e["item"], k) for e in ENTRIES for k in e["leaves"]}
    assert mine == open_leaves, (sorted(open_leaves - mine), sorted(mine - open_leaves))
    for e in ENTRIES:
        assert cb["items"][e["item"]]["translation_v25"]["column"] == e["column"], e["item"]
    return len(open_leaves)


def fmt(v):
    return "not mappable" if v is None else f"`{v}`" if not v.startswith("(") and not v.startswith("<") else v


def card_body(e):
    lines = ["**Old column:** `" + e["column"] + "`", "", "**New → old** (fills the old column on new rows):"]
    for c in e["cells"]:
        flag = " · **Needs your decision**" if c["no_source"] else ""
        note = f" — {c['note']}" if c["note"] else ""
        lines.append(f"- {fmt(c['v27'])} → {fmt(c['v25'])} ({c['confidence']} certainty){flag}{note}")
    if e.get("reverse"):
        lines += ["", "**Old → new** (for reading old rows):"]
        for r in e["reverse"]:
            flag = " · **Needs your decision**" if r["no_source"] else ""
            note = f" — {r['note']}" if r["note"] else ""
            lines.append(f"- {fmt(r['v25'])} → {fmt(r['v27'])} ({r['confidence']} certainty){flag}{note}")
    if e.get("condition"):
        lines += ["", "**Condition:** " + e["condition"]]
    if e.get("v27_new"):
        lines += ["", "**New in v2.7, no old counterpart:** " + ", ".join(f"`{x}`" if not x.startswith(("script", "three", "contracting", "developer")) else x for x in e["v27_new"])]
    for n in e.get("notes", []):
        lines += ["", n]
    return "\n".join(lines)


def main():
    n_leaves = check_leaves()
    entries_out = []
    for e in ENTRIES:
        entries_out.append({k: e[k] for k in ("item", "name", "column", "leaves", "plain", "cells", "reverse", "v27_new", "notes")}
                           | {"default_value": default_value(e)}
                           | ({"condition": e["condition"]} if "condition" in e else {}))
    no_src = [(e["item"], c["v27"]) for e in ENTRIES for c in e["cells"] if c["no_source"]] + \
             [(e["item"], "reverse " + r["v25"]) for e in ENTRIES for r in e["reverse"] if r["no_source"]] + \
             [("missing-labels", c["v27"]) for c in MISSING["cells"] if c["no_source"]]
    leaf_items = {e["item"] for e in ENTRIES if any(c["no_source"] for c in e["cells"])}
    mapped = sum(1 for e in ENTRIES for c in e["cells"] if c["v25"] is not None)
    unmapped = sum(1 for e in ENTRIES for c in e["cells"] if c["v25"] is None)
    doc = {
        "format": "t010-translation-draft-v1", "status": "DRAFT, for PI review (not folded)", "date": TODAY,
        "draft_by": PREPARED_BY, "ruling": "PI 2026-10-30 's1 b s2b; accept all' (S1 b: agent drafts the translation table, PI reviews, then signs)",
        "codebook": {"path": str(CODEBOOK), "sha256_read": "9ddf5a093ab836ee79d95ab04f70602ce1361b2db07512e14d9014f4b9d2cd8e"},
        "template_shape": "item-template.md field 25: {column, map: {v2.7 code: v2.5 code}, unmappable: [...]}",
        "fold_note": "On approval, each entry's default_value fills that item's open translation_v25 leaves (map, and unmappable where listed), origin 'agent draft r4 translation' plus the PI approval. The missing-labels convention applies to every coded item and is recorded once, as a shared convention.",
        "counts": {"open_leaves": n_leaves, "items": len(ENTRIES), "cells_mapped": mapped, "cells_unmappable": unmapped,
                   "no_source_cells": len(no_src), "items_with_no_source_cells": len(leaf_items)},
        "missing_labels_convention": MISSING, "entries": entries_out, "no_source": no_src,
    }
    (DRAFTS / "translation-r4.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    md = ["# T-010 translation table v2.5 ↔ v2.7 (DRAFT, round 4)", "",
          f"Drafted {TODAY} by the translation subagent (Claude Code, claude-opus-5-5) for integrator session 20261030-claude-v2-2b8200388885f8f9, PI ruling S1 b. Not folded; for PI review. Codebook read at sha256 `9ddf5a09…2cd8e`.", "",
          f"{n_leaves} open leaves on {len(ENTRIES)} items. Cells: {mapped} mapped, {unmapped} not mappable; {len(no_src)} rest on no ruling (marked **no source**).", "",
          "## Missing labels (every coded item)", ""]
    for c in MISSING["cells"]:
        md.append(f"- `{c['v27']}` → {fmt(c['v25'])} — {c['confidence']}{' · **no source**' if c['no_source'] else ''}; {c['source']}{'; ' + c['note'] if c['note'] else ''}")
    for e in ENTRIES:
        md += ["", f"## {e['name']} (`{e['item']}` ← v2.5 `{e['column']}`; leaves: {', '.join(e['leaves'])})", "", e["plain"], "",
               "Default value: `" + json.dumps(default_value(e), ensure_ascii=False) + "`", "", "New → old:"]
        for c in e["cells"]:
            md.append(f"- {fmt(c['v27'])} → {fmt(c['v25'])} — {c['confidence']}{' · **no source**' if c['no_source'] else ''}; {c['source']}{'; ' + c['note'] if c['note'] else ''}")
        md += ["", "Old → new:"]
        for r in e["reverse"]:
            md.append(f"- {fmt(r['v25'])} → {fmt(r['v27'])} — {r['confidence']}{' · **no source**' if r['no_source'] else ''}; {r['source']}{'; ' + r['note'] if r['note'] else ''}")
        if e.get("condition"):
            md += ["", "Condition: " + e["condition"]]
        if e["v27_new"]:
            md += ["", "New in v2.7, no old counterpart: " + ", ".join(e["v27_new"])]
        for n in e["notes"]:
            md += ["", n]
    (DRAFTS / "translation-r4.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    items = [{"id": "ALL", "kind": "review", "title": "Batch approval for the whole table",
              "situation": f"This page shows the old-to-new translation for {len(ENTRIES)} codebook items, plus the missing-label rule. Choose the batch option to approve everything you do not mark in a card below; any card you answer overrides it for that item.",
              "options": [{"id": "approve-unmarked", "label": "Approve everything on this page that I do not mark below"},
                          {"id": "no-batch", "label": "No batch approval: only my card answers count"}]}]
    smap = {"ALL": {"owner": "all"}}
    opts = [{"id": "approve-all", "label": "Approve this translation as shown"},
            {"id": "approve-edits", "label": "Approve, except the changes in my comments"},
            {"id": "redraft", "label": "Redraft from my comments and show me again"}]
    prompt = 'Name the line and the change, e.g. "event only → background only" or "keep codes with a label"'
    m_body = "\n".join(f"- {fmt(c['v27'])} → {fmt(c['v25'])} ({c['confidence']} certainty)"
                       f"{' · **Needs your decision**' if c['no_source'] else ''}{' — ' + c['note'] if c['note'] else ''}" for c in MISSING["cells"])
    items.append({"id": "M1", "kind": "review", "title": MISSING["name"], "situation": MISSING["plain"],
                  "body_label": "Show the rule", "body": m_body, "options": opts, "prompt": prompt})
    smap["M1"] = {"owner": "missing-labels", "sources": [c["source"] for c in MISSING["cells"]]}
    for i, e in enumerate(ENTRIES, 1):
        cid = f"T{i:02d}"
        decide = sum(c["no_source"] for c in e["cells"]) + sum(r["no_source"] for r in e["reverse"])
        sit = e["plain"] + (f"\n\n**{decide} line(s) need your decision.**" if decide else "")
        items.append({"id": cid, "kind": "review", "title": e["name"], "situation": sit, "body_label": "Show the translation",
                      "body": card_body(e), "options": opts, "prompt": prompt})
        smap[cid] = {"owner": e["item"], "column": e["column"], "leaves": e["leaves"], "default_value": default_value(e),
                     "sources": [c["source"] for c in e["cells"]] + [r["source"] for r in e["reverse"]]}
    bg = ("You chose on 30 October that an agent drafts the table that translates between the current production version (2.5) "
          "and the new version (2.7), and that you review it before signing.\n\n"
          "Each card is one codebook item. **New → old** says how the old column is filled on new rows; **Old → new** says how an old row reads in the new terms. "
          "Where a translation would be a guess, the draft says *not mappable* rather than force one. "
          f"Lines marked **Needs your decision** rest on no ruling or text ({len(no_src)} in all); each says what the alternative is.\n\n"
          "No recommendation is given on the substance. The batch card at the top approves everything you leave unmarked.")
    data = {"format": "decision-page-v1", "id": "t010-translation-review", "title": "Codebook translation table: version 2.5 to 2.7",
            "eyebrow": "G3O codebook · translation review", "project": "G3O pipeline reclassification", "prepared": TODAY,
            "prepared_by": PREPARED_BY, "background": bg,
            "sources": [{"label": "Translation draft (readable)", "href": "../../drafts/translation-r4.md"},
                        {"label": "Final-draft codebook", "href": "../final-draft/codebook-final-draft.html"}],
            "items": items, "slot_map": smap}
    jp = HERE / "translation-review.json"
    jp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (HERE / "translation-review.map.json").write_text(json.dumps(smap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    r = subprocess.run([sys.executable, str(BUILDER), str(jp)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"builder failed\n{r.stdout}\n{r.stderr}")
    html_text = (HERE / "translation-review.html").read_text(encoding="utf-8")
    sha = json.loads(html_text.split('<script id="page-data" type="application/json">', 1)[1].split("</script>", 1)[0])["_sha256"]
    print(json.dumps({"counts": doc["counts"], "no_source": no_src, "link": r.stdout.strip(), "page_sha256": sha}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
