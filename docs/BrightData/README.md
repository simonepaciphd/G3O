# Routing Stage 4 through Bright Data

**Status: wired, inert, and never yet run through a live provider.** The code path
exists and is tested; no G3O run has ever fetched a page through a residential proxy.
Everything below the "Turning it on" heading is written to be executed, not to be
believed — verify each step's output rather than assuming the step worked.

> ### ⚠ Two gates stand before any of this is used
>
> **1. A legal review the PI ruled must come first.** On 2026-08-26 the PI ruled
> legal review **before** the code change, scoped *"across the whole vendor chain,
> incl. Bright Data"* (`personal/memory/researcher-log.md`, *evidence-layer
> custody*, decision 6). The Bright Data MSA was read in that session and three
> findings bear directly on this document: Bright Data *"may retain data Client has
> collected and may use it for its own purposes in its sole discretion"*, so G3O
> would **not be sole custodian of its own evidence layer**; the **KYC intended-use
> statement is contractually binding**, so anything like public archival deposit
> must be declared up front; and neither the AUP nor the MSA requires `robots.txt`
> or target-ToS compliance, so **G3O is stricter than its vendor demands**. Do not
> re-derive these — cite the entry.
>
> **2. No provisioned endpoint exists.** Credits received is not a gateway. See
> [`validation-probe.md`](./validation-probe.md).
>
> **The code being ready is not the same as the decision being made.** Nothing in
> this document authorises a run.

