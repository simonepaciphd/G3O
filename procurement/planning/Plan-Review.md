# Plan review: G3O procurement pipeline, Plan-Draft v001-draft.1

## Review record

- **Reviewer:** an isolated general-purpose subagent (claude-opus-5-5). It ran read-only, on 2026-10-27.
- **Inputs:** `planning-adversarial-review-protocol.md` v0.2 in PLAN mode; `SPEC.md` v001-draft.3; `RESOURCES.md` v001; `Plan-Draft.md` v001-draft.1; `Plan-Manifest.md`; code at `procurement/main` @ `cee79b2`; the Drive subproject.
- **Withheld:** the mapper's rationale was not given to the reviewer.
- **Verdict:** Requires user decisions.
- **Severity counts:** Critical 0, High 7, Medium 12, Low 6.
- **Tests:** the reviewer re-ran `pytest` at `cee79b2` and got 105 passed.

## Parent's check of the evidence (2026-10-27)

The parent spot-checked the reviewer's evidence against the code and the live repo. Every check confirmed the reviewer's claim.

| Finding | What the parent checked | Result |
|---|---|---|
| PF-013 | `matcher.py` | Docstring line 30 says auto-accept applies to tiers 1/3; lines 316 and 335 return `"auto_accepted"` |
| PF-007 | `classify.py` | Lines 242-243 say the snippet is "verbatim source text — never a paraphrase, never a translation" |
| PF-011 | `procurement_record.schema.json`, `models.py` | `ocds_ocid` is present in both (`models.py` lines 103 and 170) |
| PF-002 | ARCE adapter | `fetch()` makes a live `requests.get` (line 92); `_cache_raw` only writes; `fetched_at=datetime.now` (line 207); no from-cache option in `cli.py` or `base.py` |
| PF-003 | `replay_n100.py` | `ROOT = HERE.parents[3]` plus `sys.path.insert`, so it imports the Drive `pipeline` |
| PF-006 | `sources.yaml` | No language field; "language" appears only inside free-text `tracker_notes_ra` (4 rows) |
| PF-015 | `gh api …/branches/procurement%2Fmain` | `protected: false` |
| PF-016 | `cli.py` lines 32-35 | Master and ledger defaults are relative to the subproject root |
| PF-005 | `classify.py` lines 209-211 | A per-record `confirms_absence` already exists |

## Disposition ledger

Dispositions follow `planning-adjudication-protocol.md`. Mechanical fixes are applied in `PLAN.md`. User decisions go to the PI as chat items U-1 to U-8.

