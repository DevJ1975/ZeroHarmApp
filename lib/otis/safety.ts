/**
 * A hard rule outside the AI: if a message sounds like someone is hurt or in danger right now,
 * the app shows "Call 911" before OTIS says anything. Small on-device models can be wrong; this can't be.
 *
 * A miss (someone hurt, no 911 prompt) is far worse than a false alarm, so the patterns lean wide,
 * and they allow for panic typing: no apostrophes ("cant", "hes"), common misspellings
 * ("unconcious", "siezure", "electricuted", "se callo", "inconciente").
 * Stems like "amputat" have no trailing \b so they match "amputated" / "amputation".
 * Spanish lines have no trailing \b: JavaScript's \b doesn't know accented letters (ó, é),
 * and it would also block attached pronouns like "ayúdame". For the same reason no \b sits
 * right before a word that starts with an accent ("ácido").
 */
const URGENT = [
  // Someone is down or not responding
  /\b(unresponsive|not respond|collapsed|colapsed|seizure|siezure|seizing|convuls|fainted|blacked out|knocked out|out cold)/i,
  /\buncon(sc|c|s)h?i?ous|\bpassed[ -]?out\b/i,
  /\b(hurt|injured|man down|person down|worker down|not movin|won'?t wake up|not waking up)\b/i,
  /\b(head|eye|back|neck|spinal|serious|bad) injur/i,
  /\b(he|she|they|someone|somebody|guy|dude|man|woman|worker|co-?worker|operator|driver|bro|buddy)('?s|s| is| are| was| went| just went)?( lying| laying)? (down|on the (ground|floor))\b/i,
  /\b(is|he'?s|hes|she'?s|shes|they'?re|looks|might be|may be) dead\b|\b(died|dying)\b/i,
  // Breathing, heart, choking, allergy
  /\b(can'?t|cant|cannot|can not|couldn'?t|unable to|struggling to|trouble|hard to|hard time) breath/i,
  /\b(not|isn'?t|isnt|ain'?t|aint|stopped|quit|no longer) breath/i,
  /\b(short of breath|gasping|no pulse|heart stopped|cardiac|heart ?attack|cpr|aed|turning blue|drowning|allergic reaction|anaphyla)/i,
  /\bchok(e|es|ed|ing)|\bchocking\b(?! (the |a |his |her |their )?(wheels?|tires?|trucks?|trailers?|cars?))/i,
  /\bthroat (is )?(closing|swelling)/i,
  // Bleeding, crushing, caught, struck
  /\b(bleedin|bled out|crushed|trapped|pinned|caught in|lacerat|deep cut|smashed|mangled|deglov|impaled)/i,
  /\bblood\b|\bcut (himself|herself|myself|themselves)\b|\bthrough (his|her|my|their) (hand|foot|arm|leg|eye)/i,
  /\b(amputat|severed|cut (off )?(his|her|my|their) (finger|hand|arm|leg|foot))/i,
  /\b(fingers?|hand|arm|leg|toes?|foot|thumb) (got |was |is )?(cut|chopped|sliced|ripped|torn) off/i,
  /\b(hand|arm|fingers?|leg|foot|hair|sleeve|glove|shirt|clothes)\b.{0,20}\b(is|got|was|are|were|been|just got) (caught|stuck|jammed|pulled|sucked|dragged|crushed|smashed|mangled)/i,
  /\b(hand|arm|fingers?|leg|foot|hair|sleeve|glove) (is |was |got )?in the (machine|rollers?|press|conveyor|gears?|auger|mixer|grinder|saw|chain|belt|chipper|blender|slicer|shaft|lathe)/i,
  /\b(stuck|caught|jammed|pulled|sucked|dragged|drawn)\b.{0,20}\b(machine|rollers?|conveyor|gears?|auger|mixer|grinder|chipper|blender|slicer|shaft|lathe)/i,
  /\b(stuck|locked|trapped) (in|inside) (the|a) (freezer|cooler|tank|silo|bin|vessel|pit|trench|elevator)|\b(can'?t|cant|cannot) get out\b/i,
  /\bbrok(e|en) (his|her|my|their|a) (arm|leg|wrist|ankle|back|neck|bone|hip|ribs?)\b|\bbroken (arm|leg|wrist|ankle|back|neck|bone|hip|ribs?)\b/i,
  /\b(arm|leg|wrist|ankle|back|neck|hip|bone|ribs?) (is |are )?(broken|broke|snapped)\b|\bbone (is )?(sticking|poking) out|\bfractur/i,
  /\b(tipped over|rolled over|under it|fell on (him|her|them|me)|ran over|run over|got hit by|was hit by|got struck|was struck|struck by|caved in)\b/i,
  /\b(hit|struck|ran into|backed into) (him|her|them|someone|somebody|a (guy|worker|man|woman|person|pedestrian))\b|\bhit (his|her|my|their) head\b/i,
  /\b(forklift|truck|lift|loader|tractor|vehicle|cart|car|mower|crane)\b.{0,15}\b(flipped|overturned|rolled|tipped|crash)|\bcrashed into\b/i,
  /\b(hanging|suspended|dangling|stuck) (in|from|by|on) (his|her|their|the|a|my) (harness|lanyard|rope|lifeline|line|srl)\b|\bsuspension trauma/i,
  // Electricity, burns, fire
  /\b(electr[io]?cut|being shocked|getting shocked|got shocked|got zapped|stuck to|can'?t let go|live wire)/i,
  /\b(arc flash|burned|burnt|got burned|scalded|on fire|blinded|went blind)\b/i,
  /\b(chemical|acid|caustic|steam|electrical|bad|serious|severe) burns?\b|\bburns? (on|to) (his|her|my|their)\b/i,
  /\b(fire|smoke|explosion|exploded|flames|in flames|burning|blew up)\b/i,
  // Chemicals and gas
  /\b(gas|ammonia|chlorine|propane|refrigerant|carbon monoxide|co|h2s|hydrogen sulfide|chemical|acid) (leak|leaking|release|cloud|everywhere)/i,
  /\bleak(ing|ed)? (of )?(gas|ammonia|chlorine|propane|refrigerant|carbon monoxide|h2s)\b/i,
  /\bsmell(s|ing)? (like )?gas\b|\b(gas smell|smell of gas|rotten eggs?)\b/i,
  /\b(alarms?|detectors?|monitors?|sensors?|meters?)\b.{0,25}\b(going off|went off|sounding|alarming)\b/i,
  /\bchemical (in|on) (my|his|her|their) (eyes?|face|skin)\b/i,
  /\b(splash(ed)?|sprayed|squirted)\b.{0,30}\b(eyes?|face|skin)\b/i,
  /\b(acid|caustic|bleach|chemicals?|lye|chlorine|ammonia|sanitizer|degreaser|solvent)\b.{0,30}\b(eyes?|face|skin|mouth)\b/i,
  /\b(flush(ing)?|rins(e|ing)) (his|her|my|their|your) (eyes?|face|skin)\b/i,
  /\b(swallowed|ingested|poisoned|poisoning|overdos|od'd|narcan)/i,
  // Medical, heat and cold, falls
  /\b(chest pain|heart attack|stroke|heat ?stroke|heat exhaustion|fell|fallen|fall from)\b/i,
  /\b(slurr|drooping|hypotherm)/i,
  // Violence and self-harm (an emergency right now, even though no machine is involved)
  /\b(stabbed|got shot|been shot|was shot|shooter|has a (gun|knife|weapon)|pulled a (gun|knife)|attacked|assaulted)\b/i,
  /\b(suicid|kill (myself|himself|herself|themselves)|end (my|his|her|their) life|wants? to die|wanna die)/i,
  // Accidents and evacuations
  /\b((there'?s been|there was|we had|we just had|just had) an?|bad|serious|terrible|major) accident\b|\bevacuat(e|ing|ed)\b/i,
  // Spanish
  /\b(no (pued[eo]n? |pod[ií]a )?respir|incons?ciente|sangr|atrap(ad|[oó])|electr[io]?cut|in[cs]endio|fuego|desma(y|ll)|dolor de pecho|se ca(y|ll)[oó])/i,
  /\b(no se mueve|no despierta|no reacciona|no responde|aplast|quem(ó|o\b|ad[oa]|adura|ando)|herid[oa]|lastim|se (est[aá] )?ahog)/i,
  /\b(fuga de (gas|amon[ií]aco|cloro|qu[ií]mico)|se trag[oó]|descarga el[eé]ctrica|atropell|se cort[oó]|me cort[eé])/i,
  /\b(le dio (un |una )?(choque|toque|corriente|descarga|paro|infarto|ataque)|choque el[eé]ctrico|infarto|paro card|ataque al coraz|convuls|amput|derrame)/i,
  /\bhumo\b|\b(huele a gas|olor a gas|en llamas|explot|explosi[oó]n|prensad|ator[oó]|atorad)/i,
  /\b(agarr[oó] (la|el|su) (mano|brazo|dedo|pie|pierna)|perdi[oó] (un|una|el|la|los) (dedo|mano|brazo|pie|pierna))/i,
  /\b(le ca(y|ll)[oó]|ca(y|ll)[oó] (de|del|desde)|se golpe[oó]|golpe en la cabeza|(le|lo|la) peg[oó]|se volc[oó]|muert[oa]|se muri[oó]|muriendo)/i,
  /\bse (le )?rompi[oó] (el|la|un|una) (brazo|pierna|mano|pie|tobillo|mu[nñ]eca|cuello|espalda|hueso|cadera|costilla)/i,
  /\b(hubo un accidente|tuvo un accidente|accidente grave|matarse|suicid|tiene un arma|tiene una pistola)/i,
  /(ácido|\bacido|qu[ií]mico|\bcloro|amon[ií]aco|\bsosa|c[aá]ustico).{0,30}(ojos?|cara|piel)/i,
  // Calls for help
  /\b(emergency|emergencia|911|9-1-1|right now|ahora mismo|help+|auxilio|socorro|ambulance|ambulancia|paramedics?|medics?)\b/i,
  /\b(needs?|get|bring|call) first aid\b/i,
  /\bay[uú]d(a|ame|enme|anme)/i,
];

/**
 * Emergencies told with a safe phrase's own words ("I used the fire extinguisher",
 * "his fall arrest deployed"). These are checked on the FULL message, before safe phrases are
 * stripped, so stripping can never hide them.
 */
const IN_PROGRESS = [
  /\b(grab|grabbed|bring|brought|emptied|sprayed|spraying|used) (a |the |an |another |our |my |his |her )?(fire )?extinguishers?/i,
  /\b(lanyard|srl|yo-?yo|lifeline|harness|shock (pack|absorber)|fall arrest|fall protection)\b.{0,20}\b(deployed|snapped|broke|failed|gave out|didn'?t hold|caught (him|her|them|me))/i,
  /\b(get|got|take|took|rush|bring|brought|put|carry) (him|her|them|me) (to|in|under) (the )?(emergency )?(eye ?wash|safety shower|shower)/i,
  /\b(he'?s|she'?s|they'?re|i'?m) (in|under|at|using) the (emergency )?(eye ?wash|safety shower|shower)/i,
  /\b(activate|activated|activating|initiate|initiated|declare|declared|declaring|executing|started|starting) (the |our |an? )?emergency (action|response) plan/i,
  /\b(pressed|pushed|slammed|smashed|pulled|had to hit|just hit|i hit|we hit|he hit|she hit) (the |an? )?(emergency stop|e-?stop)/i,
];

/**
 * Everyday phrases that contain an alarm word but are not emergencies.
 * Rule: strip these from a copy of the message, THEN match URGENT on what's left.
 * Never skip the whole message because a safe phrase appears, so
 * "there's a fire, where's the fire extinguisher" still fires on the first "fire".
 */
const SAFE_PHRASES = [
  /\bfire (extinguishers?|prevention|drills?|exits?|watch|safety|marshals?|doors?|lanes?|codes?|retardant|resistant|rated)\b/gi,
  /\bsmoke (breaks?|(detector|alarm)s? (tests?|testing|inspections?|batter(y|ies)|placement|requirements?|spacing|codes?))\b/gi,
  /\b(test|testing|tested|inspect\w*|check\w*|replac\w*|install\w*) (the |a |our |all )?smoke (detectors?|alarms?)\b/gi,
  /\bemergency (action|response) plans?\b/gi,
  /\bemergency (eye ?wash|showers?)( stations?)?\b/gi,
  /\bemergency (exits?|stops?|lighting|contacts?|drills?|assembly (points?|areas?)|preparedness)\b/gi,
  /\b(how (do|can|should) (i|we|you) )?prevent(ing)? (a )?falls?\b/gi,
  /\bfall (protection|arrest|prevention|hazards?)\b/gi,
  /\barc flash (ppe|boundary|boundaries|study|labels?|suits?|assessment|analysis|training)\b/gi,
  /\bwhat('?s| is| are) (an? )?arc flash(es)?\b/gi,
  // OSHA "Focus Four" and program names that are training topics, not events
  /\bcaught[- ]in(( or| and|\/)? ?-?between)? hazards?\b|\bcaught[- ]between hazards?\b|\bstruck[- ]by hazards?\b/gi,
  /\belectrocution (hazards?|risks?|prevention|training)\b|\b(prevent(ing)?|avoid(ing)?) electrocution\b/gi,
  /\bamputation (hazards?|risks?|prevention|programs?|nep|emphasis)\b/gi,
  /\btrapped[- ]key( interlocks?)?\b/gi,
  /\b(cpr|aed|first aid) (training|class(es)?|courses?|certifications?|certified|cards?|inspections?|checklists?|kits?|requirements?)\b/gi,
  /\bblood[- ]?borne( pathogens?)?\b/gi,
  /\bactive shooter (training|drills?|plans?)\b|\bsuicide prevention\b/gi,
  // Spanish: plans, drills and equipment ("plan de emergencia", "simulacro de incendio")
  /\b(plan(es)?|salidas?|simulacros?|luces|paros?|regaderas?|duchas?|lavaojos|contactos?|rutas?|procedimientos?) de (emergencias?|incendios?|evacuaci[oó]n)/gi,
  /\b(extintor(es)?|prevenci[oó]n) (de|contra) incendios?/gi,
];

const stripSafePhrases = (text: string) =>
  SAFE_PHRASES.reduce((rest, phrase) => rest.replace(phrase, ' '), text);

export const looksUrgent = (text: string) => {
  if (IN_PROGRESS.some((r) => r.test(text))) return true;
  const rest = stripSafePhrases(text);
  return URGENT.some((r) => r.test(rest));
};
