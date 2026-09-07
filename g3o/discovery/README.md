# `g3o.discovery` — Stage 1: candidate source discovery

Stage 1 of the pipeline (see [`docs/architecture.md`](../../docs/architecture.md)). Maps institutions to candidate URLs via the Google Search API (Serper).

## Modules

- `serper_client.py` — Serper.dev client with retry + on-disk cache. Falls back to mock data when `SERPER_API_KEY` is unset, so the rest of the pipeline can be exercised without API credentials.
- `query_builder.py` — the query builders and the three rosters they read: `DOMAIN_SUFFIX_BY_LANG` (leg 1, 90 rows, tabled for signature 2026-09-03), `EVIDENCE_TERMS_BY_LANG` (legs 2 and open, 90 rows, PI-signed 2026-08-31), and the legacy `GENAI_TERMS_BY_LANG`. Each has a fingerprint the run manifest records.
- `domain_pick.py` — the naive first-non-aggregator domain pick, recorded on every chain run and deliberately not acted on; Stage 2 decides.

## The legs (`discovery_mode="chain"`, the default since 2026-08-01)

| leg | builder | query | runs |
|---|---|---|---|
| 1 | `build_domain_queries` | `<name> <country> <disambiguation> official website` | every institution, English |
| 1′ fallback | `build_domain_queries` | same shape, localized suffix | `discovery_leg1_multilingual`; only where Stage 2 found no site |
| 2 | `build_evidence_query` | `site:<domain> <term>` | per policy language, where a site is known |
| open | `build_open_evidence_queries` | `"<name>" <country> <disambiguation> "<term>"` | `discovery_evidence_open`; every institution, per policy language |

Languages come from the signed country→language policy (`g3o.common.languages`, `language_policy="2026-08-30"`), English always included. A language with no roster row raises before the first credit; there is no silent English fallback.

The runners live in `g3o.run.presweep.stage_discovery`; artifacts are `1a_discovery_general.json` (leg 1, both passes), `1b_discovery_site_restricted.json` (leg 2) and `1d_discovery_evidence_open.json` (open leg), one per institution, each URL carrying `found_by` — every query and language that surfaced it.

## CLI

```bash
python -m g3o discover --institution "City of Helsinki" --languages en,fi --limit 3
```

Returns a JSON list of search results (one record per hit) on stdout.
