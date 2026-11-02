# Draft T-051 issue — additive storage and correction interface

Target: simonepaciphd/g3o-api; proposed owner: Colin.

Status: INTERNAL DRAFT — NOT SENT. PI contract approval is recorded; posting still requires explicit PI instruction after T-050B conformance. Colin acceptance A-019 remains pending. No implementation, migration, database-write, deploy or release authorization is conveyed by this draft.

Approved source: planning/handoffs/D-007-interface-spec.md and D-007-field-map.json on local branch planning/r11-rcd009 (approved governance commit e06cf4bd37772631e3171eccc7a5fdc34238c1b2). Decision page SHA256 d9ca34714331b5a565a3f30ca56a34dccc2ceb8a74ebf39ac37889d2d4a29977, S1a/S2a/P1a/P2. Replace the local source pointer with a verified accessible publication link before sending; do not claim an unpublished commit is remotely available.

The instrument and storage implementation is local-fixture work until T-030/T-035 bind actual runtime configuration. T-050B compares implemented T-012/T-027 contracts before seeking consumer acceptance. Generated data dictionary owns definitions; the storage map owns physical locations and encodings.

Requested contract review:
- Preserve existing institution/run/activity/source keys; sources are page × activity evidence claims, not unique URLs. Seven evaluation fields stay on each finding × page claim.
- Add version/setup/channel columns and the exact questionnaire/storage fields from the approved map. Preserve keyed full-text support, original observation endpoints, pairwise relations and internal per-code coder records. Keep instrument payload ID distinct from the stored-record byte hash.
- Preserve original observations. Correction rows link original observation IDs and use a distinct correction run/release ID; they create no search/sweep records and do not alter denominators.
- Historical missing additions use NULL plus legacy_not_collected or historical_provenance_unavailable, retaining only supported version facts. Do not manufacture signed missing tokens or certify old provenance.
- Keep full extracted emails, provider details/distributions and local paths internal. Public email projection is domain/count pairs for distinct addresses per actual page, domain lowercase only, local case retained; no alias assumptions. Existing unmasked-quote rule remains.
- Keep every 2.7 row hidden until PI release. Correction rows are wave-free; ordinary rows retain wave windows. Own required views/materialized aggregates and explicit refresh/watermark verification.
- Provide forward/down migration review and dry-run correction loader. Disposable-branch creation/writes and live apply retain their named PI gates; this draft does not authorize them.

A-019 reply requested after authorized delivery: accept or identify exact field/grain/type/key/provenance deviations. Implementation conformance and actual runtime producer evidence must be linked separately.
