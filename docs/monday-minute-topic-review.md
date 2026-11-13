# Monday Minute topic bank: CSP review record

**Content:** `backend/monday/topics.json` (104 topic briefs, loaded by migration `monday/0002`)
**Source text:** eCFR, 29 CFR Parts 1910 and 1904, current as of 2026-11-06
**Why this review matters:** Monday Minute publishes with no person approving each talk. The AI writer may use only one
brief, so the bank is the safety review that happens before anything is written. Each weekly draft is also checked
automatically (hard rules plus a CSP-role AI review) before it publishes. See `backend/monday/generate.py`.

## How the bank was built
1. 104 topics were chosen to cover General Industry hazards with no overlap: hazardous energy, machines, falls,
   walking surfaces, forklifts, material handling, electrical, PPE, chemicals, emergencies, recordkeeping, health,
   confined spaces, tools and culture.
2. Each brief was written to a fixed spec and checked by a script. Every cited section must exist in the eCFR text, and
   every number in a fact must appear in that section. Numbers in actions must be backed by a fact (911 excepted).
3. Two reviewers in the Certified Safety Professional role reviewed 52 briefs each against the regulation text and the
   CSP review standard. All MUST FIX and SHOULD FIX items were applied (46 briefs changed), and the script check was re-run.
4. One more change after review: `stop-work` no longer states that anyone at any site can stop work, which is a policy
   claim not every site makes. Its required line is now "If something looks unsafe, stop first, then talk." It also
   tells crews to ask who can stop a job at their site.

## Open items for people (not code)
- **Lawyer / HR:** state-plan reporting deadlines differ from federal (the OSHA-reporting topic is labeled federal);
  medical privacy around telling a supervisor about medicines (impairment); how near-miss retraining is described.
- **Industrial hygienist:** noise survey areas at or above 85 dBA, respirator cartridge change schedules, CO monitoring
  for indoor forklifts, hydrofluoric acid first aid where it's used.
- **Site written procedures:** alternative measures for specific jams, try-out method, propane cylinder changes,
  eyewash flush time, stop-work program, bloodborne exposure control plan.
- **Spanish:** Monday Minute is English only. Translating safety talks needs a reviewed translation, not machine output.

---

## CSP review: Monday Minute bank A (52 briefs)

Reviewed as culture and communication content (a toolbox talk read aloud by a supervisor, not certifying training). The briefs are the only source an AI writer uses, and the talks publish with no human review. So I judged every line as if the writer will quote it alone. Corrected file: `reviewed_A.json`. Verifier result: `OK: 52 briefs`.

### Verdict

The bank is sound. The facts check out against the eCFR text. I checked every number, and nearly every paraphrase holds up at the section level. The classic traps are handled well: gloves off at rotating parts, "stay out of the path" for suspended loads, no rescuing someone from electrical contact. The perimeter is clean too: no statistics, no names, no injury counts.

**The most serious finding is in `jam-clearing`.** Its first fact paraphrases the 1910.147 minor-servicing exception ("routine, repetitive, integral... outside the lockout standard"). That fact hands the writer a legal reason why routine jams do not need lockout. The same brief's must_say says "stop it and lock it out." Read aloud to a crew, that exception becomes the rationalization behind most jam-clearing amputations. I removed it.

The other MUST FIX items follow the same pattern: a line that is right with its qualifier, but dangerous when the writer drops it.
- "Never jump, stay in" reaching stand-up forklift drivers.
- A skylight that you may step on "if rated".
- Safety glasses under a face shield for chemical splash.
- Eye flushing with no instruction to keep flushing.
- Unqualified workers testing for voltage.
- Lockout taught to every worker without "authorized only".

### MUST FIX: wrong, unsafe, or creates exposure (8)

