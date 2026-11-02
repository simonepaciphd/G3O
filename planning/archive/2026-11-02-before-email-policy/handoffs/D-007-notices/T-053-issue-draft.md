# Draft T-053 issue — version-aware published fields and supporting text

Target: simonepaciphd/g3o-website; proposed owner: Colin.

Status: INTERNAL DRAFT — NOT SENT. PI contract approval is recorded; posting still requires explicit PI instruction after T-050B conformance. Colin acceptance A-019 remains pending. No implementation, migration, database-write, deploy or release authorization is conveyed by this draft.

Approved source: planning/handoffs/D-007-interface-spec.md and D-007-field-map.json on local branch planning/r11-rcd009 (approved governance commit e06cf4bd37772631e3171eccc7a5fdc34238c1b2). Decision page SHA256 d9ca34714331b5a565a3f30ca56a34dccc2ceb8a74ebf39ac37889d2d4a29977, S1a/S2a/P1a/P2. Replace the local source pointer with a verified accessible publication link before sending; do not claim an unpublished commit is remotely available.

The instrument and storage implementation is local-fixture work until T-030/T-035 bind actual runtime configuration. T-050B compares implemented T-012/T-027 contracts before seeking consumer acceptance. Generated data dictionary owns definitions; the storage map owns physical locations and encodings.

Requested interface:
- Consume only the accepted staged API. Show the latest eligible institution row and its actual version; make older labelled history available through the agreed API contract.
- Hide new fields on v2.5-latest rows. Present its no result with the v2.5 rule label, and preserve comparability/unmappable states rather than inventing new questionnaire responses.
- Show confirmed public activities, approved public questionnaire fields and domain/count pairs. Counts mean distinct observed address strings per actual page, not people or repeated occurrences.
- Keep full supporting text available; the website display cap still awaits its existing PI gate. Display-only translation must not replace stored source text.
- Respect the PI release flag and internal-field exclusions, including nested rollups/provenance. No index UI is authorized.
- Use generated plain-language item/part/value labels and signed label_rules; do not substitute raw codes. Computed years use actual year strings; free text has no finite label map.

Public copy, cap value, staging review and deployment retain their named gates. This draft does not authorize publication or contact.
