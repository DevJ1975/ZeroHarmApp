# OTIS knowledge base: OSHA General Industry review

**Content:** `backend/talks/migrations/0009_seed_osha_general_industry.py` (40 entries: 1 scope note, 39 rule summaries)
**Source text:** eCFR, 29 CFR Part 1910 and Part 1904, current as of 2026-11-06
**Review standard:** Certified Safety Professional review of frontline safety content (heavy industry and manufacturing, OSHA General Industry)

## What this is

- **Type:** Reference content, not compliance training. Nothing here certifies anyone. OTIS is the Zero Harm on-device
  assistant: it keyword-searches these passages and a small language model (Qwen3 0.6B or 1.7B) writes an answer of up to five
  sentences with a citation.
- **Where it plays:** As text on a phone, often read once on a dock or line. The model may quote **only the first sentences** of
  an entry, so the action has to come first and each entry has to be correct on its own.
- **Legal perimeter:** No legal or medical advice beyond calling 911. No performance figures (rates, counts, trends). No named
  employees or real incidents. Federal rules only: state plans such as Nevada OSHA can be stricter, and the scope entry says so.

## Verdict

The most serious risk in the first draft was **teaching the wrong action in the urgent case**. The fire extinguisher entry told
everyone to fight a small fire, but OSHA lets a site choose an evacuate-only plan, and at those sites that advice puts someone in
front of a fire their employer never trained them for. The draft glove entry carried the same class of risk: correct about choosing
a glove, silent about taking it off at rotating equipment. Both are fixed. Every number and rule statement was then checked
word-for-word against the current eCFR text, and the lockout entries now follow the order of 1910.147(d) and (e) instead of a
loose summary. The remaining open items need people, not code: a Nevada-specific pass and an approved Spanish translation of the
highest-risk entries.

## MUST FIX (all applied)

| # | Entry | Finding | Applied wording |
|---|---|---|---|
| 1 | Portable fire extinguishers | Told everyone to fight small fires. Wrong at evacuate-only sites, which 1910.157 allows. | "If your site's plan is to evacuate, pull the alarm and get out: do not fight the fire. Use an extinguisher only if your site has trained you and expects you to, the fire is small, and your way out is clear behind you." |
| 2 | Gloves, and when not to wear them | A glove-selection entry with no warning teaches a *swap* at rotating equipment, where the safe answer is *removal*. | Leads with: "Around rotating parts, such as drill presses, lathes, spindles, rollers and shafts, a glove can be caught and pull your hand in. Follow your site's procedure for that machine. It often means no gloves, no rings, no loose sleeves and hair tied back while the part is turning." That is site guidance, worded as such: 1910.138 itself covers only selection. |
| 3 | Lockout/tagout: the steps | Step 6 stated "try the start controls, test, then return them to off" as if it were the rule. 1910.147(d)(6) only requires verification. The site procedure sets the method. | "6. Verify isolation before you start work, for example by trying the normal start controls, then returning them to off." Opening line: "Never put any part of your body into a machine until it is locked out and you have proven it is dead." |
| 4 | Lockout/tagout: whose lock comes off | Restart checks were paraphrased loosely ("area is clear, tools removed"). Energy isolation content is not cleared from a summary. | Now follows 1910.147(e)(1)–(3): nonessential items removed, components intact, employees safely positioned or removed, affected employees told after the locks come off and before the start. The removal exception lists all three elements of (e)(3). |
| 5 | Permit-required confined spaces | The urgent case has to come first: untrained would-be rescuers are a classic way a single fatality becomes several. | "If someone collapses inside, do not go in after them. Call for the trained rescue team and 911." Placed in the first two sentences. |
| 6 | Emergency action plan | "At least:" followed by five of the six required elements implied a complete minimum. | Lists all six elements of 1910.38(c), including who to ask about the plan. |
| 7 | Reporting a death or serious injury to OSHA | "The clock starts when the employer learns of it" overstated 1904.39(a). The 8 and 24 hours run from the event, or from when the employer learns of it if that is later. | "If the employer learns of it later, the clock starts then." Entry opens with "If someone is hurt, call 911 first." |

## SHOULD FIX

| # | Where | Finding | Proposed wording or action |
|---|---|---|---|
| 1 | All entries, Spanish answers | Entries are English. A 0.6B model translating "never remove someone else's lock" on the fly can get it wrong. | **Needs a human translator.** Add reviewed Spanish entries (`lang: es` passages) for: Lockout/tagout (both), Permit-required confined spaces, Reporting to OSHA, Forklift (all three), Fall protection, Chemical labels and SDS, Exit doors. The Spanish tags already route Spanish questions to the right English entry in the meantime. |
| 2 | Scope entry and all rule entries | Federal text only. Nevada OSHA (a state plan) has its own requirements, such as its heat illness rules, which matter for Las Vegas sites. | **Needs a Nevada OSHA review** before marketing OTIS as covering Nevada. Then add entries citing NAC/NRS sections, with source labels like "Nevada OSHA". |
| 3 | Chemical labels and SDS | 1910.1200 was amended in 2024 with phased deadlines (substances by May 19, 2026, with later dates for mixtures). The entry stays at a level that doesn't change, but an industrial hygienist should confirm before the next HazCom talk. | No wording change. Recheck after the final 2027 compliance date. |
| 4 | First aid and eyewash | Flushing time (commonly 15 minutes) comes from ANSI Z358.1 and the SDS, not from 1910.151, so it is left out deliberately. | If you want it, add as a separate entry sourced to the SDS and your site procedure, not to OSHA. |