| Finding | Severity / type | Disposition | Applied in / decision |
|---|---|---|---|
| PF-001 | HIGH / change-control | Split. (a) USER-DECISION: integrator and report surface. (b) ACCEPT: add a ruling-propagation task and a Stage-8 reconciliation card; T-024/T-031 done conditions become "ruling sent to integrator" | U-1, U-2; PLAN |
| PF-002 | HIGH / omission | ACCEPT: add a cache-replay mode task and a comparison field set. The excluded-field list becomes a PI gate on that task | PLAN |
| PF-003 | HIGH / interface | ACCEPT: port the replay into the repo ahead of T-019; add the edge port → T-045; add a T-045 self-check | PLAN |
| PF-004 | HIGH / dependency | ACCEPT: add the edge T-017 → T-019, a synthetic resolved-link fixture, and a Q-010 gate for Uruguay absence output | PLAN |
| PF-005 | MEDIUM / interface | ACCEPT-MODIFIED: T-019 writes a separate `absence` table with its own schema and key. Per-record `confirms_absence` stays staging evidence, unchanged. T-014 and T-020 consume the table explicitly. No coded meaning changes | PLAN |
| PF-006 | HIGH / omission + spec-question | USER-DECISION: who supplies each source's language(s), and how multilingual sources are treated | U-3 |
| PF-007 | HIGH / omission + spec-question | USER-DECISION (spec-question): how R-025's English translation is produced | U-4 |
| PF-008 | HIGH / dependency | ACCEPT: add an ARCE terms/robots task with the edge → T-035; add the edge T-028 → T-041 | PLAN |
| PF-009 | MEDIUM / dependency | ACCEPT: T-023 requires fan-out data in the non-Latin and multi-country strata; drop the slack claim; D-009 status becomes blocked | PLAN |
| PF-010 | MEDIUM / interface | ACCEPT: add the Q-030 and Q-031 residuals as gates on T-014 and T-040; T-014 outputs D-002 at contract grain | PLAN |
| PF-011 | MEDIUM / inefficiency | ACCEPT: drop the new `activity_id` and collapse on the existing `ocds_ocid`. Non-OCDS records get an empty key plus an internal flag, never a raise. T-015 shrinks to tests plus the flag and leaves the critical path | PLAN |
| PF-012 | MEDIUM / contradiction | USER-DECISION: present the 08-29 package labelled as historical, or regenerate it at `cee79b2` | U-5 |
| PF-013 | MEDIUM / contradiction + spec-question | ACCEPT the evidence correction to T-002. USER-DECISION: are tier-1/3 auto-accepts allowed before D-009? | U-6 |
| PF-014 | MEDIUM / review-gap | ACCEPT: T-009 set to `verified`-pending, with a check to open RS-035/RS-042 and add a fixture test | PLAN |
| PF-015 | MEDIUM / risk | USER-DECISION: protect `procurement/main` (PR + CI required), or accept convention-only control | U-7 |
| PF-016 | MEDIUM / omission | ACCEPT: the card defaults pass absolute Drive paths for `--master`/`--ledger`/`--out-dir`/`--cache-dir`. USER-DECISION: Drive access grants for the RAs | U-8 (with U-1 batch) |
| PF-017 | MEDIUM / omission | ACCEPT: attach Q-011, Q-017, Q-021, Q-022 and Q-026 as gates on the named cards | PLAN |
| PF-018 | MEDIUM / granularity | USER-DECISION: who runs fan-out beyond Uruguay and Italy, and whether to move the Drive-only tasks (T-022, T-047, T-048) to Asenat | U-8 |
| PF-019 | MEDIUM / contradiction | ACCEPT-MODIFIED: add a PI gate on T-036 to adopt a query set v1.x with `it` terms supplied by the multilingual subproject (R-010, R-035). The ruling itself waits until the terms exist | PLAN |
| PF-020 | MEDIUM / dependency | ACCEPT: remove the edges T-011 → T-022/T-047/T-048/T-037 and T-013 → T-018; T-047 is ready now; T-013 placed by lane capacity | PLAN |
| PF-021 | LOW / interface | ACCEPT: put the `contract_version` manifest field in T-013's write claim; add the edge T-047 → T-035; T-035's check uses the T-047 hash↔commit record | PLAN |
| PF-022 | LOW / review-gap | ACCEPT: R-033 cites T-020; R-034 partial (no codebook/query version on records), so a field is added in T-020; R-026 added to T-014; R-019 removed from T-001 | PLAN |
| PF-023 | LOW / granularity | ACCEPT: T-011 uses `merge-base --is-ancestor`; T-015 says "4 synthetic fixtures"; T-027 script path set; T-026 gets the coder-assignment gate | PLAN |
| PF-024 | LOW / omission | ACCEPT-MODIFIED: the planning commit is already a Stage 6 action (protocol rule 13); the T-011 note now cites the Asenat email draft (it exists in the session scratchpad and is PI-held). ACCEPT: add a task applying the approved VP §B amendment | PLAN |
| PF-025 | LOW / granularity | ACCEPT: T-006 and T-008 become `verified (preparation/draft)`; Wave 4 Ainhoa tasks are sequenced | PLAN |

**Strengths to preserve (reviewer):**
1. PI-reserved items stay as BLOCKED-SPEC gates.
2. The completed claims T-001 to T-004 hold (105 tests pass).
3. Wave 3 runs as one sequential lane.

## Reviewer's findings (as returned, condensed only for line length; IDs, evidence and patches unchanged)

**PF-001 — HIGH / CHANGE-CONTROL**
- **Defect:** the delta channel has no owner, no surface and no propagation task.
  - Reports go to the DEC-009 integrator, which is OPEN.
  - No delivery surface exists (Stage 7 channel OPEN).
  - About 25 researcher gates exist, but no task records a PI ruling, versions the SPEC, or releases blocked cards.
  - T-024 ("PI decision recorded in SPEC Q-009b") and T-031 ("recorded at Q-009a") contradict the rule forbidding SPEC edits.
  - There is no Stage-8 card.
- **Patch:**
  - name the integrator (user);
  - name one report surface;
  - add a task: ruling → SPEC version → CHANGELOG → unblock;
  - reword T-024/T-031;
  - add a reconciliation card.

**PF-002 — HIGH / OMISSION**
- **Defect:** there is no offline replay, so A-009, A-010 and D-013 cannot produce "identical" output.
  - ARCE `fetch()` makes a live GET (lines 182-208).
  - `_cache_raw` only writes.
  - `fetched_at=datetime.now()`.
  - `cli.py run` has no cache-replay.
  - The only replay is the Drive script `replay_n100.py`.
- **Patch:**
  - add a `--from-cache <dir>` replay mode in `Pipeline`/the adapter base;
  - define the A-009 comparison field set, excluding `fetched_at` and manifest timestamps (PI signs the list);
  - add the edge to T-041.

