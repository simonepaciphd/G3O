# The paired egress validation probe — designed, not run

**Status: BLOCKED, and the blocker is not technical.** Written 2026-08-27 to be
executable in about ten minutes by whoever unblocks it. Nothing here has been run.

## Why it is blocked — two independent gates, either one sufficient

1. **No provisioned endpoint.** The project record says Bright Data is *"in talks
   as of 2026-08-26"* with ~$1k/month of credits received. Credits received is not
   a provisioned gateway. Verified absent 2026-08-27: no `G3O_SCRAPE_PROXY` in
   either `.env`, no host/port/zone/credential anywhere in the repo, the Drive
   project tree, or `coord/`.
2. **A PI ruling that comes first.** On 2026-08-26 the PI ruled legal review
   **before** the code change, scoped *"across the whole vendor chain, incl.
   Bright Data"* (researcher-log, *evidence-layer custody*, decision 6). Sending
   real traffic through the gateway is *use of the Service*, and the MSA's KYC
   intended-use statement is contractually binding (same entry, finding (b)). So
   the probe is downstream of that review even if an endpoint appears tomorrow.

**Owner of gate 1:** whoever holds the Bright Data relationship — not this lane.
**Owner of gate 2:** the PI. `G3O YLD` withdrew its $40 authorization on
2026-08-27 for exactly this reason, having initially priced it: *"a substantive
question wearing a procedural costume."*

## The design

Repeat the 2026-08-26 pairing with a third arm. **Same URLs, same code, same
headers** — the only variable is egress, which is the whole point.

- **Frame:** the same 120 URLs, one per institution, drawn from the 636
  institutions on `r20260824T215623Z-bb4e` whose triage kept URLs and whose every
  fetch failed. Reuse the original draw rather than redrawing: a fresh sample
  would confound the arm comparison with sampling noise, and the wave-1 numbers
  (0/120 and 91/120) are only interpretable against the same frame.
- **Arms:** (A) the run droplet direct — expected 0/120, and it is the negative
  control, so run it rather than assuming it still holds; (B) residential ISP,
  the 2026-08-26 arm, as the reproducibility check; (C) **Bright Data**, the new
  arm.
- **Primary outcome:** count of 200-with-body, per arm. Secondary: the status
  distribution, because wave 1's signature was 64× 406 / 37× 403 and a different
  signature would mean something changed underneath.
- **Read it as:** arm C ≈ arm B ⇒ the fix works. Arm C ≈ arm A ⇒ the gateway is
  not residential, or not in the path. **Arm C between them is the interesting
  case and the one the wave-1 result cannot predict** — partial recovery would
  mean the block is not purely ASN-based.

## Conditions on running it, all of which were set before it was blocked

- **120 URLs, not a pipeline stage.** Do not route Stage 4 of a real run through
  the proxy. That is a production run and it is the PI's call.
- **No credential in any artifact, including the probe's own logs.** The
  credential-hygiene work is a prerequisite, not a parallel task: see
  `tests/test_egress.py`, and run `scripts/verify_egress.py` first.
- **Coordinate the droplet.** Arm A needs the box. `G3O LANG` held droplet
  priority on 2026-08-27; ask, do not assume.
- **Projected cost:** 120 URLs × ~177 KB mean HTML (measured 2026-08-27) ≈
  **21 MB**, so **well under $1 at any plausible per-GB rate.** The $40 that was
  authorised was two orders of magnitude more than this probe needs — the
  constraint was never the money.

## Executable form, once unblocked

```bash
ssh g3o-run-01
set -a; . ~/.g3o-egress.env; set +a          # arm C only
~/venv/bin/python scripts/verify_egress.py   # confirm the proxy is in the path
```

Then, per arm, with `G3O_SCRAPE_PROXY` set (C) or unset (A):

```bash
~/venv/bin/python - <<'EOF'
import json, os
from urllib.parse import urlsplit
import requests
from g3o.common import config
from g3o.scrape import egress

egress.validate()
urls = json.load(open(os.path.expanduser("~/probe-120-urls.json")))
proxies = egress.requests_proxies()
headers = {"user-agent": config.USER_AGENT}
out = []
for u in urls:
    try:
        r = requests.get(u, headers=headers, proxies=proxies, timeout=20)
        out.append({"url": u, "status": r.status_code, "bytes": len(r.content),
                    "server": r.headers.get("server")})
    except Exception as exc:
        # Class only. A requests proxy error can carry user:pass — measured
        # 2026-08-27 — and this file is an artifact.
        out.append({"url": u, "error": type(exc).__name__})
mode = egress.describe()["mode"]
json.dump({"egress": egress.describe(), "results": out},
          open(os.path.expanduser(f"~/probe-arm-{mode}.json"), "w"), indent=1)
ok = sum(1 for r in out if r.get("status") == 200 and r.get("bytes", 0) > 0)
print(f"arm={mode}  200-with-body: {ok}/{len(out)}")
EOF
```

**The `~/probe-120-urls.json` frame does not exist yet.** Regenerate it from
`bb4e`'s attrition ledger — the 636 all-fetch-failed institutions — or recover the
2026-08-26 draw if it was kept. **Recovering the original draw is strongly
preferable**; a redraw makes arms A and B non-comparable to their published
values, which costs the probe its two reference points.

## What this probe cannot tell you

- **Whether the recovered pages contain anything.** It measures bodies returned,
  not GenAI evidence found. The wave-2 probe suppressed 1 of 6
  attribution-valid positives to a fetch failure (`G3O DIAG`, 2026-08-27), which
  is the yield question — and it is separate.
- **Whether the egress is residential.** A different IP is not a residential IP.
  Check the ASN; that is the variable #90 actually measured.
- **The per-GB cost.** 120 HTML fetches will not exercise the PDF or render
  paths, which are 88% of the projected traffic. See
  [`../budget/cost-model.md`](../budget/cost-model.md) § *Residential proxy
  egress*.