| # | Slug | Field | Finding | Applied replacement wording |
|---|---|---|---|---|
| 1 | jam-clearing | facts[0]; key_points[2] | The fact paraphrases the 1910.147(a)(2)(ii) minor-servicing exception. It gives the writer a reason to say routine jams are exempt from lockout, which contradicts the must_say and never_say. The old KP3 ("approved tool or method") can be read as an alternative to lockout. | Fact **removed**. The fact that stays: lockout applies when a worker removes or bypasses a guard or puts any part of the body in a danger zone. KP3: "Use only the clearing tool your site's procedure names for that machine, and only after it is locked out." **Needs the site's written procedure:** if the site uses approved alternative measures for specific jams, this talk will be stricter than its program. That is the safe direction, but the site should confirm it. |
| 2 | forklift-loads | key_points[5]; never_say[1] | "Never jump: stay in" is correct for sit-down counterbalance trucks. On stand-up rear-entry trucks the trained action is usually to step off backward. The writer can easily drop "sit-down". | KP: "On a sit-down truck, wear your seatbelt; if it tips, never jump: stay in, hold on, lean away. Stand-up trucks: follow your training." New never_say: "Every kind of forklift uses the same move to escape a tip-over." (This replaces "Adding extra weight to the back lets you lift more". The capacity-plate KP already covers that point.) |
| 3 | floor-holes | key_points[0] | "Never step on a skylight or a cover unless you know it is rated to hold you" teaches that a skylight can be walked on once it is "rated". People fall through skylights. A skylight is never a walking surface. | "Never step, sit or lean on a skylight, even one with a screen, and never step on a cover you are not sure is secured." |
| 4 | eye-protection | key_points[2] | "Goggles or a face shield over glasses... like chemicals" teaches glasses plus a face shield for chemical splash. Splash runs under a shield and around glasses. Goggles are the eye protection for chemical splash. | "Wear goggles for chemical splash, and add a face shield over your glasses or goggles when the task or your site calls for it." |
| 4b | face-shields | key_points[1] | Same issue. "Over safety glasses or goggles" leaves glasses as an option for chemical splash. | "Wear a face shield only over safety glasses or goggles, and wear goggles under it for chemical splash." |
| 5 | eye-protection, face-shields, battery-charging | eye KP[0] and must_say[0]; face KP[0]; battery KP[0] | The urgent chemical-in-eye action says "flush" with no duration and no "keep going". Crews flush for seconds and stop. No number is allowed here (none is backed by a fact), so the fix is behavioural. | Eye KP: "If a chemical splashes in your eye, get to the eyewash, hold your eyes open, call for help, and keep flushing until help says stop." Eye must_say: "If something splashes in your eyes, get to the eyewash, keep flushing, and call for help." Face-shield KP: "...go to the eyewash or shower now, call for help, and keep flushing until help says stop." Battery KP: "If acid hits your eyes or skin, flush at the eyewash or shower now, call for help, and keep flushing until help says stop." **Industrial hygienist / SDS:** the site should post its flush duration at each eyewash. |
| 6 | loto-try-out | key_points[2] | "Test for voltage... using the right meter and training" invites any worker to test live circuits. Testing for voltage is qualified-person work under 1910.333. | "Have a qualified person test for voltage where your site's procedure calls for it. Never test for voltage unless you are qualified." |
| 7 | loto-try-out | must_say[0] | "Before you touch it, try to start it" is quoted word for word, and it has no clear-the-area step. A try-out with someone inside the machine is the injury. The Appendix A sample procedure starts by checking that no one is exposed. | "Clear everyone, then try to start it before you touch it. If anything moves, stop and get help." |
| 8 | loto-six-steps | key_points[0], [2], [4] | The six steps are taught to every worker with no "authorized only". There is no step to tell affected people (1910.147(c)(9)), and the try-out has no clear-the-area step. | KP1: "Know every energy source the machine has, and tell the people who run or work near it before you shut it down." KP3: "Lock out only if you are trained and authorized, and put your own lock and tag on each energy isolating device." KP5: "Make sure everyone is clear, then try the normal start controls to prove it will not run, and return them to off." |

### SHOULD FIX: weakens the training (13)

