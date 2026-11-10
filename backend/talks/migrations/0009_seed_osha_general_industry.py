"""OTIS knowledge base: OSHA General Industry (29 CFR 1910) and recordkeeping (29 CFR 1904).

Checked against the eCFR text current as of 2026-11-06, then reviewed as frontline safety content (see
docs/otis-osha-kb-review.md). Each entry stands on its own, because OTIS retrieves a few passages and may quote only
the first sentences: the action comes first, the rule after. Edit or unpublish entries in the admin.
"""
from django.db import migrations

SCOPE = "Zero Harm app help"

ENTRIES = [
    # ---- How to read these ------------------------------------------------------------------------
    ("OSHA rules in OTIS: what they cover",
     "OTIS summarizes federal OSHA General Industry rules (29 CFR 1910) and injury recordkeeping rules (29 CFR 1904) in plain words, "
     "checked against the official text as of November 2026. They are the legal minimum, not the whole job. Your site's written "
     "procedures, your training and your state's rules come first. Nevada and many other states run their own OSHA plan, which can be "
     "stricter. A summary is not legal advice: for the exact wording, look up the section number at ecfr.gov or ask your safety lead.",
     SCOPE, "osha, rule, regulation, law, 1910, general industry, nevada, state plan, legal, reglamento, ley"),

    # ---- Emergencies, reporting and exits ---------------------------------------------------------
    ("Reporting a death or serious injury to OSHA",
     "If someone is hurt, call 911 first. After that, the employer must report to OSHA: a work-related death within 8 hours, and an "
     "in-patient hospitalization, amputation or loss of an eye within 24 hours. If the employer learns of it later, the clock starts then. "
     "Tell your supervisor right away so they can make the report.",
     "OSHA 29 CFR 1904.39", "report, reporting, fatality, death, hospital, hospitalized, amputation, eye, 8 hours, 24 hours, osha, muerte, reportar"),
    ("When an injury goes on the OSHA 300 log",
     "A work-related injury or illness is recordable if it causes death, days away from work, restricted work or a job transfer, medical "
     "treatment beyond first aid, or loss of consciousness, or if a doctor or other licensed health care professional diagnoses a "
     "significant injury or illness. Report every injury to your supervisor, even a small one. The employer decides what is recordable.",
     "OSHA 29 CFR 1904.7", "recordable, 300 log, osha log, first aid, medical treatment, days away, restricted duty, trir, dart, lesion"),
    ("Emergency action plan",
     "Know your site's alarm, your exit route and your meeting point before you need them. OSHA requires an emergency action plan that "
     "covers how to report a fire or other emergency, how to evacuate and which exit routes to use, what employees who stay to run "
     "critical operations do before they leave, how everyone is accounted for after evacuating, what employees with rescue or medical "
     "duties do, and who to ask about the plan. It must be written and available to employees. A "
     "workplace with 10 or fewer employees may share it by word of mouth.",
     "OSHA 29 CFR 1910.38", "emergency, evacuation, evacuate, alarm, muster, meeting point, plan, tornado, earthquake, emergencia, evacuar"),
    ("Exit doors and exit routes",
     "If an exit is locked, chained or blocked, report it to your supervisor now and do not work around it. Exit route doors must open "
     "from the inside at all times without keys, tools or special knowledge. Exit routes must be kept free and unobstructed: nothing may "
     "be stored in them, even for a short time. An exit route may not pass through a room that can be locked, like a bathroom.",
     "OSHA 29 CFR 1910.36 and 1910.37", "exit, door, locked, chained, blocked, egress, fire exit, route, obstructed, salida, puerta"),
    ("Portable fire extinguishers",
     "If your site's plan is to evacuate, pull the alarm and get out: do not fight the fire. Use an extinguisher only if your site has "
     "trained you and expects you to, the fire is small, and your way out is clear behind you. OSHA requires portable extinguishers to be visually inspected monthly and to get an annual maintenance check. Employers who expect "
     "employees to use extinguishers must train them when hired and at least once a year after that.",
     "OSHA 29 CFR 1910.157", "fire extinguisher, extinguisher, fire, monthly inspection, annual, pass, extintor, fuego, incendio"),
    ("Fire prevention plan",
     "OSHA requires a fire prevention plan that lists the major fire hazards and how to handle and store those materials, the ignition "
     "sources and how to control them, and the fire equipment for each hazard. It also covers controlling flammable and combustible waste, "
     "maintaining safeguards on heat-producing equipment, and who is responsible for ignition and fuel hazards. "
     "It must be written and available to employees. A workplace with 10 or fewer employees may share it by word of mouth. Keep "
     "flammable scrap and trash from piling up in your area.",
     "OSHA 29 CFR 1910.39", "fire prevention, fire hazard, housekeeping, ignition, combustible, plan, prevencion de incendios"),
    ("First aid and eyewash",
     "If a chemical gets in someone's eyes or on their skin, get them to the eyewash or drench shower right away and call for help. "
     "Where eyes or body could be exposed to corrosive materials, OSHA requires facilities for quick drenching or flushing within the "
     "work area for immediate use. If there is no clinic or hospital in near proximity, someone on site must be trained in first aid, and "
     "first aid supplies must be readily available. Know where your eyewash is before you open a chemical.",
     "OSHA 29 CFR 1910.151", "first aid, eyewash, eye wash, shower, drench, corrosive, chemical in eye, acid, caustic, lavaojos, primeros auxilios"),

    # ---- Walking-working surfaces and falls ------------------------------------------------------
    ("Floors, spills and housekeeping",
     "Clean up or guard a spill before anyone walks through it, and report hazards you cannot fix. OSHA requires work areas, passageways "
     "and storerooms to be clean, orderly and sanitary, floors kept as dry as feasible, and walking surfaces free of sharp or sticking-out "
     "objects, loose boards, corrosion, leaks, spills, snow and ice. A hazard must be fixed before anyone uses that surface again, or "
     "guarded until it is fixed.",
     "OSHA 29 CFR 1910.22", "housekeeping, spill, slip, trip, wet floor, ice, walking surface, clutter, piso mojado, resbalon, derrame"),
    ("Ladders: safe use",
     "Check the ladder before you use it each shift. If it is damaged, tag it \"Dangerous: Do Not Use\" and take it out of service. When "
     "you climb, face the ladder, keep at least one hand on it, and do not carry anything that could throw you off balance. Use a ladder "
     "only for what it was designed for. A portable ladder used to reach an upper level must extend at least 3 feet above that landing. "
     "Do not tie ladders together to make them longer unless they are designed for it.",
     "OSHA 29 CFR 1910.23", "ladder, step ladder, extension ladder, climb, three points, inspect, damaged ladder, escalera"),
    ("Fall protection: the 4-foot rule",
     "If you could fall 4 feet or more to a lower level from an unprotected side or edge, you must be protected by a guardrail, safety net "
     "or personal fall protection system. The same 4-foot rule covers holes, including skylights: they need a cover, guardrail or fall "
     "protection. Do not step past a missing guardrail or an uncovered hole. Stop and tell your supervisor. Other heights apply in "
     "special cases, like dockboards and fixed ladders.",
     "OSHA 29 CFR 1910.28", "fall, fall protection, 4 feet, edge, hole, skylight, mezzanine, platform, harness, guardrail, caida, proteccion contra caidas"),
    ("Guardrails",
     "Never lean on, sit on or climb a guardrail, and report one that is loose or damaged. OSHA requires the top rail to be 42 inches high, "
     "plus or minus 3 inches, and to hold at least 200 pounds pushed down or out near the top. Openings in the guardrail system may be no "
     "more than 19 inches wide.",
     "OSHA 29 CFR 1910.29", "guardrail, railing, top rail, midrail, 42 inches, barandal, baranda"),
    ("Fixed ladders over 24 feet",
     "Fixed ladders that extend more than 24 feet above a lower level need fall protection. Ladders installed on or after November 19, 2018 "
     "need a personal fall arrest system or ladder safety system. Older ladders may still use a cage or well for now, but by November 18, "
     "2036 all such fixed ladders must have a personal fall arrest or ladder safety system. Use the system that is installed every time.",
     "OSHA 29 CFR 1910.28(b)(9)", "fixed ladder, cage, ladder safety system, roof ladder, 24 feet, tank ladder, escalera fija"),
    ("Fall protection training",
     "You must be trained by a qualified person before you are exposed to a fall hazard where you use personal fall protection. Training "
     "covers how to recognize the fall hazards in your area, how to reduce them, and how to put on, inspect, use, anchor and store your "
     "fall protection the way the manufacturer says. If you have not been trained on the harness or lanyard you were handed, do not use it "
     "yet. Ask for training.",
     "OSHA 29 CFR 1910.30", "fall training, harness, lanyard, anchor, tie off, competent, qualified person, arnes, entrenamiento"),

    # ---- PPE ------------------------------------------------------------------------------------
    ("PPE: hazard assessment and who pays",
     "Your employer must assess the workplace for hazards that call for PPE, choose the right PPE, and document the assessment in a written "
     "certification. PPE required by OSHA is provided at no cost to employees, with some exceptions, such as ordinary steel-toe boots and "
     "ordinary prescription safety glasses that can be worn off the job. Damaged or defective PPE must not be used: swap it out before you "
     "start.",
     "OSHA 29 CFR 1910.132", "ppe, personal protective equipment, hazard assessment, who pays, cost, steel toe, equipo de proteccion, epp"),
    ("PPE training",
     "Before you work with required PPE, you must be trained on when it is needed, which PPE, how to put it on, take it off, adjust and wear "
     "it, its limits, and how to care for it. You must show you understand before doing the work. You must be retrained when the work or "
     "the PPE changes, or when it is clear you did not understand. Ask if no one has shown you.",
     "OSHA 29 CFR 1910.132(f)", "ppe training, how to wear, don, doff, retrain, capacitacion epp"),
    ("Eye and face protection",
     "Wear eye or face protection when there is a hazard from flying particles, molten metal, liquid chemicals, acids or caustics, chemical "
     "gases or vapors, or harmful light like welding. Where things can fly, your eye protection must have side protection: clip-on or "
     "slide-on side shields that meet the rule are fine. If you wear prescription glasses, you need protection that covers them or has "
     "your prescription built in.",
     "OSHA 29 CFR 1910.133", "safety glasses, goggles, face shield, eye protection, side shields, welding, gafas, lentes de seguridad, careta"),
    ("Gloves, and when not to wear them",
     "Around rotating parts, such as drill presses, lathes, spindles, rollers and shafts, a glove can be caught and pull your hand in. Follow "
     "your site's procedure for that machine. It often means no gloves, no rings, no loose sleeves and hair tied back while the part is "
     "turning. Everywhere else, OSHA requires hand protection where hands face cuts, punctures, abrasions, chemical or thermal burns, "
     "skin absorption of harmful substances or temperature extremes, and the glove must be chosen for that task.",
     "OSHA 29 CFR 1910.138", "gloves, hand protection, cut, chemical gloves, rotating, lathe, drill press, entanglement, guantes"),
    ("Noise and hearing protection",
     "If you have to raise your voice to be heard an arm's length away, ask whether the area has been checked for noise. Your employer must "
     "run a hearing conservation program when exposure reaches an 8-hour average of 85 decibels. That includes monitoring, hearing "
     "protection, training, a baseline hearing test within 6 months of first exposure, and a new test every year. The legal limit for "
     "8 hours is 90 decibels, and the allowed time drops as noise goes up: for example 4 hours at 95, 2 hours at 100.",
     "OSHA 29 CFR 1910.95", "noise, hearing, ear plugs, earmuffs, decibels, 85, 90, audiogram, hearing test, ruido, tapones, audicion"),
    ("Respirators",
     "Do not use a tight-fitting respirator until you have had a medical evaluation and a fit test for that exact make, model and size. "
     "OSHA requires a written respiratory protection program, medical evaluations, fit testing before first use, whenever you change to a "
     "different facepiece, and at least once a year after that, plus training, all at no cost to you. A beard or anything that gets "
     "between the seal and your face can stop a tight-fitting respirator from sealing.",
     "OSHA 29 CFR 1910.134", "respirator, mask, n95, fit test, medical evaluation, cartridge, dust, fumes, respirador, mascarilla"),

    # ---- Hazardous energy and confined spaces ------------------------------------------------------
    ("Lockout/tagout: the steps",
     "Never put any part of your body into a machine until it is locked out and you have proven it is dead. OSHA sets this order, and your "
     "site's written procedure for that machine gives the details: "
     "1. Preparation: know the type and amount of energy, its hazards and how to control it. "
     "2. Shut the machine down the normal way. "
     "3. Isolate it: operate every energy isolating device. "
     "4. Apply your lock or tag to each energy isolating device. "
     "5. Relieve, disconnect, restrain or otherwise make safe all stored energy, such as springs, pressure, hydraulics or capacitors. "
     "6. Verify isolation before you start work, for example by trying the normal start controls, then returning them to off.",
     "OSHA 29 CFR 1910.147(d)", "lockout, tagout, loto, lock out, energy, isolate, verify, try out, zero energy, bloqueo, candado, etiquetado"),
    ("Lockout/tagout: whose lock comes off",
     "Each lock or tag must be removed by the person who put it on. If that person is not available, the employer may remove it only by "
     "following a specific procedure: verify the person is not at the facility, make every reasonable effort to reach them, and make sure "
     "they know before they come back to work. Never remove someone else's lock. Before locks come off and energy is restored, check "
     "that tools and other nonessential items are removed, the machine is intact, and every employee is safely positioned or clear. "
     "After the locks come off and before the machine starts, tell the affected employees. The employer must inspect each energy control procedure at least once a year.",
     "OSHA 29 CFR 1910.147(e) and (c)(6)", "remove lock, coworker lock, someone else's lock, restart, annual inspection, quitar candado"),
    ("Permit-required confined spaces",
     "Never go into a tank, pit, vault, silo or similar space marked \"Danger: Permit-Required Confined Space, Do Not Enter\" unless you are "
     "an authorized entrant on a signed entry permit. If someone collapses inside, do not go in after them. Call for the trained rescue "
     "team and 911. Before entry, the air is tested first for oxygen, then for flammable gases and vapors, then for toxic gases. Oxygen "
     "below 19.5 percent or above 23.5 percent is a hazardous atmosphere. An attendant stays outside, watching the entrants, the whole time.",
     "OSHA 29 CFR 1910.146", "confined space, permit space, tank, vault, pit, silo, manhole, entry permit, attendant, rescue, oxygen, espacio confinado"),

    # ---- Machines and tools ------------------------------------------------------------------------
    ("Machine guarding",
     "Run a machine only with its guards in place. If a guard is missing, loose or bypassed, stop and report it. OSHA requires guarding to "
     "protect the operator and others from the point of operation (where the work is done), in-running nip points, rotating parts, and "
     "flying chips and sparks. Guards must be attached to the machine where possible and must not create a hazard themselves. Machines "
     "designed to stay in one place must be anchored so they cannot walk or move.",
     "OSHA 29 CFR 1910.212", "machine guard, guarding, point of operation, nip point, pinch point, rotating, bypass, guarda, maquina"),
    ("Bench and pedestal grinders",
     "Before mounting a wheel, inspect it and ring-test it: tap it gently with a light non-metal tool. A dull, dead sound means it may be "
     "cracked: do not use it. Check that the wheel's rated speed is at least the grinder's spindle speed. Keep the work rest within 1/8 "
     "inch of the wheel and the tongue guard within 1/4 inch, and adjust them as the wheel wears. Wear eye protection with side shields "
     "and a face shield if your site requires one.",
     "OSHA 29 CFR 1910.215", "grinder, bench grinder, abrasive wheel, work rest, tongue guard, ring test, 1/8, 1/4, esmeril, piedra"),
    ("Compressed air for cleaning",
     "Never blow dust or chips off your skin or clothing with compressed air: it can force air or debris into your body. OSHA allows "
     "compressed air for cleaning only when it is reduced to less than 30 psi, and only with effective chip guarding and PPE.",
     "OSHA 29 CFR 1910.242(b)", "compressed air, air hose, blow off, 30 psi, cleaning, chips, aire comprimido"),

    # ---- Forklifts, cranes and slings --------------------------------------------------------------
    ("Forklift: check it before every shift",
     "Inspect your forklift before you put it in service, at least once a day. If it is used around the clock, check it after each shift. "
     "If anything affects safety, such as brakes, steering, horn, forks, chains, hydraulic leaks, tires or lights, do not drive it. Tag it "
     "out and report it. It stays out of service until it is repaired.",
     "OSHA 29 CFR 1910.178(q)(7)", "forklift, powered industrial truck, pre-shift, daily inspection, checklist, montacargas, inspeccion"),
    ("Forklift: training and evaluation",
     "Only trained and evaluated operators may drive a forklift. Training covers that type of truck and your workplace, and ends with an "
     "evaluation of your driving. Your performance must be re-evaluated at least once every three years. You get refresher training after "
     "unsafe driving, an accident or near miss, a poor evaluation, a different type of truck, or workplace changes that affect safe "
     "operation.",
     "OSHA 29 CFR 1910.178(l)", "forklift training, certification, license, operator, evaluation, three years, refresher, montacargas, capacitacion"),
    ("Forklift: leaving it parked",
     "When you leave a forklift unattended, lower the forks fully, put the controls in neutral, shut off the power and set the brakes. Block "
     "the wheels if it is on an incline. It counts as unattended when you are 25 feet or more away, or whenever you cannot see it. Even "
     "when you are within 25 feet and can see it, lower the forks, neutralize the controls and set the brakes. Keep a safe distance from "
     "the edge of docks and ramps.",
     "OSHA 29 CFR 1910.178(m)(5)", "park forklift, unattended, forks down, brake, 25 feet, dock edge, estacionar montacargas"),
    ("Slings and rigging",
     "A competent person designated by the employer must inspect each sling and all its fittings every day before use, and during use when "
     "conditions call for it. Damaged or defective slings must be removed from service right away. Do not use a sling without its legible "
     "identification tag, and never go over its rated load. Stand out of the path of the load, because a failed sling or load does not go "
     "where you expect.",
     "OSHA 29 CFR 1910.184", "sling, rigging, chain sling, wire rope, synthetic sling, inspection, rated capacity, tag, eslinga, aparejo"),
    ("Overhead cranes: inspections",
     "OSHA sets two levels of crane inspection: frequent, at daily to monthly intervals, and periodic, at 1 to 12 month "
     "intervals. Operating mechanisms and air or hydraulic systems are checked daily, and hooks get a daily visual check plus a monthly "
     "inspection with a signed, dated record. Your site's crane program "
     "sets the exact schedule. Report any defect before you lift, and never ride the hook or the load.",
     "OSHA 29 CFR 1910.179(j)", "crane, overhead crane, hoist, bridge crane, hook, inspection, frequent, periodic, grua"),

    # ---- Electrical ------------------------------------------------------------------------------
    ("Electrical panels: keep the space clear",
     "Never store anything in front of an electrical panel. For equipment up to 150 volts to ground, OSHA requires clear working space at "
     "least 3 feet deep in front, at least 30 inches wide or the width of the equipment, whichever is more, with room for the door to open "
     "at least 90 degrees. That working space may not be used for storage, and it must be lit.",
     "OSHA 29 CFR 1910.303(g)", "electrical panel, breaker panel, clearance, 36 inches, 3 feet, storage, blocked panel, panel electrico"),
    ("Extension cords and flexible cords",
     "Do not use an extension cord with damaged insulation, a missing ground pin or a bad splice. Take it out of service. Unless a specific "
     "exception applies, flexible cords may not be used as a substitute for permanent wiring, run through holes in walls, ceilings or "
     "floors, run through doorways or windows, attached to building surfaces, or hidden behind walls or ceilings. Cords must have strain "
     "relief so a pull does not reach the terminals.",
     "OSHA 29 CFR 1910.305(g)", "extension cord, flexible cord, power strip, daisy chain, splice, permanent wiring, extension electrica"),
    ("Working on or near live electrical parts",
     "Live parts you may be exposed to must be de-energized before you work on or near them, unless de-energizing creates a greater hazard "
     "or is not feasible. Only qualified persons may work on parts that have not been de-energized and locked out. If you are not "
     "qualified, stay away from open panels and exposed wiring and report them.",
     "OSHA 29 CFR 1910.333", "electrical, live parts, energized, qualified person, electrician, shock, arc flash, electricidad, energizado"),

    # ---- Chemicals and health ------------------------------------------------------------------
    ("Chemical labels and safety data sheets (HazCom)",
     "Before you use a chemical, read its label and know where its safety data sheet (SDS) is. Every container of hazardous chemicals in the "
     "workplace must be labeled. SDSs must be readily accessible to you during every shift in your work area: electronic access is fine "
     "if nothing gets in the way. You must be trained on the chemicals in your area when first assigned and whenever a new chemical "
     "hazard is introduced. If a container has no label, do not use it. Report it.",
     "OSHA 29 CFR 1910.1200", "hazcom, hazard communication, sds, msds, safety data sheet, label, chemical, right to know, etiqueta, hoja de datos"),
    ("Flammable liquid storage cabinets",
     "Keep flammable liquids closed and in their approved cabinet when you are not using them. A single flammable storage cabinet may hold "
     "no more than 60 gallons of Category 1, 2 or 3 flammable liquids, or 120 gallons of Category 4. Keep ignition sources away from where "
     "they are used and stored.",
     "OSHA 29 CFR 1910.106(d)(3)", "flammable, cabinet, gasoline, solvent, 60 gallons, storage, flammable liquids, inflamable, gabinete"),
    ("Storing oxygen and fuel gas cylinders",
     "Inside buildings, store oxygen cylinders at least 20 feet from fuel-gas cylinders, like acetylene or propane, and from combustible "
     "materials, especially oil or grease. Otherwise separate them with a noncombustible barrier at least 5 feet high with at least a "
     "half-hour fire rating. Store cylinders in a well-protected, ventilated, dry place away from heat sources, at least 20 feet from "
     "highly combustible materials.",
     "OSHA 29 CFR 1910.253(b)(4)", "cylinder, oxygen, acetylene, propane, fuel gas, welding, torch, 20 feet, storage, cilindro, oxigeno"),
    ("Bloodborne pathogens",
     "Treat all blood and certain body fluids as if they are infectious. If you help someone who is bleeding, put on gloves first if you can, "
     "and report any contact with blood. Employers with workers who have occupational exposure need a written exposure control plan. The "
     "hepatitis B vaccine must be offered within 10 working days of starting the assignment, after training, unless the worker is "
     "already vaccinated or immune.",
     "OSHA 29 CFR 1910.1030", "blood, bloodborne, first aid responder, needle, hepatitis b, exposure control plan, sangre, hepatitis"),
    ("Respirable crystalline silica",
     "Cutting, grinding or crushing stone, concrete, brick or sand can release silica dust that scars the lungs. Use the dust controls your "
     "site provides, like water, vacuum or ventilation, and do not dry-sweep or blow the dust. In general industry, the exposure limit is "
     "50 micrograms per cubic meter as an 8-hour average, and employers must assess exposure at or above the 25 microgram action level.",
     "OSHA 29 CFR 1910.1053", "silica, dust, concrete, stone, countertop, quartz, grinding, cutting, lung, silice, polvo"),

    # ---- Signs -----------------------------------------------------------------------------------
    ("Danger and caution signs and tags",
     "Obey every sign and tag, and never remove one that is not yours. Danger signs mean an immediate hazard and use red. Caution signs warn "
     "of a possible hazard or unsafe practice and use a yellow background with black letters. For accident prevention tags, OSHA "
     "recommends red for DANGER, yellow for CAUTION and orange for WARNING.",
     "OSHA 29 CFR 1910.145", "sign, tag, danger, caution, warning, red, yellow, orange, do not operate, letrero, etiqueta, peligro"),
]

