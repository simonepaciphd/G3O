# RC-D-011 local reconciliation - 2026-11-02

Execution state: approved bounded offline email follow-up complete; full pipeline partial. Sole integrator: 20261102-codex-v2-53c1342c65a05a30. SPEC v001.15, RESOURCES v001.3, signed r11 and approved D-007 v1.1/map bytes are unchanged. Source governance is e49c497963e150bb89fd4c710780d52d1c2899ba; the application lock remains its historical snapshot, not a hash assertion about later execution-status edits.

Implementation 36d88bc7e20b3347b92f72e749d12f43a36ccc27, tree d96293f3cb682eb21d0ba5a1cf2861cb7e8e65ff, base 686882547d3390c05019256d6d120f4e6c1eb6b2. Five files changed on reclass/rcd011-email; extractor, T-027, codebook and runtime remain unchanged. Local commit is clean and unpushed by this task.

| Requirement | Evidence | Disposition and limit |
|---|---|---|
| R-058 / RC-D-011 full-address lowercase, distinct page addresses, plus/alias boundaries | 22 independent tests; direct/extractor parity, repeat/idempotence and exact counts | MET-AS-CHANGED for the available local storage/helper path |
| R-023 / D-007 internal storage and JSON/CSV | Independent roundtrips and Stage7 builders; normalized internal lists, public domain/count cells | MET locally; T-024 complete extraction/gate integration remains UNVERIFIED |
| D-007 actual-page versus claim grain | One page/two activities; different pages with same text; separate fetch provenance; cross-run rejection | MET for local fixtures; actual producer integration remains UNVERIFIED |
| R-050 / D-007 missingness | Observed empty list, three signed tokens, historical null/blank with reasons; incomplete new rows refused | MET locally; Q01 exact public missing-state convention carried downstream, unchanged |
| R-052/R-057/R-058 privacy and quotes | Public projection excludes full-address values/internal supports/coder records/local paths; quotes remain verbatim | MET for privacy projection; no release eligibility/API/site acceptance claimed |
| D-007 120-item mapping | Exact map pin 5dfb8dc5d4cb0bdc9e14dc9cf0216cfd8cd47281bf648cafff8cc70c70ee2465; 960 compiled-field comparisons; unchanged FIELDS | MET locally; only approved normalization policy and pin changed |
| R-026/A-013 T-027 regression preservation | 192 independent focused regressions; 326 engineer regressions; T-027 source/test blobs unchanged | Prior acceptance preserved; no global re-certification |
| RS-010/018/039 source traceability | Signed r11 and LABELS exact pins; nine generated outputs reproduced in memory | MET for source identity; candidate retains r8 and is NOT an assembled r11 runtime |
| A-019/T-050B, T-031 and runtime/publication | No authorized send, Colin acceptance or integrated runtime produced | UNVERIFIED; existing gates remain |

No implementation findings remain. Two preliminary mapping audit assertions were reviewer-harness mistakes; logs are preserved, and the final independent run passes. Earlier S2a evidence is historical; the superseded T-014 case-preservation repair was not implemented. Prior T-012 Windows-I/O cross-invocation qualification and six strict T-035 exceptions remain. No full-suite or actual provider/pipeline rerun is claimed.

Traceability: T-012 produces the five-file change; RC-D-011/R-058 supplies the fixed PI decision; D-007/RS-010/018/039 supply schema/map/instrument contracts. Engineer commands and independent COMMANDS.txt reproduce the bounded synthetic tests; source-audit/audit_sources.py reproduces nine generated outputs in memory. Exact manifests, hashes, case coverage and limitations are in ../../handoffs/RC-D-011-local-verification.json. Next-stage gates: ../../handoffs/RC-D-011-next-stage.md. No substantive policy decision was taken here.
