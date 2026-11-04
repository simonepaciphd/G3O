"""Build tests/fixtures/v27/real.json and transfers.json: T-040 real-page fixtures (RC-D-014 P4).

Run: python -I -X utf8 tests/fixtures/v27/build_real.py
Free and offline. Reads only stored scrapes already on Drive (no SSH, no fetch):
  SP  agent-workspace/2026-11-02-safe-review/t003-recovery/SOURCE-PAGES.jsonl (50 pages from RS-008/RS-009)
  TAR agent-workspace/2026-09-27-jev-compare/pulled/stored-subset.tar (RS-009), via the lane-D extract
      agent-workspace/2026-11-04-v27-orch/lane-d/candidates.jsonl (member + hashes)
  WS10 agent-workspace/2026-09-05-combined-ws10-review/activity-review-prepared.csv (RS-026, the 114)
No page text is written to git: each fixture pins its page by store, line or member, and sha256.

Labeller: agent (Lane D, session 20261104-claude-v2-87b58de9a1ec1fe0, claude-opus-5-5), 2026-11-04.
Every label cites the signed codebook 2.7 (sha256 f948fe0b...181e0d) or a SPEC row. Judgement calls are
flagged (judgement-calls.csv) and are NOT resolved here; jev scores are filled later (paid, Simone-run).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

DRIVE = Path("H:/My Drive/Research/G3O")
SP = "agent-workspace/2026-11-02-safe-review/t003-recovery/SOURCE-PAGES.jsonl"
TAR = "agent-workspace/2026-09-27-jev-compare/pulled/stored-subset.tar"
CAND = DRIVE / "agent-workspace/2026-11-04-v27-orch/lane-d/candidates.jsonl"
WS10 = "agent-workspace/2026-09-05-combined-ws10-review/activity-review-prepared.csv"
HERE = Path(__file__).resolve().parent
CB = "codebook 2.7"
PV = f"{CB} core.page_verdict"
LABELLER = {"labeller": "agent", "label_session": "20261104-claude-v2-87b58de9a1ec1fe0", "label_model": "claude-opus-5-5",
            "label_date": "2026-11-04", "jev_score": None}


def sp_ref(n):
    lines = (DRIVE / SP).read_text(encoding="utf-8").split("\n")
    r = json.loads(lines[n])
    return ({"store": SP, "line_1based": n + 1, "page_id": r["page_id"], "url": r["source_record"]["url"],
             "text_sha256": r["text_sha256"]},
            {"institution_id": r["page_id"].split(":")[2], "country": r["country"], "script": r["script"]})


_cand = None


def tar_ref(url_part, iid):
    global _cand
    if _cand is None:
        _cand = [json.loads(l) for l in CAND.read_text(encoding="utf-8").split("\n") if l.strip()]
    hits = [c for c in _cand if url_part in c["url"] and c["institution_id"] == iid]
    c = sorted(hits, key=lambda h: len(h["url"]))[0]
    return ({"store": TAR, "member": c["member"], "member_sha256": c["member_sha256"], "url": c["url"],
             "text_sha256": c["text_sha256"]},
            {"institution_id": iid, "name": c["institution_meta"].get("institution_name"),
             "country": c["institution_meta"].get("country")})


def e(item, value, rule, quote=None, scope="page", jc=None):
    d = {"item": item, "scope": scope, "value": value, "rule": rule, "evidence_quote": quote, **LABELLER}
    if jc:
        d["judgement_call"] = jc
    return d


F = []


def add(fid, a_ids, ref_inst, name, expected, note=""):
    ref, ins = ref_inst
    ins = {**ins, "name": ins.get("name") or name}
    F.append({"fixture_id": fid, "kind": "real", "a_ids": a_ids, "institution": ins, "page_ref": ref,
              "expected": expected, "note": note})


# ------------------------------------------------------------------ SOURCE-PAGES (n = 0-based line)
add("v27-real-01", ["A-011", "A-003", "A-020"], sp_ref(13), "Fairfield School District", [
    e("core.page_verdict", "confirms_activity", f"{PV} confirms_activity: the institution's own policy/guidance on GenAI, explicitly generative",
      "This policy establishes guidelines for the use of Generative Artificial Intelligence", jc="JC-R1"),
    e("core.governance_direction", "restricts_with_conditions", f"{CB} core.governance_direction; SPEC R-044 (a condition ranks first)",
      "Submitting AI generated content without teacher permission and proper citation", scope="activity:Use of Artificial Intelligence policy 6141.3273"),
    e("core.evaluation_documented", "not_documented", f"{CB} core.evaluation_documented rule (r11 C3): review/monitoring of the policy itself is not_documented unless it requires testing of GenAI tools",
      "Monitor implementation and", scope="activity:Use of Artificial Intelligence policy 6141.3273", jc="JC-R2"),
    e("n_activities", 1, "SPEC R-017 activity unit: the policy and its attached AI Guidelines read as one governance instrument", scope="page", jc="JC-R3"),
], "Board policy-committee packet, draft AI policy plus guidelines (Adopted: X/X/2025).")
add("v27-real-02", ["A-011", "A-012"], sp_ref(3), "Ministry Of Foreign Affairs & Foreign Trade", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai: AI at this institution, not settled whether generative",
      "The Ministry of Foreign Affairs continues to embrace technology, including the integration of AI at our consulates")])
add("v27-real-03", ["A-012"], sp_ref(22), "COUNTY OF CALHOUN", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai (generic AI policy, generative not stated); SPEC R-016",
      "436 Artificial Intelligence (AI) Workplace Use", jc="JC-R4")])
add("v27-real-04", ["A-011"], sp_ref(43), "Ministry Of Industry", [
    e("core.page_verdict", "background_only", f"{PV} background_only: news about AI in general (another country's AI law), no activity at this institution",
      "สภาผู้แทนราษฎรของญี่ปุ่นได้ผ่านร่างกฎหมายควบคุมปัญญาประดิษฐ์ (AI) ฉบับแรกของประเทศ")])
add("v27-real-05", ["A-011"], sp_ref(34), "Hebei", [
    e("core.page_verdict", "background_only", f"{PV} background_only: national AI strategy speech reposted, no activity at this institution",
      "习近平在2026世界人工智能大会暨人工智能全球治理高级别会议开幕式上的主旨讲话")])
add("v27-real-06", ["A-011"], sp_ref(10), "Croft", [
    e("core.page_verdict", "no_genai", f"{PV} no_genai: no GenAI content", "Welcome to Croft Parish Council")])
add("v27-real-07", ["A-011", "A-012"], sp_ref(6), "Makari", [
    e("core.page_verdict", "no_genai", f"{PV} no_genai: 'AIG' (police rank) is not AI content; keyword trap",
      "the Minister of Internal Affairs Rtd AIG Morie Lengor Esq")])
add("v27-real-08", ["A-012"], sp_ref(24), "COUNTY OF GREENE", [
    e("core.page_verdict", "no_genai", f"{PV} no_genai: vendor name 'Placer.ai' (visitor data) is not stated to be AI; keyword trap",
      "renew Placer.ai for one- year including the STI Demographics Bundle", jc="JC-R5")])
add("v27-real-09", ["A-012"], sp_ref(44), "阿勒泰市", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai: AI classroom analytics (recording, behaviour capture, scoring); confirms_activity excludes analytics/recognition unless the tool generates content",
      "平台自动生成课堂分析报告", jc="JC-R6")])
add("v27-real-10", ["A-012"], sp_ref(46), "Gand", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai (definition example: traditional machine learning / NLP at this institution)",
      "Using artificial intelligence, such as natural language processing (NLP) , we link decisions to keywords and locations")])
add("v27-real-11", ["A-012", "A-011"], sp_ref(2), "Cork", [
    e("core.page_verdict", "event_only", f"{PV} event_only: the only AI content is a public business event run by the council's Local Enterprise Offices",
      "“Understand How AI Can Transform Your Business”", jc="JC-R8")])
add("v27-real-12", ["A-011"], sp_ref(1), "Alberta", [
    e("core.page_verdict", "background_only", f"{PV} background_only: general explainer on GenAI at work, no activity at this institution",
      "Generative AI is a new form of AI that can create content", jc="JC-R9")])
add("v27-real-13", ["A-012"], sp_ref(4), "Ministry Of Education", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai (traditional ML / expert systems in the institution's curriculum)",
      "Deep learning and Machine learning in imaging", jc="JC-R10")])
add("v27-real-14", ["A-011"], sp_ref(49), "大館市", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai: AI in a city-coordinated startup project, generative not stated",
      "オンライン・AIを活用した新たなフレイル予防")])
add("v27-real-15", ["A-011"], sp_ref(42), "Ministry Of Agriculture & Cooperatives", [
    e("core.page_verdict", "ambiguous_genai", f"{PV} ambiguous_genai: ministry policy to bring in AI, generative not stated",
      "การนำปัญญาประดิษฐ์ (AI) และเทคโนโลยีการเกษตรแม่นยำมาใช้")])

# ------------------------------------------------------------------ RS-009 stored-subset.tar
WOK = "INST-0651125"
add("v27-real-20", ["A-011", "A-003", "A-020"], tar_ref("wokingham.gov.uk/foi/use-ai", WOK), "Wokingham", [
    e("core.page_verdict", "confirms_activity", f"{PV} confirms_activity (order rule: first fitting value; absence statements on the same page do not override)",
      "Staff may use approved Generative AI tools internally under policy governance."),
    e("n_activities", 3, "SPEC R-017: AI policy; Minute pilot; Q Assistant pilot (policy and the tools it governs are separate)", jc="JC-R11"),
    e("core.has_human_oversight", "yes", f"{CB} core.has_human_oversight (safeguard, r2#10)", "All AI use requires full human oversight.",
      scope="activity:APPROVED AI Policy WBC v3.1"),
])
add("v27-real-21", ["A-011"], tar_ref("wokingham.gov.uk/foi/use-ai-recording-tools", WOK), "Wokingham", [
    e("core.page_verdict", "confirms_absence", f"{PV} confirms_absence: page states this institution does not use the AI tools asked about",
      "No, we do not use AI powered recording, transcription or note taking in Social Services", jc="JC-R12")])
add("v27-real-22", ["A-011"], tar_ref("wokingham.gov.uk/foi/ai-recruitment", WOK), "Wokingham", [
    e("core.page_verdict", "confirms_absence", f"{PV} confirms_absence: page states no AI use in recruitment",
      "The council does not use any form of AI in any of the above instances", jc="JC-R12")])
add("v27-real-23", ["A-011", "A-012", "A-020"], tar_ref("eastmoline.com", "INST-0668835"), "CITY OF EAST MOLINE", [
    e("core.page_verdict", "confirms_activity", f"{PV} confirms_activity: the institution's own notice governing its GenAI use, named products",
      "Microsoft Copilot – drafting, summarization, analysis, or productivity assistance within", jc="JC-R13"),
    e("core.genai_mechanism_basis", "named_genai_product_or_model", f"{CB} core.genai_mechanism_basis", "ChatGPT or similar generative AI tools",
      scope="activity:Notice of Use of AI in Employment Decisions"),
    e("core.has_human_oversight", "yes", f"{CB} core.has_human_oversight", "Final employment decisions are made by human decision-makers.",
      scope="activity:Notice of Use of AI in Employment Decisions", jc="JC-R13"),
])
add("v27-real-24", ["A-011"], tar_ref("labs.oslo.kommune.no", "INST-0500400"), "Oslo", [
    e("core.page_verdict", "confirms_activity", f"{PV} confirms_activity: the municipality's own developer hackathon testing LLMs (pilot/experiment, internal, not public-facing)",
      "Vi ønsket å teste ut alt fra nye store språkmodeller (a la ChatGPT)", jc="JC-R14")])
add("v27-real-25", ["A-011", "A-010"], tar_ref("labs.oslo.kommune.no", "INST-0673165"), "CITY OF OSLO", [
    e("core.page_verdict", "other_body", f"{PV} other_body: similarly named organisation (Oslo kommune, Norway) for a US city named Oslo; X30 identical-name pair",
      "Origo er blitt Digitaliseringsetaten")], "Same stored page as v27-real-24 under a different institution.")
add("v27-real-26", ["A-011", "A-020"], tar_ref("highland.gov.uk", "INST-0644700"), "Kilmallie", [
    e("core.page_verdict", "other_body", f"{PV} other_body: parent/higher-level body (The Highland Council) for a community-council-level institution",
      "This report introduces a new policy for the Council covering the responsible use of"),
    e("core.evaluation_documented", "required_or_planned", f"{CB} core.evaluation_documented required_or_planned: a policy that requires evaluation of GenAI tools",
      "Ensure AI systems are tested for fairness, accuracy, and security", scope="activity:Highland Council AI Policy", jc="JC-R15"),
])
add("v27-real-27", ["A-011"], tar_ref("beemata.co.id", "INST-0453011"), "Kota Bitung", [
    e("core.page_verdict", "other_body", f"{PV} other_body: vendor/marketing page that only uses the place name",
      "Bee Mata membangun fitur AI yang terintegrasi rapi ke sistem yang sudah Anda pakai di Bitung")])
add("v27-real-28", ["A-011"], tar_ref("gov.sr/inspirerende-ai-workshop", "INST-0546192"), "Ministry Of Public Works", [
    e("core.page_verdict", "ambiguous_attribution", f"{PV} ambiguous_attribution: government-wide GenAI launch (AI chatbot, R-016) by e-Government Suriname, no confirmation this ministry takes part",
      "de officiële lancering van zowel de AI Chatbot als de e-Visa applicatie", jc="JC-R16")])
add("v27-real-29", ["A-011"], tar_ref("city.chiba.jp", "INST-0462130"), "千葉市", [
    e("core.page_verdict", "event_only", f"{PV} event_only: public GenAI course for residents and workers",
      "ビジネスで使える生成ＡＩ活用講座")])
add("v27-real-30", ["A-011"], tar_ref("heidekreis.de", "INST-0096271"), "Landkreis Heidekreis", [
    e("core.page_verdict", "event_only", f"{PV} event_only: public workshop on using AI (ChatGPT) for job applications",
      "Ein eigener Account bei einem KI-Dienst wie ChatGPT ist hilfreich")])
add("v27-real-31", ["A-011", "A-003"], tar_ref("kelso-and-longview", "INST-0657431"), "Kelso School District", [
    e("core.page_verdict", "confirms_activity", f"{PV} confirms_activity: the district's own governance action on a named GenAI product (ban on school computers)",
      "the website has been blocked on school computers", jc="JC-R17"),
    e("core.governance_direction", "prohibits", f"{CB} core.governance_direction prohibits", "the website has been blocked on school computers",
      scope="activity:ChatGPT block on school computers"),
    e("n_activities", 2, "SPEC R-017: the ChatGPT block and the AI-detection application are separate activities; Longview's software belongs to another body", jc="JC-R17"),
])

# ------------------------------------------------------------------ A-010 real institution (three Wokingham pages)
F.append({"fixture_id": "v27-real-40", "kind": "real", "a_ids": ["A-010"],
          "institution": {"institution_id": WOK, "name": "Wokingham", "country": "United Kingdom"},
          "page_refs": [tar_ref(u, WOK)[0] for u in ("wokingham.gov.uk/foi/use-ai", "wokingham.gov.uk/foi/use-ai-recording-tools", "wokingham.gov.uk/foi/ai-recruitment")],
          "expected": [e("core.has_genai_activity", "yes", "SPEC R-005 / codebook truth table: >= 1 supported confirms_activity page; absence pages do not block `yes`",
                         "Staff may use approved Generative AI tools internally under policy governance.", scope="institution")],
          "note": "Page labels in v27-real-20..22."})

# ------------------------------------------------------------------ A-022 WS10 transfers (real ids)
rows = list(csv.DictReader((DRIVE / WS10).open(encoding="utf-8")))
pick = {}
for r in rows:
    pick.setdefault(r["correction_set"], r)
T = []
for n, (cs, r) in enumerate(sorted(pick.items()), start=1):
    T.append({"fixture_id": f"v27-transfer-{n:02d}", "kind": "real_transfer", "a_ids": ["A-022"],
              "transfer_ref": {"store": WS10, "finding_uid": r["finding_uid"], "row_before_sha256": r["row_before_sha256"]},
              "institution": {"institution_id": r["institution_uid"]},
              "expected": [
                  {"item": "correction_layer.owner_uid", "scope": "transfer", "value": r["candidate_owner_uid"],
                   "rule": "SPEC R-077 / A-022: each transfer appears under its verified owner (candidate_owner_uid of the RQ-003 list)", "judgement_call": "JC-T1"},
                  {"item": "correction_layer.ws10_disposition", "scope": "transfer", "value": None,
                   "rule": "SPEC A-022: with WS10 disposition; the list's reviewer_adoption_construct_verdict is PENDING for all 114 (correction_set " + cs + ")", "judgement_call": "JC-T2"},
                  {"item": "search_records_added", "scope": "transfer", "value": 0, "rule": "SPEC C-005 (T-034): the transfer path invents no search records"},
                  {"item": "denominator_change", "scope": "transfer", "value": 0, "rule": "SPEC C-005: nothing added to denominators"},
              ],
              "note": f"{r['activity_name']} ({cs})"})


def main():
    (HERE / "real.json").write_text(json.dumps({"_about": "T-040 real-page fixtures; generated by build_real.py", "fixtures": F},
                                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    (HERE / "transfers.json").write_text(json.dumps({"_about": "T-040 WS10 transfer fixtures (A-022); generated by build_real.py", "fixtures": T},
                                                    ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(len(F), "real,", len(T), "transfer fixtures")


if __name__ == "__main__":
    main()