WHAT_OTIS_IS_OLD = (
    "OTIS is the Zero Harm safety assistant from Trainovate Technologies. OTIS answers only from Zero Harm Weekly toolbox talks "
    "and this knowledge base, runs on your phone, and works with no signal."
)
WHAT_OTIS_IS_NEW = (
    "OTIS is the Zero Harm safety assistant from Trainovate Technologies. OTIS answers only from Zero Harm Weekly toolbox talks, "
    "Zero Hour huddle cards, and plain-language summaries of federal OSHA General Industry rules in this knowledge base. OTIS runs on "
    "your phone and works with no signal."
)


def seed(apps, schema_editor):
    KbEntry = apps.get_model("talks", "KbEntry")
    for title, body, source, tags in ENTRIES:
        KbEntry.objects.get_or_create(title=title, defaults={"body": body, "source": source, "tags": tags})
    # Only touch the starter entry if nobody has edited it in the admin.
    entry = KbEntry.objects.filter(title="What OTIS is").first()
    if entry and entry.body.startswith(WHAT_OTIS_IS_OLD):
        entry.body = entry.body.replace(WHAT_OTIS_IS_OLD, WHAT_OTIS_IS_NEW)
        entry.tags = entry.tags + ", osha, general industry"
        entry.save()


def unseed(apps, schema_editor):
    KbEntry = apps.get_model("talks", "KbEntry")
    KbEntry.objects.filter(title__in=[e[0] for e in ENTRIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("talks", "0008_otis_edge")]
    operations = [migrations.RunPython(seed, unseed)]