**Scope of this document.** How to point Stage 4 at a residential gateway, how to check
it is actually live, and how to turn it off. It is not a decision record: whether the
observatory *should* run this way is [ruled and disclosed elsewhere](#what-this-document-does-not-decide).

---

## Why this exists

Measured 2026-08-26 on run `r20260824T215623Z-bb4e`. A paired probe of 120 URLs — one
per institution, sampled from the 636 institutions whose triage kept URLs and whose every
fetch failed — run with identical code and identical headers from two egresses:

| egress | 200-with-body | what came back |
|---|---|---|
| DigitalOcean sfo3 (the run droplet) | **0 / 120** | 64× HTTP 406, 37× 403 |
| residential ISP | **91 / 120** | 10× 403, rest TLS/connection |

The user-agent is not the cause: the same probe from the droplet under a Chrome UA
returned the identical distribution. The discriminating variable is the egress ASN. This
is issue #90.

**The recovery is smaller than that table alone suggests.** See
[`../budget/cost-model.md`](../budget/cost-model.md) § *Residential proxy egress* for the
sizing against the wave-2 frame, which is the number to quote — not the 12.4%.

---

## The design, in one paragraph

`g3o/scrape/egress.py` is the only module that knows a proxy exists. It reads one
environment variable, `G3O_SCRAPE_PROXY`, through `g3o.common.config` (so it resolves
once per process, like every other engineering parameter), and hands the right shape to
each of Stage 4's three egress points: `requests` proxies for page fetches
(`g3o/scrape/fetcher.py`), the same for `robots.txt` (`g3o/scrape/politeness.py`), and
Playwright's split-field form for the headless render (`g3o/scrape/render.py`).

**All three move together, and that is a correctness property rather than a tidiness
one.** Fetching `robots.txt` direct while fetching pages through a proxy would decide
politeness from one identity and act on it from another — the D4 respect-robots decision
assumes those are the same host asking. Do not add a fourth egress point without routing
it through this module.

---

## Turning it on

### 1. Get the endpoint from the Bright Data console

You need four values. **Read them out of the console; do not reconstruct them from this
document.** The shapes below are the vendor's usual convention and are recorded as an
expectation to check against, not as a specification:

| value | expected shape | notes |
|---|---|---|
| host | `brd.superproxy.io` | conventional; confirm in the console |
| port | e.g. `33335` | zone-specific; there is no safe default |
| username | `brd-customer-<account>-zone-<zone>` | encodes the zone, so it changes per zone |
| password | opaque | rotate it if it has ever been pasted anywhere |

Assemble them as a single URL:

```
http://<username>:<password>@<host>:<port>
```

**http, not https, even though the targets are https.** A residential gateway is reached
over HTTP and then `CONNECT`s to the target. `egress.requests_proxies()` maps both
schemes to this one endpoint deliberately; an https-only mapping would send half of
Stage 4 out of the direct — blocked — egress, silently.

### 2. Set it on the droplet, in the environment and nowhere else

**Never in a file inside the repo. Never as a default in `config.py`. Never on a command
line** — a command line is visible in `ps` to every process on the box and lands in shell
history.

```bash
ssh g3o-run-01
umask 077                      # before the file exists, not after
printf 'G3O_SCRAPE_PROXY=%s\n' 'http://USER:PASS@HOST:PORT' >> ~/.g3o-egress.env
chmod 600 ~/.g3o-egress.env
```

Then source it only in the shell that launches the run:

```bash
set -a; . ~/.g3o-egress.env; set +a
~/venv/bin/python -m g3o.cli ...
```

> `~/venv/bin/python`, named explicitly. `~/G3O/.venv` exists again against the PI's
> 2026-08-19 ruling, and a bare `python` may find it.

**Check it did not reach your shell history**, which is the leak this whole procedure is
arranged to avoid:

```bash
grep -c 'G3O_SCRAPE_PROXY=http' ~/.bash_history   # expect 0
```

### 3. Verify it is actually live

```bash
~/venv/bin/python scripts/verify_egress.py
```

The script reports the public IP and reverse-DNS seen by an echo service, direct and
through the proxy, and **prints no credential on any path, including its failure paths**.
A live residential gateway shows a different IP from the direct arm, and one that does
not resolve to a hosting provider.

**A same-IP result means the proxy is not in the path** — treat it as a failure even
though nothing raised.

### 4. Confirm the run recorded it

Every run writes its egress identity into `manifest.json` as `run_egress`:

```json
{ "mode": "proxy", "endpoint": "brd.superproxy.io:33335", "credentialed": true }
```

Host and port only, plus a flag saying a secret was in play. **If you ever see a
username or password in a manifest, stop the run and rotate the credential** — that is a
defect, not a configuration choice, and `tests/test_egress.py` should have caught it.

The resume guard compares this field across resumes: a run that scraped half its
institutions direct and half through a proxy has two different scrape instruments in one
artifact and no column saying which, so it refuses to resume rather than silently
producing one.

---

## Turning it off

**Unsetting the variable is the whole procedure.** Empty or absent means direct, which is
the historical behaviour and the default; `tests/test_egress.py` asserts that a direct run
is byte-identical to what it was before this module existed, down to Playwright's launch
kwargs.

```bash
unset G3O_SCRAPE_PROXY
rm ~/.g3o-egress.env          # if you want it gone rather than dormant
```

**You cannot turn it off mid-run.** The resume guard will refuse — deliberately. Finish
the run or start a new one.

---

## Failure modes, and what they look like

| symptom | cause | what to do |
|---|---|---|
| Run refuses to start, `EgressConfigError` | The URL cannot work — whitespace, missing port, wrong scheme, no credentials | Read the message; it names the defect and never the value |
| Run refuses to start, `EgressConfigError` naming the user-agent | `USER_AGENT` carries no contact point | Set one — see below. This fires only when the proxy is on |
| `verify_egress.py` shows the same IP both arms | The proxy is not in the path | Re-check the port; a wrong port often connects to *something* |
| Every fetch fails, yield collapses to near zero | Gateway rejecting auth (407) | Re-read the username from the console — it encodes the zone |
| Resume aborts naming `run_egress` | The egress changed between passes | Intended. Do not override it |

**The `EgressConfigError` guard exists because of a measured failure mode**, not a
hypothetical one. A proxy URL `requests` cannot parse — a trailing space is enough, and
that is what a copy-paste out of a password manager leaves behind — does not stop a run.
It fails *every fetch individually*, so the run completes and reports a catastrophic
yield that looks like the network rather than like a typo. Worse, the exception message
`requests` raises contains the whole URL including `user:pass`, and Stage 4 wrote that
into `_attrition.jsonl` once per URL. Both halves are fixed as of 2026-08-27: the ledgers
redact, and the run refuses to start. Do not remove either; they are belt and braces on a
path where the failure is silent and the blast radius is a whole run.

---

## The user-agent must carry a contact, and only when proxied

`egress.validate()` refuses a **proxied** run whose `USER_AGENT` contains no URL
and no email address. A direct run is untouched, and every run before 2026-08-27
went out under the bare default without complaint.

**The argument, because the guard is easy to mistake for boilerplate.** Routing
Stage 4 through a residential gateway makes the observatory opaque at the
*network* layer. The user-agent is then the only identity control it still holds
— the only way a site operator can tell what is fetching them, or ask it to stop.
Going opaque at both layers at once is a different act from going opaque at one,
and it should not be reachable by forgetting to set a variable.

**Which it currently is.** Measured 2026-08-27:

| box | `USER_AGENT` | contact? |
|---|---|---|
| the laptop | set in `.env`, carries a repo URL and an email | yes |
| **`g3o-run-01`, where runs actually happen** | **not set at all** | **no — bare `G3O-Observatory/0.1`** |

So every production sweep to date has identified itself to government websites
with no way to be reached, while the machine that barely scrapes identifies itself
properly. Nothing compared them, so nothing caught it. This was surfaced as a
*"cheap fix"* on 2026-08-26 (researcher-log, *evidence-layer custody*) and had not
been actioned.

Set it in the same env file as the proxy:

```bash
printf 'USER_AGENT=G3O-Observatory/0.1 (+%s)
' 'https://example.org/crawler' >> ~/.g3o-egress.env
```

**The value is the PI's to choose** — which page, which address — and is
deliberately not defaulted anywhere in the code, because an unreviewed value here
would be shipped to every government website the observatory touches.

Safe for politeness: `urllib.robotparser` compares only the token before the first
`/`, so a `(+...)` suffix cannot change which `robots.txt` rules apply. Asserted
in `tests/test_egress.py` against the real parser, not assumed.

---

## What this document does not decide

Three questions are **open and are not engineering's** — they are recorded here so that
whoever turns this on knows they are outstanding, and they are argued in full in the
2026-08-27 closeout note (`coord/mailbox/simone/`):

1. **The methods disclosure.** A paper describing an automated observatory of government
   websites should state how its traffic presented itself. Not drafted here.
2. **`scrape_respect_robots` stays `true`,** and all three egress points move together
   precisely so politeness is decided and acted on by one identity. This is a real
   defence and belongs in the record, because "residential proxy" alone reads worse than
   what this design actually does.
3. **Whether this touches the project's human-subjects posture.** These are institutional
   websites, not people — but that judgement is the PI's, and possibly Stanford's IRB's.

**A production or wave run through the proxy is the PI's call and has not been made.**
Nothing in this document authorises one.
