# RC-D-011 email alignment — prepared engineering follow-up

Status: COMPLETED for the authorized bounded offline follow-up at 36d88bc7e20b3347b92f72e749d12f43a36ccc27. Independent verification: RC-D-011-local-verification.json; successor gates: RC-D-011-next-stage.md. The original assignment below is retained as historical task scope.
Authority: Simone's 2026-11-02 instruction in ../deltas/RC-D-011.md; SPEC v001.15 R-058; D-007 interface v1.1.
Replaces the old NEXT-T014 case-preservation repair.

Lowercase the entire extracted email address (local part and domain) before deduplication; count case-only variants once per actual page. Keep full normalized addresses internal and publish only domain/count pairs. Do not collapse aliases or plus-addresses; supporting quotes remain verbatim.

Owner: T-012 storage follow-up; T-024/T-028 consume the result under existing gates.
Inspected implementation base: 686882547d3390c05019256d6d120f4e6c1eb6b2, reclass/t027-record at C:/Users/spaci/worktrees/G3O-eng-b-t027.
Do not assume this checkout has signed r11: it retains r8. Assemble authoritative r11 codebook and LABELS inputs explicitly before claiming signed-runtime coverage. Do not silently change codebook pins or broaden the task.

Expected touchpoints (confirm before claiming/writing): g3o/common/storage.py, g3o/common/storage_fields.py (revised map SHA256 only), tests/test_storage.py and focused relevant storage/serialization tests. Preserve T-014's whole-address lowercasing. Check actual internal email storage output as well as the public counter; both must use approved normalization. Report any required producer change beyond existing claim scope to the integrator.

Required verification:
1. Direct mixed-case input Alice@EXAMPLE.org, alice@example.org, Alice@example.org yields one lowercase internal address and example.org count 1; distinct bob adds one.
2. Repeated addresses count once; plus tags/aliases stay distinct except for case.
3. Extractor-to-storage path agrees with direct input; missing/unavailable extraction is not fabricated as zero.
4. JSON/CSV round-trip preserves normalized internal lists and domain counts; public extracted-email projection contains no complete addresses or local paths.
5. Page/activity duplication retains actual-page grain. Existing qualified storage and T-027 regressions stay intact.
6. New MAP_SOURCE_SHA256 matches approved field-map bytes; all 120 mappings retain prior grain, type and visibility.
Return exact base/commit hashes, diff, commands/results and limitations for renewed local T-050B email conformance. Prior S2a results do not prove this implementation.

Runtime integration, T-050B send/Colin acceptance, T-031 and publication gates remain. No paid calls, external sends, DB writes, push/merge/deploy, or unrelated successor launch.
