/**
 * looksUrgent() is the "911 rail": a hard regex check that must fire before OTIS answers whenever a
 * message sounds like someone is hurt or in danger right now. A miss (someone hurt, no 911 prompt) is
 * far worse than a false alarm, so misses are listed first.
 *
 * Every case below was run against lib/otis/safety.ts. Cases that currently behave wrongly are marked
 * test.failing('BUG: ...') and assert the CORRECT behaviour, so they turn red (unexpected pass) once fixed.
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

describe('looksUrgent: known MISSES (someone may be hurt, no 911 prompt)', () => {
  // Each of these returns false today. Not a single pattern in URGENT (lib/otis/safety.ts:5-13)
  // covers generic injury words ("hurt", "injured", "man down"), choking, burns, arc flash,
  // tip-overs/struck-by, splash wording, or most Spanish injury verbs.
  test.failing.each([
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
  ])('BUG: misses %p - %s', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  // "amputat" is a stem, but the group is wrapped in a trailing \b (safety.ts:7), so it only matches
  // the non-word "amputat" itself. "amputated" / "amputation" never fire. Same dead stem for
  // "electrocut" on safety.ts:8; that one is masked only because the Spanish line (safety.ts:11) has
  // no trailing \b and happens to catch "electrocuted".
  test.failing.each([
    'he amputated his finger on the saw',
    'possible amputation at line 2',
  ])('BUG: stem "amputat" never matches because of the trailing \\b (safety.ts:7): %p', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  test.failing.each([
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
  ])('BUG: misses Spanish %p - %s', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  test.failing('BUG: a bare "HELP" does not fire, only "help me" (safety.ts:12)', () => {
    expect(looksUrgent('HELP')).toBe(true);
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

describe('looksUrgent: known FALSE ALARMS on routine questions', () => {
  // Bare "fire" / "smoke" / "emergency" on safety.ts:9 and :12 match routine program and
  // housekeeping questions, which teaches workers to ignore the 911 banner.
  test.failing.each([
    ['fire extinguisher inspection', 'bare "fire" (safety.ts:9)'],
    ['what goes in a fire prevention plan', 'bare "fire" (safety.ts:9)'],
    ['where is the smoke break area', 'bare "smoke" (safety.ts:9)'],
    ['how often do we test the smoke detectors', 'bare "smoke" (safety.ts:9)'],
    ['what goes in an emergency action plan', 'bare "emergency" (safety.ts:12)'],
    ['emergency eyewash station requirements', 'bare "emergency" (safety.ts:12)'],
    ['when is the next fire drill', 'bare "fire" (safety.ts:9)'],
    ['how do I prevent a fall from a ladder', '"fall from" matches fall-protection questions (safety.ts:10)'],
  ])('BUG: fires for %p - %s', (text) => {
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
