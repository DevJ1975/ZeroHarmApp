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
  /\b(unresponsive|not respond|collapsed|colapsed|seizure|siezure|seazure|sezure|seisure|seizur|seizing|seizin|convuls|fainted|blacked out|knocked out|out cold)/i,
  /\buncon(sc|c|s)h?i?ous|\bpassed[ -]?out\b/i,
  /\b(hurt|injured|man down|person down|worker down|won'?t wake up|not waking(?: up)?)\b/i,
  // "not moving", "aint movin", "isnt movin'": the old `not movin\b` never matched "moving".
  /\b(not|ain'?t|aint|isn'?t|isnt) movin(g|')?(?![a-z])/i,
  /\b(head|eye|back|neck|spinal|serious|bad) injur/i,
  /\b(he|she|they|someone|somebody|guy|dude|man|woman|worker|co-?worker|operator|driver|bro|buddy)('?s|s| is| are| was| went| just went)?( lying| laying)? (down|on the (ground|floor))\b/i,
  /\b(is|he'?s|hes|she'?s|shes|they'?re|looks|might be|may be) dead\b|\b(died|dying)\b/i,
  // Breathing, heart, choking, allergy
  /\b(can'?t|cant|cnt|cannot|can not|couldn'?t|unable to|struggling to|trouble|hard to|hard time) (breath|breth|breeth)/i,
  /\b(not|isn'?t|isnt|ain'?t|aint|stopped|quit|no longer) (breath|breth|breeth)/i,
  /\b(short of breath|gasping|no pulse|heart stopped|cardiac|heart ?attack|cpr|aed|turn(ing|ed|in'?) (blue|purple)|drowning|allergic reaction|anaphyla)/i,
  /\bchok(e|es|ed|ing)|\bchocking\b(?! (the |a |his |her |their )?(wheels?|tires?|trucks?|trailers?|cars?))/i,
  /\bthroat (is |feels )?(closing|swelling|swollen|tight)/i,
  /\b(stung|bitten|bit) by (a |an |some )?(bee|bees|wasps?|hornets?|yellow ?jackets?|snakes?|spiders?|scorpions?|dogs?|rats?|insects?|bugs?)|\b(asthma|panic|allergy|diabetic) attack|\b(having|had|has) an? (asthma|panic|allergic|diabetic|insulin) (attack|reaction|episode|emergency)|\b(low blood sugar|diabetic (shock|emergency|coma)|insulin shock)/i,
  // Bleeding, crushing, caught, struck
  /\b(bleedin|bleding|bledin|gush(ing|es|ed)?\b|bled out|crushed|trapped|pinned|caught in|lacerat|deep cut|smashed|mangled|deglov|impaled)/i,
  /\bblood\b|\bcut (himself|herself|myself|themselves)\b|\bthrough (his|her|my|their) (hand|foot|arm|leg|eye|boot|shoe|glove|palm|fingers?|thumb|head|chest|neck)/i,
  /\b(amputat|severed|cut (off )?(his|her|my|their) (finger|hand|arm|leg|foot))/i,
  /\b(fingers?|hand|arm|leg|toes?|foot|thumb) (got |was |is )?(cut|chopped|sliced|ripped|torn|took|taken|tore|came|snapped) off/i,
  /\b(hand|arm|fingers?|leg|foot|hair|sleeve|glove|shirt|clothes)\b.{0,20}\b(is|got|was|are|were|been|just got) (caught|stuck|jammed|pulled|sucked|dragged|crushed|smashed|mangled)/i,
  /\b(hand|arm|fingers?|leg|foot|hair|sleeve|glove) (is |was |got )?in the (machine|rollers?|press|conveyor|gears?|auger|mixer|grinder|saw|chain|belt|chipper|blender|slicer|shaft|lathe)/i,
  /\b(stuck|caught|jammed|pulled|sucked|dragged|drawn|pinched)\b.{0,20}\b(machine|rollers?|conveyor|gears?|auger|mixer|grinder|chipper|blender|slicer|shaft|lathe)/i,
  // "Got pinched in the press", "pinched his hand in the brake"
  /\bpinch(ed|ing)?\b.{0,25}\b(press|presses|brake|rollers?|machine|conveyor|gears?|belt|chain|die|between)\b/i,
  /\b(stuck|locked|trapped|shut) (in|inside) ((the|a|that|this) )?(walk-? ?in )?(freezer|fre+z+e?r|freezr|cooler|tank|silo|bin|vessel|pit|trench|elevator)|\b(can'?t|cant|cannot) get out\b/i,
  /\bbrok(e|en) (his|her|my|their|a) (arm|leg|wrist|ankle|back|neck|bone|hip|ribs?)\b|\bbroken (arm|leg|wrist|ankle|back|neck|bone|hip|ribs?)\b/i,
  /\b(arm|leg|wrist|ankle|back|neck|hip|bone|ribs?) (is |are )?(broken|broke|snapped)\b|\bbone (is )?(sticking|poking) out|\bfractur/i,
  /\b(tipped over|rolled over|under it|fell on (him|her|them|me)|ran over|run over|backed (up )?over|backed (up )?into (him|her|them|someone|somebody|a (guy|worker|man|woman|person))|got hit by|was hit by|got struck|was struck|struck by|caved in)\b/i,
  /\b(hit|struck|ran into|backed into) (him|her|them|me|us|someone|somebody|a (guy|worker|man|woman|person|pedestrian))\b|\bhit (his|her|my|their) head\b/i,
  /\b(forklift|truck|lift|loader|tractor|vehicle|cart|car|mower|crane)\b.{0,15}\b(flipped|overturned|rolled|tipped|crash)|\bcrashed into\b/i,
  /\b(hanging|suspended|dangling|stuck) (in|from|by|on) (his|her|their|the|a|my) (harness|lanyard|rope|lifeline|line|srl)\b|\bsuspension trauma/i,
  // Something came down on, closed on or rolled onto a person ("the press came down on his hand", "a rack came down on
  // top of Mike", "the buggy rolled on top of him", "the press cycled on her arm")
  /\b(came|come|comes|coming|fell|falls|landed|lands|dropped|drops|rolled|rolls|collapsed|toppled|tipped|slammed|crashed|cycled|closed|clamped|went off)\b.{0,12}\b(on|onto|over) top of\b/i,
  /\b(came|come|comes|coming|fell|falls|landed|lands|dropped|drops|rolled|rolls|collapsed|toppled|tipped|slammed|cycled|closed|clamped|went off|ran)( down| back)? (on|onto|over) (him|her|them|me|us|someone|somebody|a (guy|worker|man|woman|person|kid))\b/i,
  /\b(came down|come down|comes down|cycled|closed|clamped|slammed|landed|fell|dropped|rolled|ran|went off|shut|shuts)\b.{0,20}\b(on|onto|over) (his|her|their|my|someone'?s|somebody'?s|the (guy|worker|man|woman)'?s) (hands?|arms?|fingers?|thumbs?|legs?|foot|feet|toes?|head|chest|back|neck|body)\b/i,
  // Pinned, wedged or under something
  /\b(he|she|they|someone|somebody|guy|man|woman|worker|co-?worker|operator|driver|partner|buddy|person|kid|employee)\b.{0,25}\b(stuck|pinned|wedged|squeezed|caught|trapped)\b.{0,30}\bbetween\b/i,
  /\b(is|'s|got|was|are|stuck|pinned|trapped|lying|laying) (under|underneath|beneath) (the|a) (forklift|truck|trailer|car|vehicle|load|pallet|rack|racking|machine|lift|loader|tractor|beam|pipe|press|buggy|cart|skid|crate)\b/i,
  /\b(stuck|locked|trapped|caught) (in|inside) (the|a) (baler|compactor|machine|hopper|chute|auger|crusher|shredder|mixer|conveyor|grinder|chipper|dumpster|trailer)\b/i,
  /\b(pulling|pulled|dragging|dragged|sucking|sucked|drawing|drew) (him|her|them|me) (in|into|under)\b|\b(sleeve|hair|glove|shirt|clothes|clothing|jacket|hoodie|scarf)\b.{0,20}\bwrapped\b/i,
  /\bgave way\b|\bcave-?in\b/i,
  // Started up with a person still in it
  /\b(started|restarted|turned on|energized|re-?energized|switched on|powered (on|up)|fired up|kicked on|ran)\b.{0,60}\b(still )?(inside|in it|in there|under it|working on it|working in it|working under it|in the (machine|mixer|tank|press|line|conveyor))\b/i,
  // Not answering, not coming out, signs of trouble
  /\b(he|she|they|he'?s|hes|she'?s|shes|they'?re|guy|man|woman|worker|partner|co-?worker|buddy|entrant|attendant|operator|driver)\b.{0,25}\b(not|isn'?t|isnt|ain'?t|aint|aren'?t|stopped|won'?t|wont|quit|no longer) (answering|answerin|answer|talking|talkin|responding|respondin|moving|movin|getting up|gettin up|breathing|breathin)\b/i,
  /\b(not answering|not responding|no answer|isn'?t answering|isnt answering|ain'?t answering|aint answering|stopped answering)\b.{0,30}\b(inside|in the|from the|on the radio)\b|\b(isn'?t|isnt|not|ain'?t|aint) answer(ing|in) (me|us|the radio|on the radio)\b/i,
  /\b(in|inside) (the|a) (tank|vessel|silo|pit|bin|manhole|vault|sewer|trench|confined space)\b.{0,25}\b(not answering|not responding|no answer|not moving|not coming out)\b/i,
  /\b(has not|hasn'?t|hasnt|didn'?t|did not|never) (come|came) (back )?out\b/i,
  // A person turning gray (not "the screen turned gray")
  /\b(he|she|they|he'?s|hes|she'?s|shes|guy|man|woman|worker|co-?worker|buddy|partner)\b.{0,12}\bturn(ing|ed|s) gr[ae]y\b/i,
  /\b(lips|face|skin|fingers?|fingernails) (are |is )?(turned |turning |look |looks |went |going |gone )?(blue|purple|gr[ae]y)\b/i,
  /\beyes (are )?(closed|rolled|rolling)\b|\bfoaming\b|\b(shaking|twitching|jerking) (all over|uncontrollably|and)\b|\b(shaking|twitching|jerking|convulsing|seizing|lying|laying|passed out) (there |still |down )?(on|in) the (ground|floor|dirt)\b|\bscreaming\b|\bin (a lot of )?pain\b/i,
  /\b(drank|drunk|drink|swallowed|ate) (some |the |a )?(degreaser|bleach|chemicals?|cleaner|solvent|acid|caustic|antifreeze|coolant|sanitizer|poison|lye|ammonia)\b/i,
  /\b(sprayed|splashed|soaked|doused) (with|by|in) (ammonia|acid|caustic|chemicals?|chlorine|bleach|steam|hot)\b/i,
  /\b(touched|grabbed|contacted) (the |a )?(busbar|bus bar|live|energized|hot) ?\w*\b.{0,20}\b(dropped|fell|went down|collapsed)\b/i,
  /\b(took|taken|cut|ripped|tore) (off )?(\w+ )?(of )?(his|her|their|my) (fingers?|thumbs?|hand|toes?|ear)\b/i,
  // A body part gone or hanging, a machine grabbing clothes ("his finger is gone", "the belt grabbed his shirt")
  /\b(his|her|their|my|your|someone'?s|somebody'?s|\w+'s) (fingers?|finger ?tips?|thumbs?|hand|toes?|foot|ear|arm|leg|eye) (is |are |was |were )?(gone|missing|off|hanging|cut|out)\b/i,
  /\b(belt|chain|conveyor|rollers?|gears?|auger|shaft|spindle|chuck|drill|lathe|machine|mixer|saw|press|pulley|sprocket|blade|it)\b.{0,12}\b(grabbed|caught|took|pulled|snagged|yanked|ate|sucked in)\b.{0,6}\b(his|her|their|my|someone'?s) (shirt|sleeve|hair|glove|hand|arm|fingers?|clothes|jacket|hoodie|leg|foot|vest)\b/i,
  /\bred everywhere\b/i,
  // Heart, heat and cold illness on a person ("holding her chest", "gray and sweaty", "stopped sweating", "is dizzy")
  /\b(holding|clutching|grabbing|grabbed) (his|her|their|my) (chest|heart|arm|throat)\b|\bchest (hurts?|(is|feels|feel|getting|got) (real |really |so |very |kinda |kind of |super |too )?(hurting|tight|heavy)|tightness|pressure)\b|\b(pain|pressure|tightness) in (my|his|her|their|the) chest\b|\bchest (?:(?:is|feels?|got|getting|real|really|so|very|kinda|super|too|all|been) ){0,3}(tight|heavy|hurting|pains?)\b/i,
  /\b(gr[ae]y|pale|clammy|cold) and (sweaty|clammy|sweating)\b|\b(sweaty|sweating) and (gr[ae]y|pale|clammy)\b|\b(stopped|quit|not|isn'?t|isnt|no longer) sweating\b/i,
  /(?:^|[\s,.;:!?])(?!(?:otis|app|the|this|that|a|it|its|todays|new|next|last|monday|safety|toolbox)\s)[\w']+\s+talk(?:s|ed|in)?\s+(?:so |real |really |very |kinda |all )?(?:weird|funny|strange|slurred|slow|nonsense|gibberish|crazy)\b/i,
  /\btalking (weird|funny|strange|slurred|nonsense|gibberish|crazy)\b|\b(not|isn'?t|isnt) making (any )?sense\b|\bmaking no sense\b/i,
  /\b(is|are|was|were|feels?|felt|feeling|getting|got|seems?|looks?|am|i'?m|im) (so |really |very |kind of |kinda |a little |real |too )?(dizzy|disoriented|light-? ?headed|woozy|delirious)\b|\b(feels?|felt|feeling|getting|got|going|am|i'?m|im) (so |really |very |kind of |kinda |a little |real )?faint\b/i,
  /\b(going to|gonna|about to|might|could) (pass out|faint|black out|collapse|throw up)\b|\b(throwing up|threw up|vomiting|puking)\b/i,
  /\bshivering\b.{0,25}\b(won'?t|wont|can'?t|cant|not|isn'?t|stopped|uncontrollably)\b|\b(not|isn'?t|isnt|won'?t|wont|can'?t|cant) (getting up|get up)\b/i,
  /\b(he|she|they|guy|man|woman|worker|co-?worker|buddy|partner|someone|somebody|person)\b.{0,20}\b(is not|isn'?t|isnt|not|ain'?t|aint|doesn'?t look|does not look) (ok|okay|alright|all right)\b(?! to\b)/i,
  /\b(can'?t|cant|cnt|cannot|can not) feel (my|his|her|their) (arms?|legs?|face|hands?|feet|foot|fingers?|toes?|body|left|right|lips)\b/i,
  // Struck, clipped, a body part off: "got clipped by the forklift", "a bug bit me"
  /\b(got|was|been|get|gets|just got) (clipped|smacked|bumped|rammed|nailed|knocked over|knocked down|plowed|pinned|backed into)( into)?( by)?\b/i,
  /\b(bees?|wasps?|hornets?|spiders?|snakes?|scorpions?|dogs?|rats?|bugs?|insects?|ticks?|something|it) (bit|stung) (me|him|her|them|us)\b/i,
  // Someone who will not come out, a name and "down": "the tank guy ain't coming out", "mike down"
  /\b(guy|he|she|they|man|woman|worker|entrant|buddy|partner|someone|somebody|dude|bro)\b.{0,15}\b(aint|ain'?t|isnt|isn'?t|not|hasnt|hasn'?t|wont|won'?t|never) (coming|come|came|getting|got) (back )?out\b/i,
  /^\W*(?!(?:app|otis|it|its|system|server|wifi|internet|site|phone|screen|network|everything|all|shut|slow|calm|upside|sit|lay|stand|turn|break|count|back|scroll|weekly|zero|zeroharm|website|page|chat|signal|thumbs|go|went|come|settle|die|wind|cool|power|powered|shutting|slowing|calming|knock|tone|turned)\b)[a-z]+('?s| is)? down\W*$/i,
  /(?:^|\b(?:and|n|but|so)\b|[,;.!-])\s*(?!(?:app|otis|it|its|system|server|wifi|internet|site|phone|screen|network|everything|all|shut|slow|calm|upside|sit|lay|stand|turn|break|count|back|scroll|weekly|zero|website|page|chat|signal|thumbs|go|went|come|settle|die|wind|cool|power|powered|shutting|slowing|calming|knock|tone|turned|shuts|goes|going|broke|broken|stays|still|keeps)\b)[a-z]+('?s| is)? down\W*$/i,
  /\b(clipped|smacked|bumped|rammed|nailed|knocked over|knocked down|plowed into|backed over) (me|him|her|them|us|someone|somebody)\b/i,
  // Dizzy, blacking out, calls to be saved: "everything is spinning", "I black out", "please save me"
  /\b(everything|the room|room|my head|his head|her head)('?s| is| was| keeps| started| just)* (spinning|going black|went black|went dark|going dark)\b|\b(i|he|she|they) (black|blacked|keep blacking|am blacking|is blacking) out\b/i,
  /\bsave (me|us)\W*$|\b(please|pls|plz|someone|somebody|can you|come|help|gotta|need you to) save (me|us|him|her|them)\b/i,
  // Batteries, threats, weather
  /\b(batter(y|ies)|charger|motor|outlet|wiring|cord|engine)\b.{0,15}\b(smoking|sparking|smoldering|swelling|swollen|hissing)\b/i,
  /\bbomb\b|\bthreat(en|ened|ening|s)? (to )?(kill|shoot|stab|hurt|bomb|blow)|\bthreatened\b.{0,25}\b(kill|shoot|stab|hurt|bomb)|\b(going to|gonna|wants? to|said (he|she|they)'?d) (kill|shoot|stab)\b/i,
  /\b(thinking (about|of)|want to|wanna|going to|gonna) (ending it|end it( all)?|hurt(ing)? myself|not being here)\b/i,
  /\btornado (warning|coming|touched|on the ground|sirens?)\b|\bearthquake\b(?! (drills?|plans?|kits?|preparedness|training))|\btake shelter\b|\bshelter in place\b(?! (drills?|plans?|training))/i,
  // Electricity, burns, fire
  /\b(electr[io]?cut|being shocked|getting shocked|got shocked|got zapped|stuck to|can'?t let go|live wire)/i,
  /\b(won'?t|wont|doesn'?t|doesnt|can'?t|cant|cannot|will not|does not) let go\b/i,
  /\b(arc flash|burned|burnt|got burned|scalded|on fire|blinded|went blind)\b/i,
  /\b(chemical|acid|caustic|steam|electrical|bad|serious|severe) burns?\b|\bburns? (on|to) (his|her|my|their)\b/i,
  /\b(fire|smoke|explosion|exploded|flames|in flames|burning|blew up)\b/i,
  // Chemicals and gas
  /\b(gas|ammonia|chlorine|propane|refrigerant|carbon monoxide|co|h2s|hydrogen sulfide|chemical|acid) (leak|leaking|release|cloud|everywhere)/i,
  /\bleak(ing|ed)? (of )?(gas|ammonia|chlorine|propane|refrigerant|carbon monoxide|h2s)\b/i,
  /\bsmell(s|ing|ed)? (like |of )?(gas|propane|ammonia|chlorine|natural gas|rotten eggs?|smoke|burning)\b|\b(gas smell|smell of gas|rotten eggs?)\b/i,
  /\b(alarms?|detectors?|monitors?|sensors?|meters?)\b.{0,25}\b(going off|went off|sounding|alarming)\b/i,
  /\bchemical (in|on) (my|his|her|their) (eyes?|face|skin)\b/i,
  /\b(splash(ed)?|sprayed|squirted)\b.{0,30}\b(eyes?|face|skin)\b/i,
  /\b(acid|caustic|bleach|chemicals?|lye|chlorine|ammonia|sanitizer|degreaser|solvent)\b.{0,30}\b(eyes?|face|skin|mouth)\b/i,
  /\b(flush(ing)?|rins(e|ing)) (his|her|my|their|your) (eyes?|face|skin)\b/i,
  /\b(swallowed|ingested|poisoned|poisoning|overdos|od'd|narcan)/i,
  // Medical, heat and cold, falls
  /\b(chest pains?|heart attack|stroke|heat ?stroke|heat exhaustion|fell|fallen|fall from)\b/i,
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
  /\bse le fue la mano en (la|el) (sierra|m[aá]quina|prensa|banda|rodillo)|\bno se (levanta|para|puede levantar|puede parar)|\bdebajo del? (montacargas|cami[oó]n|tr[aá]iler|carga|rack|tarima)/i,
  /\bse (le )?rompi[oó] (el|la|un|una) (brazo|pierna|mano|pie|tobillo|mu[nñ]eca|cuello|espalda|hueso|cadera|costilla)/i,
  // First person and "man down" in Spanish: "me caí", "me quemé", "me golpeé la cabeza", "me torcí el tobillo",
  // "el montacargas me pegó", "hombre caído". Not "me cae bien" ("cae"), and not "me caigo de sueño".
  /\bme ca[iíy](?![a-záéíóúñ])|\bme (quem[eé]|golpe[eéoó]|torc[ií]|machuqu[eé]|fractur|romp[ií]|lastim[eé]|cort[eé])|\b(me|nos) (peg[oó]|atropell[oó]|aplast[oó]|machuc[oó]|cay[oó] encima)|\b(hombre|trabajador|compa\w*|persona|alguien|mujer|se[nñ]or) ca[ií]d[oa]/i,
  /\b(hubo un accidente|tuvo un accidente|accidente grave|matarse|suicid|tiene un arma|tiene una pistola)/i,
  // "me atoré la mano", "me agarró la máquina", "me pegué", "me picó un alacrán", "no siento las piernas", "se está
  // poniendo morado", "le está dando un ataque", "encerrado en el cuarto frío", "tirado en el piso", "se me fue el dedo
  // en la sierra", "sudando frío", "hay chispas en el panel", "necesito asistencia ahora"
  /\bme ator[eé]|\bse (me|le) ator[oó] (la|el) (mano|brazo|dedo|pie|pierna|manga|pelo|cabello|ropa)|\b(me|le) agarr[oó] (la|el) (m[aá]quina|banda|prensa|rodillo|cadena|sierra|polea)|\bme pegu[eé]/i,
  /\b(me|le|lo|la|nos) pic[oó] (un|una) (alacr|abeja|avispa|ara[nñ]a|v[ií]bora|culebra|serpiente|escorpi)|\bno (siento|siente|sentimos|puedo sentir|puede sentir) (las|los|mis|sus|el|la|mi|su) (piernas?|brazos?|pies?|manos?|cara|dedos?)/i,
  /\b(poniendo|puso|pone|ponen) (morad|azul|p[aá]lid)|\b(est[aá]|le) dando (un |una )?(ataque|infarto|paro|convulsi)|\bencerrad[oa]s? (en|dentro)|\btirad[oa]s? (en|sobre) el (piso|suelo)/i,
  /\bse (me|le) fue (el|la|un) (dedo|mano|brazo|pie)|\bsud(ando|or) fr[ií]o|\b(hay|salen|saca|sacando|echando|echa|saltan) chispas|\bchispas (en|del|de la)\b|\basistencia (m[eé]dica|ya\b|ahora|urgente|inmediata)/i,
  /(ácido|\bacido|qu[ií]mico|\bcloro|amon[ií]aco|\bsosa|c[aá]ustico).{0,30}(ojos?|cara|piel)/i,
  /\b(le |me )?duele\w* (mucho )?(el |la )?(pecho|coraz[oó]n)|\bpecho.{0,15}duele|presi[oó]n en el pecho|\bmare(ad[oa]s?|ando|o\b)|\bse marea|\bv[oó]mit|\bdesorientad|\ba punto de desmay|\bpicad[oa] por|\bmordid[oa] por|\bamenaz[oó] (con )?(matar|disparar)|\bamenaza de bomba/i,
  // Round 3: cries made only of the app's words ("it shut on me", "get me out", "it got me", "something went off"),
  // a crash that is not the app's, blows and falls told plainly, and Spanish "él" (he) typed without the accent
  /\b(shut|shuts|slammed shut)( back)? (on|onto|over) (him|her|them|me|us|someone|somebody|my|his|their)\b|\b(it'?s|its|it is) on (me|him|her|my|his)\W*$/i,
  /\b(get|let|help) (me|us|him|her|them) out\b(?! of (the |this |my )?(app|talk|screen|page|video|chat|otis|account|menu|loop|sheet)\b)|\bcome get (me|us|him|her)\b|\bget (it|this|that|them) off (me|him|her|us)\b/i,
  /\b(it|something|somethin|a bug|bugs|bees?|wasps?|a snake|a dog|the dog|the machine|the belt|that thing) (got|grabbed|caught) (me|him|her|us)\b(?! (logged|kicked|signed|booted|confused|thinking|wondering|out of))/i,
  /\bwent in\b.{0,25}\b(aint|ain'?t|isnt|isn'?t|not|hasnt|hasn'?t|never|wont|won'?t|didn'?t|didnt) (coming|come|came|comin)( back)? out\b|\b(something|somethin|it|stuff) (just )?went off\b/i,
  /\b(there was|there'?s been|theres been|there has been|we had|just had|heard) an? (big |bad |loud |huge |real )?crash\b(?! reports?\b)|\b(big|huge|loud|terrible|serious|major|massive) crash\b(?! reports?\b)/i,
  /\b(got|was|been|get|gets|just got) (hit|smacked|struck|nailed|whacked) (in|on) (the|my|his|her|their) (head|face|eyes?|chest|back|neck|legs?|arms?|hands?|throat|mouth|stomach|ribs?)\b|\b(got|was|been|just got) hit (by|with) (a|an|the|some) (?!(update|notification|error|bug|glitch|ad|popup|message)s?\b)\w+/i,
  /\b(hangin'?|hanging|dangling|suspended) (in|from|by|on|off) (his|her|their|the|a|my) (harness|lanyard|rope|lifeline|line|srl)\b|\b(guy|he|she|someone|somebody|man|woman|worker|person|dude|buddy|partner|hes|shes|he'?s|she'?s)\b.{0,12}\b(hanging|hangin'?|dangling) (off|from|over|out of) (the |a )?(side|edge|roof|ledge|trailer|truck|scaffold\w*|lift|platform|railing|rail|bucket|basket|window|beam|mezzanine|catwalk)/i,
  /\bon the (ground|floor|dirt) (shaking|twitching|jerking|convulsing|seizing|foaming)\b|\b(sitting|standing|weight|pressure|elephant) on (my|his|her|their) chest\b/i,
  /\bgash(ed|es)?\b|\bkicked back (into|on|and hit) (my|his|her|their|him|me)\b/i,
  /\bsomething('?s| is)? (really |very |seriously )?wrong with (me|him|her)\b|\b(i|he|she) (can'?t|cant|cannot) move\b|\bon top of (me|him|her|us)\b|\b(hanging|stuck|pinned|leaning|sitting) (over|on) (me|him|her)\W*$|\b(it'?s|its|it is|keeps) pulling (me|him|her)\b|\b(i|he|she) (don'?t|dont|doesn'?t|doesnt) feel (right|well)\b/i,
  // Spanish, round 3: "se volteó el montacargas", "me cayó ácido en el brazo", "él no sale", "mi compa no contesta",
  // "él se quedó pegado", "se pone blanco", "entró y ya no sale", "no veo"
  /\bse volte[oó] (el|la) (montacargas|cami[oó]n|carro|tractor|gr[uú]a|tr[aá]iler|camioneta|patin|plataforma|andamio|elevador)|\b(montacargas|cami[oó]n|carro|tractor|gr[uú]a|tr[aá]iler|camioneta) se volte[oó]/i,
  /\b(me|le|nos|les) ca(y|ll)[oó] (el |la |un |una |algo de |algo |encima |en )?(ácido|acido|qu[ií]mic|cloro|sosa|c[aá]ustic|aceite|agua caliente|vapor|metal|viga|tubo|caja|carga|tabla|pieza|piedra|fierro|hierro|encima|soldadura)/i,
  /(ácido|\bacido|qu[ií]mico|\bcloro|amon[ií]aco|\bsosa|c[aá]ustico).{0,30}(brazos?|manos?|piernas?|pies?|cuello|boca|dedos?)/i,
  /(?:^|[^a-záéíóúñ])(el|él|ella|compa\w*|compañer[oa]|companer[oa]|se[nñ]or[a]?|chavo|trabajador[a]?|operador[a]?|soldador[a]?|chofer|hombre|mujer) (ya )?no (sale|contesta|aparece|ve|responde|despierta|habla|se mueve|reacciona|se ve bien)/i,
  /(?:^|[^a-záéíóúñ])(el|él|ella|compa\w*|compañer[oa]|companer[oa]|se[nñ]or[a]?|chavo|trabajador[a]?|operador[a]?|soldador[a]?|chofer|hombre|mujer) (se )?(qued[oó]|queda|pone|puso|est[aá] poniendo|va|anda|se ve|ve) (muy |bien |todo )?(pegad|atorad|atrapad|ties[oa]|blanc|gris|morad|azul|p[aá]lid|fr[ií]o|mal(?![a-záéíóúñ]))/i,
  /\bno (me )?puedo (salir|mover)|\bno me puedo mover|\bme qued[eé] (pegad|atorad|atrapad|encerrad)|\bdescarga (el[eé]ctrica|no (para|se detiene|se quita|se va))|\bhay una descarga(?! de (la app|otis))|\bentr[oó](?![a-záéíóúñ]).{0,25}\bno (ha )?sal(e|ido|i[oó])|(?:^|\s)(ya )?no (veo|vemos|puedo ver)( nada| bien)?\W*$/i,
  // Round 4: people told as numbers ("otis 1 is down", "2 down", "i have 2 missing", "1 got stuck", "1 no sale"), out of
  // touch ("lost contact with 2", "no answer in there"), things coming down, high up, going down or going black, not
  // knowing where you are, giving up, and a few plain misses ("he went in the tank 10 min ago and wont answer")
  /(?<!\b(?:version|step|page|error|code|ios|android|talk|episode|level|option|chapter|part|iphone|pixel|galaxy|v)\s)\b\d+\s+(is |are |was |were |of mine (is |are )?|of (my|our) (guys|crew|men|workers|people) (is |are )?)?(down|missing|not answering|unresponsive|gone|hurt|stuck|trapped|pinned|lost|not breathing|not moving|hanging|frozen|freezing)\b/i,
  /\b(i |we )?(have|got|has|tengo|hay) \d+ (down|missing|hurt|stuck|trapped|pinned|pegad|atorad|atrapad|herid|tirad|ca[ií]d)/i,
  /(?<!\b(?:version|step|page|error|code|ios|android|talk|episode|level|option|chapter|part|v)\s)\b\d+ (got|get|is|are|just got|was) (stuck|trapped|pinned|caught|hurt|hit|lost)\b|^\W*(otis\W+)?\d+ down\W*$/i,
  /(?<![a-záéíóúñ])\d+ (ya )?no (sale|contesta|aparece|responde|se mueve|despierta|reacciona)|(?<![a-záéíóúñ])(\d+|otis) (est[aá]|se queda|sigue|se qued[oó]|qued[oó]) pegad/i,
  /\b(he|she|they|he'?s|hes|she'?s|shes|they'?re|guy|man|woman|worker|partner|co-?worker|buddy|entrant|attendant|operator|driver)\b.{0,40}\b(not|isn'?t|isnt|ain'?t|aint|aren'?t|stopped|won'?t|wont|quit|no longer) (answering|answerin|answer|talking|talkin|responding|respondin|moving|movin|getting up|gettin up|breathing|breathin)\b/i,
  /\blost (contact|connection|signal|radio contact|comms|sight|track) (with|of) (?!(the )?(server|app|internet|wifi|wi-?fi|network|otis)\b)|\blost contact\b|\bno answer (from (?!(otis|the app|it)\b)|in there)|\b(not answering|not responding|no answer|stopped answering)\b.{0,30}\bin there\b/i,
  /\b(it all|everything|all of it|its all|it'?s all|it is all|the whole thing)( just)? (crash\w*|came|coming|comes|fell|falling|caved|caving) (down|in)\b|\bstuck up (there|top|high|here)\b/i,
  /\b(i'?m|i am|im)( about to| gonna| going to| think i'?m| think i am)? (going|go|gonna go|goin) down\b|\bi think (i'?m|i am|im) going down\b|\b(i'?m|im|i am) (all )?(out of it|messed up|not right)\b|\bsomething('?s| is)? (going on|happening|wrong) (with|to) me\b/i,
  /\b(things|it all|its all|it'?s all|it is all|everything is all|all)( is| are| was| keeps| started| just)* (going|went|gone|turning|turned|getting) (black|dark|white|blurry|fuzzy)\b|\ball i (can )?see is (black|white|dark|blurry|stars|red)\b/i,
  /\b(don'?t|dont|do not|can'?t|cant|cannot) (know|tell) where (i|we) (am|are)\b|\bwhere am i\b/i,
  /\bi give up\b|\b(can'?t|cant|cannot) (do|take|handle) (this|it) any ?more\b|\bno (puedo|aguanto) m[aá]s|^\W*(otis\W+)?(ya )?no (puedo|aguanto)( m[aá]s)?\W*$|\by (ya )?no puedo( m[aá]s)?\W*$|\bya no aguanto/i,
  /\bchest (is |feels |feel )?(crushing|crushed|being crushed)\b|\b(my|his|her|their) (left )?(arm|arms|face|jaw|side) (is |are |went |goes |feels |feel |is going |going )?(numb|tingling|tingly|dead)\b|\bwe crashed\b/i,
  /\b(can'?t|cant|cannot|couldn'?t|could not) get (?!(logged|signed|kicked|booted|it|this|that|otis|the app|in|on|into|through)\b)\w+ out\b|\b(gas|ammonia|propane|chlorine|chemical|sulfur|rotten egg|burning) (smell|odor|odour)\b/i,
  // Spanish, round 4: "mi compita ya no está respirando", "se rebanó el dedo", "se acaba de caer", "no tengo aire",
  // "me quedó pegado", "entró y ya no contesta", "se quedó pegado", "se ve muy mal", "ya no veo bien nada", "ya no sale"
  /\bno (est[aá] )?respirando|\bya no respira|\bse (rebanaron|reban[oó]|vol[oó]|machuc[oó]|aplast[oó]|prens[oó]) (el|la|un|una|los|las|sus?) (dedos?|manos?|brazos?|pies?|piernas?|u[nñ]as?|cabeza)|\bse (acaba|acaban|acab[oó]) de caer|\bse (est[aá]|va) cayendo/i,
  /\bno (tengo|tiene|hay|tenemos) aire\b|\b(me|le|nos) falta (el )?aire|\bme qued[oó] (pegad|atorad|atrapad|encerrad)|\bentr[oó](?![a-záéíóúñ]).{0,25}\bno (ha )?(contesta|responde|se oye|se escucha|regresa|ha regresado|vuelve)|\by (ya )?no se (oye|escucha|ve bien)\b/i,
  /(?<!\b(celular|tel[eé]fono|cel|app|aplicaci[oó]n|pantalla|video|sistema)\s(\w+\s)?)\bse qued[oó] (pegado|atorado|atrapado|encerrado|tieso|tirado|colgado)\b|(?<!\b(app|aplicaci[oó]n|pantalla|charla|respuesta|p[aá]gina|hoja|conexi[oó]n|se[nñ]al|internet|wifi|celular|tel[eé]fono|video)\s(\w+\s){0,2})\b(est[aá]|anda|se ve|va) muy mal\b/i,
  /\bno (veo|vemos|puedo ver) (bien )?nada\b|\bno (veo|vemos) bien\W*$|^\W*(otis\W+)?(ya )?no (sale|aparece)( nada)?\W*$|\bno sale y (ya )?no contesta|\by (ya )?no sale\W*$|^\W*(ya )?no contesta\W*$/i,
  /\by (ya )?(est[aá]|se qued[oó]|sigue) pegado\b|^\W*(otis\W+)?(ya )?(est[aá]|sigue|se qued[oó]) pegado\W*$|\by (est[aá]|anda|se ve) (muy )?mal\W*$|\b(me|le|lo|la|nos) pega\b/i,
  /\b(i|he|she|i just|he just|she just) (went|go|going) (black|blank|dark|white|down)\b|\b(i|i just) keep (going|passing|blacking) (down|out)\b|\b(all of mine|mine|all of them|all my (guys|crew|men))( is| are)? (all )?(down|missing|not answering|gone)\b/i,
  /(?<![a-z])\d+ (are |is )?still missing\b|\b\d+ (got|is|was) frozen\b|\bso (is|are) \d+ of (mine|my|ours)\b|\b(stuck|caught|jammed|pinned|trapped|frozen)\b.{0,25}\bso (is|are) (my|his|her|their) (hands?|arms?|legs?|foot|feet|fingers?|head|hair|sleeve|glove)\b/i,
  /\b(i'?m|im|i am|we'?re|were|we are|he'?s|she'?s|hes|shes) (still )?(in|inside) there\b.{0,30}\b(frozen|freezing|black|dark|stuck|locked|cold)\b|\b(frozen|freezing|black|dark|stuck|locked)\b.{0,30}\b(i'?m|im|i am|we'?re|we are) (still )?(in|inside) there\b|\b(its|it'?s|it is) (all )?(black|dark|pitch black) in (there|here)\b/i,
  /\b(its|it'?s|it is|everything is|everything'?s) (all )?(coming|falling) apart\b|\b(its|it'?s|it is) on top\W*$/i,
  /\b(started|turned on|came on|kicked on|fired up|powered up)\b.{0,30}\b(i'?m|im|i am|he'?s|hes|she'?s|shes|we'?re|were|they'?re) still (in|inside|on it|under)\b|\bwith (me|him|her|them|us|someone|somebody) (still )?(in|inside|under|on) (it|there|top)\b|\bcrushing (me|him|her|them|us|my|his|their)\b/i,
  /\bno (lo|la|los|las|le) (veo|vemos|encuentro|encontramos|oigo|escucho|oimos)\b(?! (en|dentro de) (la app|la aplicaci[oó]n|otis|el celular|mi celular|el tel[eé]fono|la pantalla|la lista|el men[uú])\b)|\b(we|i) (lost|lose|losing) (him|her|them)\b|\b(it all|everything|all of it) (just )?(went|came|fell) down\b|\b(froze|crashed|went down|fell|blacked out|passed out) and so did (i|he|she|they)\b/i,
  // "What do I do now", said on its own: an emergency as often as anything. Not "what do I do if the app crashes".
  /^\W*(otis\W+)?(so |ok |okay |and |now )?(what (do|should|can) (i|we) do( now)?|now what( do (i|we) do)?|what now|qu[eé] (hago|hacemos)( ahora)?|y ahora qu[eé]( hago)?|ahora qu[eé]( hago)?)\W*$|\bwhat (do|should) (i|we) do,? (its|it'?s|it is) (stuck|frozen|on|running|jammed|still on)\b/i,
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