| # | Slug | Field | Finding | Applied replacement wording |
|---|---|---|---|---|
| 1 | loto-group-shift | story_seed | The story has an electrician "still inside the guard" protected only by other people's locks. That models the exact mistake the brief says not to make. | "During a long repair, an off-going tech pulled their lock from the group box before the oncoming crew put theirs on. An oncoming mechanic was about to reach into the open guard when a coworker saw the empty box and stopped them." |
| 2 | rotating-entanglement | key_points[2], [4] | The never_say refers to a cap but no KP mentions one. Badge lanyards and strings are missing. The KP does not say to wait for the machine to stop turning (chips and measuring are the story's own scenario). | KP3: "Tie long hair back and tuck it under a cap, button or roll sleeves tight, and tuck in badge lanyards and loose strings." KP5: "Never reach near a spinning part; stop the machine and wait until it stops turning before you brush chips, measure or adjust." |
| 3 | bench-grinders | key_points[3], [4] | The ring test and speed check are taught as operator tasks. Mounting a wheel is trained work, and most operators should never mount one. | KP4: "Let only trained people mount wheels; they inspect and ring test each wheel first. Never use a cracked or chipped wheel." KP5: "Never use a wheel whose marked speed is lower than the grinder's speed; report it instead." |
| 4 | conveyors | key_points[0] | SPEC rule 3: the urgent case (someone caught) was not stated. The brief only said to know where the stops are. | "If someone gets caught, hit the nearest emergency stop or pull cord and shout for help. Know where they are and keep them clear." |
| 5 | spill-cleanup | key_points (order) | KP1 told workers to "stop and guard" any spill, including a fuming chemical, before they hear the line about reporting a chemical spill. The urgent case has to come first. | New KP1: "If a spill is a chemical, unknown, large, or gives off fumes, move away, keep others back, and tell your supervisor right away." KP2: "Guard any spill you can safely stand near so no one walks through it." (The old "Report chemical, unknown or large spills" KP is folded into KP1.) |
| 6 | housekeeping, slips-trips | housekeeping KP[0] and must_say; slips KP[1] and must_say | "Clean it up" as a default action, quoted word for word, teaches people to wipe up unknown liquids. It is inconsistent with spill-cleanup. | Housekeeping KP1: "Clean up a small spill right away only if you know what it is and it is safe; otherwise block it off and report it." Housekeeping must_say: "If you see a spill, block it off and report it. Clean it only if you know it is safe." Slips KP2: "Guard and report spills as soon as you see them, and clean them up only if you know they are safe to handle." Slips must_say: "If you see a spill or trip hazard, guard it and report it. Never walk past it." |
| 7 | battery-charging | key_points[1] | In the propane-leak action, "keep flames and sparks away" came before "move away". It can read as staying to manage ignition sources. It also left out "do not start anything". | "If you smell propane or hear a hiss, move away, keep others back, do not start or switch anything on, and report it." |
| 8 | winter-walkways | story_seed | It described an actual fall with impact ("landing hard on their hands"). SPEC asks for a close call. | "On an early shift, a worker started to cut across the parking lot instead of using the salted walk. Their foot slid on black ice, and they grabbed a car mirror, then went back to the cleared path." |
| 9 | forklift-training | key_points[3]; facts[1] | Perimeter. "Ask for refresher training after a near miss", plus a fact listing "accident or near miss" as a retraining trigger, lets the writer say "if you have a near miss, you'll be retrained". That is a claim about what happens to a person after an event, and it discourages reporting. | KP4: "Ask for refresher training when you get a new truck type or attachment, or when your work area changes." Fact: "Refresher training is required in several cases, including when an operator is assigned to a different type of truck or a change in the workplace affects safe driving." **Lawyer / HR:** confirm how the site wants near-miss retraining described, if at all. |
| 10 | wet-locations | key_points[3] | "GFCI where your site requires it" makes ground-fault protection sound optional in wet areas. | "Use only tools and cords approved for wet areas, plugged into ground-fault protection (GFCI) as your site's procedure says." |
| 11 | noise-exposure | facts[0] | The PEL fact ("90 decibels for 8 hours is allowed") sits next to two 85 dB facts. A writer will likely tell crews 90 is "the legal limit", which undercuts the brief's must_say. | "The louder the noise, the shorter the time a worker may be exposed. When noise is over the limits, the employer must use feasible engineering or work-practice controls, and hearing protection when those are not enough." (cite 1910.95(b)). **Industrial hygienist:** only a noise survey tells a crew whether their area is in the hearing conservation program. |
| 12 | overhead-cranes, battery-charging, hearing-protection, forklift-training | facts[].cite | Paragraph-level cites pointed at the wrong paragraph. Rated-load marking is 1910.179(b)(5), not (n)(1). Smoking, flames and tools are (g)(10) to (g)(12). The fuel-tank rule is (p)(2), not (g)(8). Fitting and supervision are (i)(5). The trainee rule is (l)(2). | Cites changed to section or paragraph level that is true: `1910.179`, `1910.178(g)`, `1910.178`, `1910.95(i)`, `1910.178(l)`. The fact text was unchanged except for crane wording. |
| 13 | ppe-hazard-assessment | title | SPEC rule 7: the title used "PPE" before spelling it out. | "Why your protective gear (PPE) was chosen" |

### CONSIDER

- **portable-ladder-setup:** add a never_say along the lines of "Aluminum ladders are fine near wires or panels." 1910.333(c)(7) requires nonconductive side rails where the ladder could contact energized parts.
- **aerial-lifts:** all three facts apply only to vehicle-mounted boom lifts (the writer's note is correct). The writer may apply them to scissor lifts. Think about a KP: "In a scissor lift, keep the gate or chain closed and follow your site's tie-off rule." The brief also does not mention being crushed against overhead structure in a boom lift. The power-line minimum distance is correctly deferred to the site.
- **pallet-jacks:** powered pallet jacks are powered industrial trucks under 1910.178, so training applies. The tsv gives no refs, so I did not add one. Think about adding 1910.178 to the topic.
- **stored-energy:** capacitors appear in a worker action list. Think about "only qualified people discharge capacitors."
- **respirator-fit** must_say: "If it leaks, leave the area" could be "If it leaks, do not go in, or get out."
- **winter-walkways:** ice cleats are a slip hazard on smooth indoor floors. Add "take cleats off indoors" if the site issues them.
- **dock-edges:** think about checking trailer landing gear or a jack stand on dropped trailers.
- **face-shields** facts[1] (manufacturer marking) is accurate but teaches nothing. Think about swapping it.
- **Format:** several KPs start with "If", "On", "In" or "Drivers:" rather than a verb. The "If" openers are the urgent case (SPEC rule 3) and are worth keeping. Only "Drivers:" (forklift-pedestrians) and "In a boom lift" (aerial-lifts) are pure style.

### Flags for specialists and site documents

- **Site written procedure:** jam-clearing (whether the site uses alternative measures for minor servicing), every LOTO brief, try-out method, propane cylinder change, washdown lockout, aerial-lift approach distances, eyewash flush duration.
- **Industrial hygienist:** noise-exposure and hearing-protection (which areas are actually at 85 dBA or above), respirator-fit (cartridge change schedule and medical clearance are program items the brief correctly defers).
- **Labour lawyer / HR:** forklift-training near-miss and retraining wording (SHOULD 9).
- **Energy-isolation sources:** the LOTO facts were checked against the full 1910.147 text in secs.json, including Appendix A for the try-out, not a summary. They are cleared.

### Keep untouched: these will change behaviour

- **loto-six-steps / loto-group-shift:** "Never remove someone else's lock." "Your own lock protects you." The shift-change KP (oncoming locks go on before off-going locks come off) is the single most useful line in the hazardous-energy set.
- **stored-energy:** "never rely on hydraulics alone to hold them up" and "Locking the switch is not enough."
- **rotating-entanglement** must_say (gloves and jewelry off, hair back) and the never_say "A tighter or tougher glove makes it safe." This is removal, not a swap. It is exactly right.
- **suspended-loads:** "Stay out of the path the load will travel and out of the area where it could fall or swing," plus the never_say "If you know where the load is going, you can stand close to it." This is line of fire done correctly.
- **fixed-ladders:** "Never count on a cage to catch you."
- **qualified-electrical / wet-locations / arc-flash:** the urgent case comes first. "Do not touch them; shut off power if you safely can and call 911."
- **personal-fall-arrest:** the rescue KP comes first, and a harness that has caught a fall is taken out of service.
- **forklift-pedestrians:** the never_say items "A backup alarm means the driver sees you" and "A bright vest means drivers will always see you."
- **respirator-fit:** "If you can't smell anything, the cartridge is still good" as a never_say.
- **guard-bypass** must_say, and **machine-guarding**: "push sticks only as extra protection, never instead of a guard" (accurate to 1910.212(a)(3)(iii)).
- Every crew_questions pair. They are about the crew's own site and will start real conversations.


---

## CSP review: Monday Minute bank B (52 briefs)

Reviewer stance: CSP, general industry. Content type: culture/communication toolbox talks, read aloud by a supervisor, not certifying training. **Each brief is the only source for an AI writer that publishes with no human review.** That raises the bar: anything wrong in a brief gets taught. Perimeter: no statistics, no names, no claims about what happens to someone after they report, no legal advice. Corrected file: `reviewed_B.json` (verifier: `OK: 52 briefs`).

### Verdict

The bank is mostly sound. Every cited fact was checked against the eCFR text (2026-11-06) and none of the numbers is invented. The heat set is correct: 911, cool them now, no federal standard. The confined-space attendant and rescue briefs are strong. **Do not publish bank B as written.** The most serious finding is the **line-of-fire must_say** ("don't be where it will go"). It will be read word for word and teaches the exact predict-the-path trap the spec bans. Six other MUST FIX items follow close behind:
- the SDS brief tells crews to read the first-aid section before they start first aid on a splash
- the permit-space brief never states the urgent "don't go in after them" action
- two stories model "shut it down" where the machine needs to be locked out (new-workers, shift-handoff)
- two items break the perimeter by promising outcomes after a report (report-every-injury must_say, bloodborne post-exposure fact)

All 7 MUST FIX and 18 SHOULD FIX items are applied in reviewed_B.json.

Note on the verifier: it only checks that each digit in a fact appears *somewhere* in the cited section. It does not check meaning. The checks below were done by reading the cited paragraphs.

### MUST FIX (7) — wrong, unsafe, or creates exposure

| # | slug | field | finding | applied replacement |
|---|---|---|---|---|
| 1 | line-of-fire | must_say[0] | "If something can move, fall, or release, don't be where it will go" is the predictive trap. It teaches people to stand just outside their own guess. It appears word for word. | "Stay out of the path. Things that move, fall, or snap do not go where you expect." |
| 2 | sds | key_points[1] (now [0]), crew_questions[1], story_seed | "Check the first-aid section right away if someone is exposed" and "Which section of the SDS would you check first if someone got splashed?" put reading ahead of flushing. With a corrosive in the eye, that delay costs tissue. The story also showed no first aid. | KP moved to first: "Help an exposed person first: flush at the eyewash or get them to fresh air, call for help, then check the safety data sheet." Q: "If someone got splashed, what would you do first, and who would pull up the safety data sheet?" Story: the worker "flushed it at the eyewash right away, but no one on the crew knew where the safety data sheets were kept…" |
| 3 | permit-spaces | key_points, must_say | The urgent case (a coworker collapses inside) shows up only as a never_say line. The positive action is never stated, and an unstated action is an untaught one. "Never enter a space **marked** as a permit space" also suggests that unmarked spaces are fine. | New KP[0]: "Never go in after someone who collapses inside a confined space; call trained rescue and 911." KP: "Never enter a permit space unless you are trained, authorized, and the entry permit is complete." KP: "Learn which spaces at your site are permit spaces; if a tank, pit, or bin is not marked, ask before entering." Added must_say: "If someone collapses inside, do not go in. Call trained rescue and 911." |
| 4 | new-workers | story_seed | The veteran "showed him how to shut it down the right way" before reaching into a conveyor jam. That models shutdown as the control for putting a hand in. This is a caught-in fatality pattern and it conflicts with 1910.147. | "…showed him how to lock it out the way the site's procedure says before clearing it." |
| 5 | shift-handoff | story_seed, key_points, facts | In the story a guard-off machine is "kept shut down", again with no lockout. The KP says to tell the next shift about "locked-out equipment" but gives no rule on lock transfer. The writer could invent "remove your lock and the next shift adds theirs", which is the gap 1910.147(f)(4) exists to close. | Story: "…made sure the machine stayed locked out until the guard was back on." New KP: "Follow your site's lockout procedure at shift change; never remove another person's lock." New fact (1910.147(f)(4)): "Lockout programs must use specific procedures at shift or personnel changes so lockout protection continues, including an orderly transfer of locks or tags between off-going and oncoming workers." references: ["1910.147"]. |
| 6 | report-every-injury | must_say[0] | "…without being punished for it" promises what happens after a report, which is a perimeter breach. It is also not something the site can guarantee, because discipline for a separate rule violation is still lawful. | "Report every work injury or illness to your supervisor right away, even if it seems small." The anti-retaliation rule stays as an attributed fact: "Federal rules say employees have the right to report … and employers must not fire or in any way discriminate against employees for reporting." (1904.35) |
| 7 | bloodborne | facts[2] | "After a reported exposure incident, the employer must make a confidential medical evaluation and follow-up immediately available" has two problems. (a) It is a claim about what happens after reporting (perimeter). (b) It overstates scope: 1910.1030 covers only *occupational exposure*, meaning contact expected as part of a person's duties, such as designated first aiders. A crew member who helps a cut coworker as a Good Samaritan is generally not covered, so the talk would promise something the site may not owe. | Fact removed. The KPs (report right away, wash, gloves, leave cleanup to trained staff) stand without it. **Flag: site's Exposure Control Plan / lawyer**, if the site wants to say what follow-up it offers. |

### SHOULD FIX (18) — weakens the training

| # | slug | field | finding | applied replacement |
|---|---|---|---|---|
| 1 | carbon-monoxide | key_points[0], new KP, story_seed | The KPs set different 911 thresholds: "call 911 if very sick" in the KP against "dizzy or confused → 911" in the must_say. Neither says to shut off the engine. There is no warning against entering a closed trailer after a collapsed person, which risks a second victim. In the story the crew stays in place and only opens doors, with no fresh air and no medical check. | KP: "Shut off engines and get anyone with headache, dizziness, or confusion to fresh air; call 911 if anyone is confused, very sick, or passes out." Added KP: "Never go into a closed trailer or room where someone collapsed near a running engine; call 911." Story: "…the truck was shut off, everyone went outside to fresh air and got checked, and the truck was sent for maintenance." |
| 2 | eyewash | key_points[1], must_say | No flush duration, and none can be given (no 1910 number). "Keep flushing as your site's procedure… say" still leaves room for "a quick rinse". The must_say "flush. Then get medical help" implies you stop flushing to go get help. | KP: "Hold your eyelids open and keep flushing until medical help or your site's procedure says to stop. Do not stop early." MS: "If it splashes in your eyes, get to the eyewash now and keep flushing. Have someone call for medical help." |
| 3 | corrosives | key_points[0], must_say | Same flush-then-leave problem. | KP: "Flush right away at the eyewash or shower if you are splashed, keep flushing, and have someone call for medical help." MS: "If you are splashed, flush with water right away and keep flushing. Have someone call for medical help." |
| 4 | gas-cylinders | must_say, facts[2], story_seed | The must_say leaves out removing the regulator. 1910.253(b)(5)(ii)(D) says regulators off and caps on before moving, unless the cylinder is secured on a special carrier. In the story the oxygen cylinder is capped next to fuel gas and left there, which contradicts the 20 ft separation fact in the same brief. | MS: "Before moving a cylinder, remove the regulator and cap the valve, unless it is secured on a cylinder cart." The 1910.101 fact is replaced with: "Unless cylinders are secured on a special cart made for them, regulators must be removed and valve caps put in place before cylinders are moved." (1910.253). Story: the worker chained and capped it "and told the lead it needed to be moved away from the fuel gas." |
| 5 | glove-selection | key_points[0], story_seed | It says gloves off but not rings, loose sleeves and hair, so half the entanglement removal message is missing. The story has a worker "cleaning a chemical tank", which may be a permit-space entry. | KP: "Take off gloves and rings, secure loose sleeves, and tie back long hair before working near drills, lathes, or other rotating parts." Story: "…before pouring a cleaning chemical…" |
| 6 | first-aid | key_points[1] | "Make sure the area is safe" is abstract. It invites the writer to describe a self-rescue from electrical contact or a confined space (spec trap #4). | "Check the area is safe first; never touch someone in contact with electricity or enter a confined space after them. Call 911." |
| 7 | hydration | must_say | The must_say has 911 but not cooling. Heat stroke = 911 **and** cool them now. | "Drink water often and rest in shade. If someone is confused in the heat, call 911 and cool them now." |
| 8 | silica | facts[2] | "Action level" is used with no definition. The writer will either explain it vaguely or make up a number. | "Employers must offer medical exams at no cost to workers exposed at or above the action level of 25 micrograms per cubic meter of air (8-hour average) for 30 or more days per year." (1910.1053(b), (i)(1)(i)) |
| 9 | osha-reporting | facts | The facts state federal deadlines as universal. State-plan states can differ; Cal/OSHA, for example, sets a shorter window for serious injuries. The hospitalization, amputation or eye-loss trigger leaves out the "within 24 hours of the incident" condition. The OSHA phone and web fact is not something crews act on (KP: follow the site procedure for who reports), and it may change. | Facts now read "Under federal OSHA rules, …" and the second adds "if it happens within 24 hours of the incident." Phone/web fact removed. **Flag: lawyer/EHS**, for state-plan sites, before this talk runs there. |
| 10 | report-every-injury | facts[2], references | The 1904.7 recordability criteria pull the talk toward "what counts on the log". That works against "report everything" and invites talk of the team record, which is the performance-figure perimeter. | Fact and its 1904.7 reference removed. |
| 11 | fire-extinguishers | story_seed | The only story shows a worker fighting a fire, with no mention that they were trained and allowed to. Many sites are evacuate-only. Crews remember the story, not the KP. | "…The worker pulled the alarm first, then, because they were trained and their site allows it, used the nearby extinguisher with their back to the exit…" |
| 12 | fire-prevention | key_points[0] | The never_say bans "Oily rags can go in any trash can", but no KP says where they go. | "Clear away combustible waste like cardboard and dust, and put oily rags in the closed container your site provides." |
| 13 | exit-routes | key_points[3] | "Know at least two ways out" puts a number in a key point with no fact behind it (rule 2). Also, not every area legally has two exit routes (1910.36(b) has exceptions). | "Know every way out of your work area, not just the door you usually use." |
| 14 | speak-up | key_points[0] | The urgent case lacks its action. "Speak up right away" sits next to "Tell the person directly and kindly", so the writer may blend the two. When something is about to happen, skip the wording and say stop. | "Shout 'Stop!' first if someone is about to get hurt; skip the polite words and explain after." |
| 15 | atmospheric-testing | key_points[1], [4], facts[0] | "Test the air in order" tells entrants to run the meter. Testing is for a trained tester. "You have that right" is stated as a legal right with no fact behind it. | KP: "Make sure the air is tested in order by a trained tester: oxygen first, then flammable gases, then toxic gases." KP: "Ask to watch the air testing; entrants must be given the chance to see it." Fact (1910.146(d)(5)(i),(iv)): "Before entry, the permit space must be tested to see if conditions are acceptable, and each entrant must be given the chance to watch the testing." |
| 16 | fatigue | story_seed | The story ends with what happens to the person after they report ("moved him to a different task"), which is the perimeter. | "…He parked the truck and told his lead he was too tired to drive safely." |
| 17 | impairment | story_seed | Same perimeter problem ("moved him off the forklift for the day"). It also implies a consequence that drug, alcohol and medicine policies set differently at each site. | "…He told his lead before he got on the forklift." |
| 18 | severe-weather | facts[0] | The fact paraphrases 1910.38(c)(2) as "procedures for emergencies"; the rule says "emergency evacuation". | "An emergency action plan must include procedures for emergency evacuation, including the type of evacuation and exit route assignments." |

### CONSIDER (not applied)

- **corrosives / eyewash**: Some chemicals need first aid beyond water, for example hydrofluoric acid (calcium gluconate). If any site uses HF, it needs its own brief. **Flag: industrial hygienist / site SDS.** Also consider adding "remove contact lenses if you can do it quickly" and "lead a splashed coworker; they may not be able to see."
- **carbon-monoxide**: The 50 ppm PEL fact may lead the writer to say "under 50 is safe". Symptoms should drive action, not a number. **Flag: industrial hygienist** for CO monitoring on indoor forklift fleets.
- **impairment**: "Tell your supervisor if a medicine makes you sleepy or dizzy" touches medical-privacy and disability rules, and cannabis policy varies by state. **Flag: lawyer/HR**, to confirm the wording matches policy.
- **stop-work**: The must_say "Anyone can stop work" asserts a program every subscribing site must actually have. **Flag: confirm each site has a written stop-work procedure**, or soften to "You can always call a stop if something is unsafe. Then tell your supervisor."
- **secondary-containers**: The must_say carries the immediate-use exemption word for word. "Label every container you pour a chemical into" is simpler and safer; the exemption can stay as a fact.
- **hot-work**: KP "keep watching after the work ends". The fact already gives "at least a half hour", so the KP could use it.
- **small-spills**: In the story the worker cleans a corrosive spill themselves. Add "they were trained for it and the spill was small".
- **heat-illness-signs / hydration**: Add "do not give drinks to someone who is confused or passed out".
- **cold-stress**: The story ends without medical attention for lost feeling in the fingers. "Gloves that fit the task" should not be read as permission near rotating parts.
- **severe-weather**: Months [3-6] miss summer lightning and fall hurricanes. Consider adding "stay away from windows" as a KP.
- **signs-tags**: The must_say "never remove a danger tag" should say who is allowed to: "Never remove a tag you did not hang unless your site's procedure says you may." "Do Not Use" in the story is not a 1910.145 signal word.
- **workplace-violence**: Story trigger "after a write-up" ties discipline to violence; consider a neutral trigger.
- **abrasive-cutoff**: Add "run a newly mounted wheel briefly while standing out of its path".
- **first-aid**: The gloves fact comes from the non-mandatory Appendix A, which points to 1910.1030(d)(3). It is accurate, but it could be labeled as appendix guidance.
- **foot-protection**: The story relies on the safety toe "holding". The ending (keep feet clear) is right, but consider a pure near-miss.

### Writer notes: judgment calls checked

All accepted except where noted. The respirator Appendix D wording, gloves-off-near-rotating-parts framed as practice rather than a rule, bump caps as practice only, cylinders "secure upright" deferred to the site, eyewash with no time given (the wording now blocks early stopping instead), and CO 50 ppm under 1910.1000 (a)(2) all match the text. Silica "action level without a number" was not accepted: it now gives 25 µg/m³. Bloodborne "hep B omitted for scope" is right, but the same scope logic means the post-exposure follow-up fact also had to go (MUST #7).

### Keep untouched: these will change behaviour

- **heat-illness-signs**: 911 + cool now as KP[0] and KP[1]; "Never leave a sick worker alone"; "stopped sweating ≠ fine" in never_say; story with soaking until help arrives.
- **confined-space-rescue** and **confined-space-attendant**: "Do not become the second victim", attendant never goes in, retrieval line from outside. These are the best briefs in the bank.
- **glove-selection must_say**: "Take them off, do not look for a better glove." Removal, not a swap.
- **fire-extinguishers**: "Sound the alarm first"; KP defers to evacuate-only plans.
- **evacuation-headcount**: "Never go back inside for anyone or anything. Tell responders who is missing."
- **compressed-air**: "Low-pressure air is safe to point at people" in never_say heads off misuse of the 30 psi fact.
- **contractors**: the crew question "What do we do if we find a contractor's lock and can't find the contractor?" is exactly the conversation that prevents an energization.
- **hazcom-labels**: "If there is no label, do not use it. Tell your supervisor."

