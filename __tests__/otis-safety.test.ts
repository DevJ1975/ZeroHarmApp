/**
 * looksUrgent() is the "911 rail": a hard regex check that must fire before OTIS answers whenever a
 * message sounds like someone is hurt or in danger right now. A miss (someone hurt, no 911 prompt) is
 * far worse than a false alarm, so misses are listed first.
 *
 * Every case below was run against lib/otis/safety.ts. Any case that behaves wrongly is marked
 * test.failing('BUG: ...') and asserts the CORRECT behaviour, so it turns red (unexpected pass) once fixed.
 */
import { looksUrgent } from '@/lib/otis/safety';

describe('looksUrgent: clear emergencies fire (English)', () => {
  test.each([
    "He's not breathing",
    "he can't breathe",
    'my coworker is unconscious',
    'he passed out on the line',
    'he collapsed by the press',
    'she is having a seizure',
    'there is blood everywhere',
    "he's bleeding badly",
    'his arm is caught in the conveyor',
    'worker trapped in a trench',
    'he is pinned under the pallet',
    'his hand got crushed',
    'he got electrocuted',
    'she is being shocked and can\'t let go',
    'there is a fire in the paint booth',
    'smoke is coming out of the panel',
    "there's a gas leak",
    'chemical in his eyes',
    'chemical on her skin',
    'I have chest pain',
    'I think he is having a heart attack',
    "he's having a stroke",
    'he fell from the scaffold',
    'he fell off the ladder',
    'call 911',
    'EMERGENCY at bay 4',
    'help me, he is hurt',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: clear emergencies fire (Spanish)', () => {
  test.each([
    'No respira',
    'está inconsciente',
    'está sangrando mucho',
    'quedó atrapado en la máquina',
    'se electrocutó',
    'hay un incendio en la bodega',
    'hay fuego',
    'se desmayó',
    'tiene dolor de pecho',
    'se cayó del andamio',
    'se cayo del techo', // no accent, as people type on a phone
    'emergencia',
    '¡ayuda!',
    // 'ahora mismo' ("right now") is NOT asserted here: on its own it is not an emergency, and
    // locking it in as a must-fire would fight any fix for false alarms like "I need it right now".
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: former MISSES (someone may be hurt) now fire', () => {
  // Fixed: URGENT now covers generic injury words ("hurt", "injured", "man down"), choking, burns,
  // arc flash, tip-overs/struck-by, splash wording, other gas leaks, swallowing, and a bare "fell".
  test.each([
    ['someone is hurt', 'no "hurt"/"injured" pattern (safety.ts:5-13)'],
    ['someone got hurt', 'no "hurt"/"injured" pattern (safety.ts:5-13)'],
    ['he is injured', 'no "hurt"/"injured" pattern (safety.ts:5-13)'],
    ['man down in aisle 3', 'no "man down" pattern (safety.ts:5-13)'],
    ["he's not responding", 'only "unresponsive" is matched, not "not responding" (safety.ts:6)'],
    ['He is choking', 'no choking pattern (safety.ts:6)'],
    ['chemical splash in his eyes', '"chemical (in|on)" requires the word in/on right after chemical (safety.ts:9)'],
    ['chemical splashed in my eyes', '"chemical (in|on)" requires the word in/on right after chemical (safety.ts:9)'],
    ['arc flash just happened', 'no arc flash / burn pattern (safety.ts:8)'],
    ['he burned his hand on the furnace', 'no burn pattern (safety.ts:5-13)'],
    ["forklift tipped over and he's under it", 'no tip-over / struck-by / run-over pattern (safety.ts:7)'],
    ['ammonia leak in the engine room', 'only "gas leak" is matched (safety.ts:9)'],
    ['he swallowed bleach', 'no poisoning/ingestion pattern; only "overdose" (safety.ts:10)'],
    ['he fell and hit his head', 'only "fell from" / "fell off" are matched, not a bare "fell" (safety.ts:10)'],
  ])('fires for %p (was: %s)', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // Fixed: the stems "amputat" / "electrocut" no longer sit inside a trailing \b, so they match
  // "amputated", "amputation", "electrocuted".
  test.each([
    'he amputated his finger on the saw',
    'possible amputation at line 2',
    'he got electrocuted on the panel',
  ])('stem matches inside the word: %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // Fixed: Spanish line has no trailing \b (it blocked accents and attached pronouns like "-me").
  test.each([
    ['no puede respirar', 'only "no respira" is matched, not "no puede respirar" (safety.ts:11)'],
    ['no se mueve', 'no "not moving" pattern in Spanish (safety.ts:11)'],
    ['lo aplastó la prensa', 'no Spanish crush pattern (aplast-) (safety.ts:11)'],
    ['se quemó con el ácido', 'no Spanish burn pattern (quem-) (safety.ts:11)'],
    ['¡auxilio!', 'only "ayuda" is matched, not "auxilio" (safety.ts:12)'],
    // "ay[uú]da\b" on safety.ts:12 needs a word boundary right after "ayuda", so the attached
    // pronoun in the most common Spanish cry for help ("ayúdame" = "help me") blocks the match.
    ['¡ayúdame!', '"ay[uú]da\\b" rejects the attached "-me" (safety.ts:12)'],
    ['ayudame por favor', '"ay[uú]da\\b" rejects the attached "-me", typed without accent (safety.ts:12)'],
    ['¡ayúdenme!', '"ay[uú]da\\b" rejects the attached "-nme" (plural "help me") (safety.ts:12)'],
  ])('fires for Spanish %p (was: %s)', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // Fixed: a bare "help" fires, not only "help me".
  test('a bare "HELP" fires', () => {
    expect(looksUrgent('HELP')).toBe(true);
    expect(looksUrgent('help')).toBe(true);
  });
});

describe('looksUrgent: ordinary safety questions do not fire', () => {
  test.each([
    'what is the lockout tagout procedure',
    'how often should harnesses be inspected',
    'what PPE do I need for grinding',
    'how do I store chemicals',
    'what does OSHA 1910.147 cover',
    "what's the right way to lift a box",
    'silica exposure limits',
    'how do I do confined space entry',
    'configure the firewall',
    'is a bonfire allowed on site',
    'fireman carry technique',
    '',
  ])('does not fire for %p', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });
});

describe('looksUrgent: former FALSE ALARMS on routine questions stay quiet', () => {
  // Fixed: known non-emergency phrases (SAFE_PHRASES) are stripped from a copy of the text before
  // matching, so routine program and housekeeping questions no longer trip the 911 banner.
  test.each([
    ['fire extinguisher inspection', 'bare "fire" (safety.ts:9)'],
    ['what goes in a fire prevention plan', 'bare "fire" (safety.ts:9)'],
    ['where is the smoke break area', 'bare "smoke" (safety.ts:9)'],
    ['how often do we test the smoke detectors', 'bare "smoke" (safety.ts:9)'],
    ['what goes in an emergency action plan', 'bare "emergency" (safety.ts:12)'],
    ['emergency eyewash station requirements', 'bare "emergency" (safety.ts:12)'],
    ['when is the next fire drill', 'bare "fire" (safety.ts:9)'],
    ['how do I prevent a fall from a ladder', '"fall from" matches fall-protection questions (safety.ts:10)'],
  ])('does not fire for %p (was: %s)', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });

  test.each([
    'fire exit signage requirements',
    'who is on fire watch tonight',
    'emergency exit lighting test',
    'how do I test the emergency stop',
    'fall protection training',
    'arc flash PPE categories',
  ])('does not fire for routine %p', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });
});

describe('looksUrgent: safe phrases never hide a real emergency in the same message', () => {
  // Safe phrases are stripped, never used to veto the whole message.
  test.each([
    "there's a fire, where's the fire extinguisher",
    'smoke everywhere, the smoke detector is going off',
    'he fell, we had fall protection on',
    'emergency! the emergency stop did not work and his arm is caught',
    'used the emergency eyewash but he still cannot see, chemical splashed in his eyes',
    'arc flash PPE was on but he got burned',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: more real-world emergency phrasings', () => {
  test.each([
    'she fainted',
    "he won't wake up",
    "he's turning blue",
    'allergic reaction, bee sting',
    'deep cut on his arm',
    'he cut off his finger',
    'I think he broke his arm',
    'forklift ran over his foot',
    'he got hit by a forklift',
    'the pallet fell on him',
    "he's hanging in his harness",
    'chlorine leak at the pool pump',
    'propane leaking from the tank',
    'he drank and swallowed degreaser',
    'he got shocked',
    'she has heat exhaustion',
    'he got scalded by steam',
    'the tank exploded',
    'worker down by the kiln',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  test.each([
    'está herido',
    'se lastimó la mano',
    'se está ahogando',
    'fuga de amoniaco',
    'se tragó cloro',
    'le dio una descarga eléctrica',
    'lo atropelló el montacargas',
    'se cortó el dedo',
    'no despierta',
    'se quemo la mano', // no accent
    'quemadura en el brazo',
    '¡socorro!',
    'ayudenme', // no accent
  ])('fires for Spanish %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: panic typing, slang and typos (review round 2)', () => {
  // Fixed: each of these was a MISS before the review. They are how a frontline worker types in a
  // panic: lowercase, no apostrophes, slang, misspellings.
  test.each([
    // someone down
    'dude is down', 'guy down on line 4', 'hes down', 'she went down hard', 'someone is lying on the floor',
    'hes unconcious', 'she passed-out', 'he blacked out', 'he got knocked out', 'hes seizing', 'he has a siezure',
    'he is dead', 'i think hes dead', 'head injury',
    // breathing and heart
    'he cant breath', 'he cannot breathe', 'she is having trouble breathing', 'he aint breathing', 'he stopped breathing',
    'no pulse', 'start cpr', 'where is the aed', 'his heart stopped', 'cardiac arrest', 'heartattack', 'hes chocking',
    // calls for help
    'somebody call an ambulance', 'call 9-1-1', 'HELPPP', 'we need a medic', 'he needs first aid',
    // bleeding, caught, crushed, struck
    'hes bleedin', 'theres blood', 'so much blood', 'finger got cut off', 'his hand got smashed', 'degloved finger',
    'his hand is in the roller', 'his glove got caught and pulled his hand in', 'forklift hit someone',
    'he hit his head', 'she slipped and hit her head', 'he has fallen', 'struck by a falling pallet',
    'trench caved in on him', 'forklift flipped', 'the forklift rolled', 'forklift crash',
    'broken leg', 'i think his leg is broken', 'bone sticking out', 'he has a fractured wrist',
    'he is dangling from his lanyard', 'his lanyard snapped',
    // electricity, burns, fire
    'he got zapped by the panel', 'he touched a live wire', 'he got electricuted', 'chemical burn on his arm',
    'he has burns on his hands', 'flames coming out of the fryer', 'something is burning', 'the motor blew up',
    // gas and chemicals
    'i smell gas', 'smells like gas in here', 'ammonia everywhere', 'leaking ammonia', 'co alarm going off',
    'the gas monitor is going off', 'smoke detectors going off', 'acid got in his eyes', 'bleach in his eyes',
    'flush his eyes', "he od'd", 'overdosing in the bathroom',
    // stroke signs, violence, self-harm, accidents
    'his face is drooping and hes slurring', 'he got stabbed', 'someone has a gun', 'active shooter',
    'he says he wants to kill himself', 'there was an accident', 'bad accident on dock 2',
    'we are evacuating', 'evacuate the building',
    // trapped
    'the fire door is stuck and we cant get out', 'emergency exit is locked and we cant get out',
    'he is locked in the freezer',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // Fixed: Spanish misses (misspellings like "se callo", "inconciente", "desmallo" are common on phones).
  test.each([
    'se desmallo', 'le dio un choque', 'le dio corriente', 'le dio un toque electrico', 'no puedo respirar',
    'no reacciona', 'no responde', 'se callo del andamio', 'cayó del techo', 'le cayó una tarima encima',
    'hay humo', 'huele a gas', 'olor a gas', 'fuga de químico', 'quedó prensado', 'se le atoró la mano',
    'lo atrapó la máquina', 'le agarró la mano la máquina', 'perdió un dedo', 'se amputó el dedo',
    'le pegó el montacargas', 'se golpeó la cabeza', 'está convulsionando', 'le dio un infarto', 'paro cardiaco',
    'llamen una ambulancia', 'explotó la caldera', 'está inconciente', 'hay un insendio', 'está muerto',
    'se está muriendo', 'le cayó ácido en los ojos', 'se rompió el brazo', 'se fracturó la pierna',
    'está en llamas', 'se está quemando', 'hubo un accidente', 'le dio un ataque al corazón', 'derrame de cloro',
    'quiere matarse', 'tiene un arma', 'el montacargas se volcó',
  ])('fires for Spanish %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: emergencies told with a safe phrase\'s own words', () => {
  // Fixed: these are checked on the full message (IN_PROGRESS) before safe phrases are stripped.
  // Before, stripping "fire extinguisher" / "fall arrest" / "emergency stop" left nothing to match.
  test.each([
    'we grabbed a fire extinguisher but its still going',
    'i used the fire extinguisher on it',
    'his fall arrest deployed and hes hanging',
    'his fall protection failed',
    'get him to the eyewash now',
    "she's in the emergency shower",
    'we activated the emergency action plan',
    'we pressed the e-stop',
    'i hit the emergency stop his arm is caught',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // Stripping only removes the safe phrase; anything urgent next to it still fires.
  test.each([
    'fire in the fire extinguisher cabinet room',
    'he collapsed during the fire drill',
    'the fire door is on fire',
    'fire extinguisher exploded',
    'during fire watch i saw flames',
    'emergency exit blocked and hes not breathing',
    'arc flash PPE melted and he has burns on his face',
    'what is an arc flash, he just got hit by one',
    'first aid kit is empty and hes bleeding',
    'trapped key is stuck and his hand is caught',
    'electrocution hazards! he got shocked',
    'suicide prevention line, i want to kill myself',
    'smoke detector batteries are dead and theres smoke',
    'AED training, he has no pulse',
    'bloodborne kit, hes bleeding',
    'plan de emergencia: hay fuego',
    'simulacro de incendio pero se desmayo',
    'extintor de incendio no funciona, hay humo',
  ])('fires for %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });
});

describe('looksUrgent: more ordinary safety questions stay quiet (review round 2)', () => {
  // Fixed: OSHA Focus Four / program names were false alarms ("caught in", "electrocut", "amputat",
  // "trapped", bare "emergencia"); they are now SAFE_PHRASES.
  test.each([
    'what are caught in between hazards',
    'what are caught-in or -between hazards',
    'how does a trapped key interlock work',
    'electrocution hazards on a jobsite',
    'amputation hazards on a press',
    'what is an arc flash',
    'where is the emergency assembly point',
    'test the smoke alarms',
    'plan de emergencia',
    '¿dónde está la salida de emergencia?',
    'simulacro de incendio',
    'lavaojos de emergencia',
    'extintores de incendio',
  ])('does not fire for %p', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });

  test.each([
    'how often do forklifts need inspection', 'what is the OSHA rule for guardrail height', 'what PPE for welding',
    'how do I fill out a JSA', 'toolbox talk on heat stress', 'how do I inspect a harness before use',
    'who do I report a near miss to', 'when is my CPR training due', 'where do I find the SDS for bleach',
    'how do I use a fire extinguisher', 'how often should eyewash stations be flushed', 'first aid kit requirements',
    'bloodborne pathogens training', 'what is a wheel chock', 'chocking the wheels on a trailer',
    'flame resistant clothing requirements', 'how do I bleed the hydraulic lines', 'suicide prevention training',
    'aed inspection checklist', 'how do I write an accident report', 'smoke detector batteries',
    'fall arrest system inspection', 'how do I calibrate the gas monitor', 'what is a bump test for a gas detector',
    'where is the emergency stop', 'how often should lanyards be replaced', 'how do I prevent electrocution',
    'active shooter training', 'how do I troubleshoot the conveyor', 'sense of humor in toolbox talks',
    '¿cómo uso el extintor?', '¿qué EPP necesito para soldar?', '¿dónde está el botiquín?', 'paro de emergencia',
    'ruta de evacuación', 'prevención de incendios', '¿cómo se usa el lavaojos?',
  ])('does not fire for routine %p', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });
});

describe('looksUrgent: input handling', () => {
  test('is case-insensitive', () => {
    expect(looksUrgent('HE IS NOT BREATHING')).toBe(true);
    expect(looksUrgent('NO RESPIRA')).toBe(true);
  });

  test('gives the same answer on repeated calls (no regex state carried between messages)', () => {
    // A /g flag on any URGENT regex would make .test() resume from lastIndex and alternate results.
    const results = [1, 2, 3].map(() => looksUrgent('he collapsed'));
    expect(results).toEqual([true, true, true]);
    expect(looksUrgent('what PPE do I need for grinding')).toBe(false);
    expect(looksUrgent('he collapsed')).toBe(true);
  });

  test('finds the emergency inside a longer message', () => {
    expect(
      looksUrgent('Quick question about the forklift checklist, actually wait, Tony collapsed near dock 2'),
    ).toBe(true);
  });
});
