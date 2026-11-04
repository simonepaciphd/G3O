# Follow-up chat rulings, 2026-11-04

Session `20261104-claude-v2-afa657f8de5fe7e3` (Claude Code, `claude-opus-5-5`, researcher persona acting as plan integrator), card `coord/launch/2026-11-04/13-g3o-deploy-rulings.txt`.

Page reply: `g3o-deploy-blockers-2026-11-04.reply.json`, page_sha256 `a1c28a0849f9e64cbdd8a9de05307ea26cbaccb56943ddc2bab7faba725d93c9`, saved_at 2026-11-04T12:54:36.541Z. Bytes copied unchanged from the chief-of-staff scratchpad (sha256 html `6f492fb4…2f92415`, json `3ded26ca…b14b27`, reply `de9c120b…77c48`).

## Questions the integrator put in chat (summary)

1. S1: (a) the rule is: a quote is a true match if at least 80% of its words, in the original language, are present in the source page text. Is that right? (b) For CJK/Thai, count words as characters or as tokenizer words? (c) Tuning/held-out split: name it, or leave it open. (The card said a 20% hold-out was approved on 2026-11-02; the 2026-11-02 HANDOFF says "Holdout allocation has not been approved", and no approval was found.)
2. P1: which label is gold: (a) the 80% rule, with jev 1-5 as a cross-check; (b) jev, with the rule as a feature; (c) both must agree. Does the blind 30-pair PI check still happen?
3. P4 "skip": T-040/T-041 accept against agent labels plus P1 jev scores, with the PI ruling only on fixture failures?
4. S7 "yes" gave no dates: give the new window's dates, or leave it open until the 2026-12-01 check (P11)?
5-10. Procedural defaults: S5 recorded as "keep the Haiku legs"; S6 closes T-016 with the gap recorded; S3 wording approval stays a pre-merge gate, packaged once before T-030; P1 jev cost estimate about $0.25-0.35 with a $1 cap, given as a `!` line; P11 a startup pin; the other rulings as ruled.

## Simone's reply, verbatim

> 1 a, 2 4+ on jev and/or 80%+ -- if 80% does not correlate strongly with jev then we revisit it; 3 yes replace with agent + jev; 4 open; procedural accepted

## Integrator's reading (for review)

- 1 a: the 80% original-language word-presence rule is confirmed as stated. 1(b) (CJK/Thai counting unit) and 1(c) (tuning/held-out split) were not answered and stay open.
- 2: a quote pair is labelled a true match when jev scores it 4 or 5 on the 1-5 fidelity scale, or when the 80% rule holds ("and/or" read as inclusive or). If the 80% rule does not correlate strongly with jev scores, the rule is revisited. Whether the blind 30-pair PI check still runs was not answered and stays open.
- 3: T-040 real-page fixture expected values are labelled by an agent and scored by jev instead of by the PI.
- 4: the new display window stays open (no dates). It is decided at the 2026-12-01 check (P11).
- Procedural 5-10 accepted as listed.