## CONSIDER

- **Noise:** "If you have to raise your voice to be heard an arm's length away" is a field rule of thumb, not rule text. It is
  worded as a prompt to ask, not as a measurement.
- **Overhead cranes:** The entry gives only the daily and monthly items. If cranes matter at your sites, add an entry per
  inspection list from 1910.179(j)(2)–(3).
- **Recordkeeping:** Two Part 1904 entries are included because the app's TRIR/DART calculator points people toward the 300 log.
  More Part 1904 entries (privacy cases, 300A posting from Feb 1 to Apr 30) would round this out.

## Assessment items

None. OTIS has no quiz, so there are no keyed answers to defend.

## Perimeter check

- Every number is a regulatory value from the cited section: heights, distances, decibels, psi, gallons, hours, µg/m³. There are
  no rates, counts, trends or "days since" figures.
- No named people, incidents or sites, and no readable asset identifiers.
- No claim about what happens to someone after they report.

## Keep untouched

These lines will change behavior, so don't soften them in editing:

- "Never put any part of your body into a machine until it is locked out and you have proven it is dead."
- "Never remove someone else's lock."
- "If someone collapses inside, do not go in after them."
- "Stand out of the path of the load, because a failed sling or load does not go where you expect." (It says stand clear, not
  "predict where it goes".)
- "Do not step past a missing guardrail or an uncovered hole. Stop and tell your supervisor."
- "If an exit is locked, chained or blocked, report it to your supervisor now and do not work around it."
- "If you have not been trained on the harness or lanyard you were handed, do not use it yet."

## Verification record

Every rule statement was matched against the eCFR text (2026-11-06) before it was written:

| Entry | Sections checked |
|---|---|
| Reporting to OSHA; recordable cases | 1904.39(a)(1)–(2), (a)(7)–(8); 1904.7(a) |
| Emergency action plan; fire prevention plan | 1910.38(b)–(c); 1910.39(b)–(c) |
| Exit doors and routes | 1910.36(d)(1); 1910.37(a)(3) |
| Fire extinguishers | 1910.157(e)(2)–(3), (g)(1)–(2) |
| First aid and eyewash | 1910.151(b)–(c) |
| Floors and housekeeping | 1910.22(a), (d) |
| Ladders; fixed ladders | 1910.23(b)(8)–(13), (c)(11)–(12); 1910.28(b)(9) |
| Fall protection; guardrails; training | 1910.28(b)(1), (b)(3), (b)(4); 1910.29(b)(1)–(3); 1910.30(a) |
| PPE: assessment, payment, training | 1910.132(d)(2), (e), (f)(1)–(3), (h)(1)–(2) |
| Eye and face; hands | 1910.133(a)(1)–(3); 1910.138(a)–(b) |
| Noise | 1910.95 Table G-16, (c)(1)–(2), (d)(1), (g)(5)–(6) |
| Respirators | 1910.134(c)(1), (c)(4), (f)(2), (g)(1)(i) |
| Lockout/tagout | 1910.147(c)(6)(i), (d)(1)–(6), (e)(1)–(3) |
| Confined spaces | 1910.146(b), (c)(2), (d)(5)(iii), (i)(4); hazardous atmosphere definition |
| Machine guarding; grinders; compressed air | 1910.212(a)(1)–(3), (b); 1910.215(a)(4), (b)(9), (d)(1); 1910.242(b) |
| Forklifts | 1910.178(l)(4), (m)(5)–(6), (p)(1), (q)(7) |
| Slings; cranes | 1910.184(c)(4), (c)(13)–(14), (d); 1910.179(j)(1)–(2) |
| Electrical | 1910.303(g)(1) and Table S-1; 1910.305(g)(1)(iv), (g)(2)(iii); 1910.333(a)(1)–(2) |
| HazCom; flammables; cylinders | 1910.1200(f)(6), (g)(8), (h)(1); 1910.106(d)(3)(i); 1910.253(b)(2)(ii), (b)(4)(iii) |
| Bloodborne pathogens; silica | 1910.1030(b), (c)(1), (d)(1), (f)(2)(i); 1910.1053(a)(2), (b), (c) |
| Signs and tags | 1910.145(c)(1)–(2), (d)(2), (d)(4), (f) recommended tag colors |

Retrieval was spot-checked with the app's own BM25 search: lock removal, gloves at a lathe, guardrail height, parking a
forklift, reporting an amputation, a 5-foot platform, compressed air on clothing, lockout steps, a fit-test interval, and two
Spanish questions (lock removal, SDS location). Each one returned the right entry first.