**PF-003 — HIGH / INTERFACE**
- **Defect:** the replay self-checks run against the Drive code, not the branch.
  - `replay_n100.py` lines 19-21 import `PP\pipeline\` (= `55fe353`).
  - T-015 and T-019 rely on "the replay".
  - T-045 archiving breaks the script and RS-047.
  - The script is itself code on Drive (R-038).
- **Patch:**
  - port the replay into the repo (`procurement/tools/` or a pytest over the 101 fixtures) ahead of T-015;
  - add the edge port → T-045;
  - add a T-045 check that no Drive script imports `PP\pipeline`.

**PF-004 — HIGH / DEPENDENCY**
- **Defect:** T-019 needs resolved institutions it does not depend on.
  - The grain is institution × repository × window, and R-018 applies.
  - T-019 lists the link table as an input, yet its only edge is T-015 → T-019.
  - RS-047 has 0 of 132 linked, so the self-check is vacuous.
- **Patch:**
  - add the edge T-017 → T-019;
  - add a synthetic fixture with resolved links;
  - add a Q-010 gate for Uruguay absence.

**PF-005 — MEDIUM / INTERFACE**
- **Defect:** the absence-row grain clashes with existing staging.
  - `classify.py:211` already labels per record (71 records in RS-047).
  - T-019 adds per-cell rows into a per-award schema, which would double-count in T-020 and T-014.
- **Patch:** write a separate `absence` table, or relabel per-record evidence. Name the choice on the card; T-014 and T-020 consume it.

**PF-006 — HIGH / OMISSION + SPEC-QUESTION**
- **Defect:** T-020's language input does not exist.
  - `sources.yaml` has no language field, only free text such as "[F134] different language".
  - The tracker has no language column.
  - So D-011's language status has no producer.
  - Deciding a source's languages may fall under N-004.
- **Patch:** add a `languages` field producer, plus a PI gate on who supplies it and how multilingual sources are handled.

**PF-007 — HIGH / OMISSION + SPEC-QUESTION**
- **Defect:** R-025's translation has no producer.
  - `classify.py:242-243` keeps the snippet verbatim and never translates.
  - T-001 and T-014 do not translate.
  - R-009/N-005 bar LLM adjudication, and the translation method is unstated.
  - Every non-English D-001 row fails R-025.
- **Patch:** add a PI gate on the method (human, MT, or LLM translation if ruled not adjudication) and a producer feeding T-014.

**PF-008 — HIGH / DEPENDENCY**
- **Defect:** the Uruguay terms review and the D-007 inputs have no producer.
  - T-035's input "ARCE terms review" has no producer (RS-034 "ToS review open").
  - A-005/R-029 require it before a full run.
  - T-041 needs D-007, but there is no T-028 edge.
- **Patch:** add an ARCE terms task with an edge → T-035; add the edge T-028 → T-041.

**PF-009 — MEDIUM / DEPENDENCY**
- **Defect:** the T-022 strata depend on fan-out.
  - ES §5 line 175 requires several countries and Latin plus non-Latin script.
  - The only queue is Uruguay: 48 buyers, Latin script.
  - The "slack" claim is false, and A-008/R-016 sit behind T-034.x.
- **Patch:**
  - add the edge T-034.x (≥1 non-Latin source and ≥2 more countries) → T-023;
  - update the D-009 status;
  - drop the slack claim.

**PF-010 — MEDIUM / INTERFACE**
- **Defect:** the D-002 join to activity-level rows is ungated.
  - The Q-031 residual gates only T-015/T-038, and the Q-030 residual only T-019.
  - T-014, T-021 and T-040 omit both.
  - `build_extension()` works per award.
- **Patch:** add both residual gates to T-014 and T-040; give D-002 a contract-grain output in T-014 or its own card.

**PF-011 — MEDIUM / INEFFICIENCY + RISK**
- **Defect:** DEC-003/T-015 duplicate a field that already exists.
  - `ocds_ocid` already exists (schemas; `models.py:103,170`).
  - Raising for non-OCDS sources blocks PNCP and about 85 non-OCDS smoke runs.
- **Patch:**
  - collapse on `ocds_ocid` in T-014;
  - non-OCDS: empty key plus an internal flag;
  - shrink T-015 or remove it from the critical path.

**PF-012 — MEDIUM / CONTRADICTION**
- **Defect:** T-031's self-check cannot be satisfied.
  - The 08-29 draft carries no code version.
  - It predates both R1-R8 (10-07) and `55fe353` (10-11).
- **Patch:** choose (a) present it labelled historical, pre-R1-R8, together with the RS-047 replay, or (b) regenerate the 5+5 sample at `cee79b2`.

**PF-013 — MEDIUM / CONTRADICTION + SPEC-QUESTION**
- **Defect:** the claim "no auto-accept" is false.
  - The `matcher.py` docstring says auto-accept applies to tiers 1 and 3.
  - Lines 316 and 335 return `auto_accepted`.
  - A-008 and ES §5 require per-tier precision first.
- **Patch:** correct the T-002 text; add a PI gate on whether tier-1/3 auto-accept is allowed before D-009.

**PF-014 — MEDIUM / REVIEW-GAP**
- **Defect:** T-009 is marked complete without verification.
  - Its evidence is LISTED, not opened.
  - No PNCP test exists.
- **Patch:** set it to verified-pending with a check, or to blocked on Q-028.

**PF-015 — MEDIUM / RISK**
- **Defect:** the shared-infrastructure gate is unenforced.
  - `procurement/main` is `protected: false`.
  - DEC-006 and R-037 rest on convention only.
- **Patch:** a PI-gated task to add protection (PR + CI required), or explicit acceptance of convention.

**PF-016 — MEDIUM / OMISSION**
- **Defect:** the RAs have no Drive or master access provisioned.
  - T-011 covers GitHub only.
  - `cli.py:33-35` master defaults resolve only from the Drive subproject.
  - T-022, T-035 and T-047 write to `PP\`.
- **Patch:** extend T-011 with Drive access; card defaults pass absolute paths.

**PF-017 — MEDIUM / OMISSION**
- **Defect:** Q-011, Q-017, Q-021, Q-022 and Q-026 are not gates anywhere, against the spec's P1 preamble.
- **Patch:** attach each to its named card.

**PF-018 — MEDIUM / GRANULARITY**
- **Defect:** fan-out beyond Uruguay and Italy has no owner.
  - Fan-out for "other countries" is unassigned.
  - No assignment or capacity gate exists.
  - Ainhoa is a single lane, while the Drive-only tasks could move.
- **Patch:** add an assignment/capacity gate card; offer T-022/T-047/T-048 to Asenat or another person.

**PF-019 — MEDIUM / CONTRADICTION**
- **Defect:** the Italy run needs a query-set change.
  - T-036 depends on Italian terms.
  - The defaults fix query set v1.0, and R-010 and R-035 forbid changing it here.
- **Patch:** add a PI gate to adopt v1.x with `it` terms, plus a versioning step.

**PF-020 — MEDIUM / DEPENDENCY**
- **Defect:** fake edges and a misplaced wave.
  - T-011 → T-022/T-047/T-048/T-037 carry no input.
  - T-013 has no predecessor, yet sits in Wave 4.
  - The bracket shows T-013 → T-018.
- **Patch:**
  - remove those edges;
  - T-047 is ready now;
  - keep T-013 → T-014 only.

**PF-021 — LOW / INTERFACE**
- **Defect:**
  - T-013 writes a manifest field `contract_version` that does not exist, from outside its write claim.
  - T-035's check "manifest code hash = repo commit" mixes a content hash with a commit id.
- **Patch:** add the field to T-013's claim; add the edge T-047 → T-035.

**PF-022 — LOW / REVIEW-GAP**
- **Defect:** coverage is overstated.
  - R-033's QC is `written >= fetched - errors`.
  - R-034 has no codebook or query version on records.
  - T-014 omits R-026.
  - R-019 is listed on T-001.

**PF-023 — LOW / GRANULARITY**
- **Defect:**
  - `ls-remote` cannot show ancestry.
  - T-015's synthetic fixtures are 4 JSON files plus a README, not 5.
  - T-027's script path is unspecified.
  - T-026 lacks the coder-assignment gate.

**PF-024 — LOW / OMISSION**
- **Defect:**
  - `procurement/planning/` is untracked, and there is no commit gate.
  - The Asenat email has no producer.
  - No task applies the VP §B amendment.

**PF-025 — LOW / GRANULARITY**
- **Defect:**
  - T-006 and T-008 are marked `complete` although they are preparation and drafts.
  - Wave 4 runs three of Ainhoa's tasks concurrently.

**Reviewer's coverage note:**
- Examined every D/R/A/C ID, every Q-ID by grep, all edges and wave claims, the code behind each card, the replay script, the checkpoint draft, the tracker headers, the branch commits and the protection status.
- Found nothing to report on:
  - the Wave 2 and Wave 3 collisions;
  - the T-001 to T-004 evidence;
  - the R-030 guard;
  - the ledger, duplicate and subnational claims;
  - 781cf0c being absent.

**What this review does not show (reviewer):**
- Issue bodies, collaborators, invite state and CI runs were not read.
- The canonical tracker Sheet and Asenat's machine were not read.
- PNCP behaviour was not exercised.
- The baseline fingerprint was not computed.
- ES, CB and VP were read only at the cited lines.
- The review makes no judgement of the PI's rulings.
