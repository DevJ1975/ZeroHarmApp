/**
 * The order OTIS answers in, run against the knowledge base the server really sends (GET /api/v2/otis/kb with the
 * seeded entries, saved in __tests__/fixtures/otis-kb-served.json): the 911 rail, then the app-problem rule and the
 * support entries, then the safety search. This is the same routeQuestion() the chat screen calls.
 *
 * To refresh the fixture: migrate a temporary SQLite database with the backend, then save the body of
 * GET /api/v2/otis/kb (Django test client with HTTP_HOST=127.0.0.1) to that file.
 */
import served from './fixtures/otis-kb-served.json';
import questions from './fixtures/support-questions.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion } from '@/lib/support/answer';
import { looksSpanish } from '@/lib/otis/prompt';

jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() } }));
jest.mock('@/lib/otis/manifest', () => ({ kbVersionKey: 'otis_kb_version' }));

const KB = (served as { items: KbItem[] }).items;
const lang = (q: string) => (looksSpanish(q) ? 'es' : 'en');
function answer(q: string) {
  const urgent = looksUrgent(q);
  return { urgent, ...routeQuestion(KB, q, lang(q), urgent) };
}

test('the fixture is the full served payload', () => {
  expect(KB.length).toBeGreaterThan(200);
  expect(KB.filter((d) => d.kind === 'support').length).toBeGreaterThan(30);
});

// Item 0 and 11: emergencies the old order sent to tech support.
const EMERGENCIES = [
  'the press glitched and came down on his hand',
  'the light curtain glitched and the press cycled on her arm',
  'the gas monitor screen went blank and Tom is not answering from inside the tank',
  'the crew got no notification and they started the line with Luis still working on it',
  'the buggy rolled on top of him',
  'a guy is stuck at the loading dock between the trailer and the wall',
  'his arm is stuck on the loading conveyor',
  'a rack came down on top of Mike',
  'his lips are blue',
];

describe('emergencies: banner, then the safety answer, never a support path', () => {
  test.each(EMERGENCIES)('%p', (q) => {
    const r = answer(q);
    expect(r.urgent).toBe(true);
    expect(r.kind).toBe('safety');
  });
});
const MISSES = [
  'his sleeve wrapped around the drill and it is pulling him in',
  'the trench wall gave way with a guy inside',
  'he is shaking and foaming at the mouth',
  'she drank the degreaser',
  'he touched the busbar and dropped',
  "she isn't answering me and her eyes are closed",
  'Mike is under the forklift',
  'the pallet landed on his foot and he is screaming',
  'he went into the tank and has not come out',
  'the saw took two of his fingers',
  'she got sprayed with ammonia',
  'he is stuck in the baler',
  'se le fue la mano en la sierra',
  'no se levanta del piso',
  'the screen went black and he is not answering',
  'my phone froze and my partner is still in the tank and not answering',
  'the app froze, he is not answering on the radio from inside the vessel',
];
test.each(MISSES)('rail now catches %p', (q) => {
  expect(answer(q).urgent).toBe(true);
  expect(answer(q).kind).toBe('safety');
});

// Items 2, 3, 4, 10 and 15: safety questions the old rules took as app problems.
const SAFETY_QUESTIONS = [
  // 2: "report a problem" followed by a hazard
  'I need to report a problem, the guard on the saw is missing',
  'I want to report an issue. There is a spill in aisle 4',
  'How do I report a problem? My supervisor ignores safety complaints',
  'report a problem: the dock plate is cracked',
  'I have to report an issue, who do I tell about a frayed sling',
  '¿Dónde reporto un problema?',
  'necesito reportar un problema, el montacargas no tiene frenos',
  'quiero reportar un problema. La guarda de la sierra no está',
  'forklift 3 has no brakes and they are still using it',
  // 3: screens, sheets, videos, links, signatures on equipment and paperwork
  'the gas monitor screen is blank, can I still enter the tank?',
  'the forklift display screen went black, is it safe to drive',
  'the crane LMI screen is frozen, can we still make the pick',
  'the backup camera screen is not showing anything, can I still drive the forklift',
  'the safety data sheet is blank for this chemical',
  'the inspection sheet is blank, do I still need to sign it',
  'I can not find the sheet for this chemical',
  'we cannot find the signature of the authorized employee on the permit',
  'I did not see the video on forklift safety, can I still drive',
  'can I never save a signature for a coworker on the permit',
  'the fusible link did not open on the fire door',
  'what is the white screen around the welding booth for',
  'do I need a black screen for welding in the shop',
  // 4: lockout and permit words
  'we did not get notification of the lockout before they started work',
  'the crew did not receive notification before the equipment was re-energized',
  'workers got no notification before the line restarted, is that a violation',
  'employee notification is missing from our lockout procedure',
  'the confined space sign in sheet is missing, can we still enter',
  'visitors can not sign in without safety glasses, right?',
  'my coworker will not sign in on the confined space permit',
  'I have a problem with the application of lockout on the mixer',
  'is there an error in the application of the tag if the lock is missing',
  'tengo un problema con la aplicación del candado en la prensa',
  'hay un error en la aplicación del bloqueo y etiquetado',
  'the gas monitor download failed at the docking station, can I still use it',
  'zero harm is not working at our plant, the crew does not buy in',
  'is there a problem with zero harm as a goal',
  'zero harm no funciona en mi planta',
  'otis is that stuck valve dangerous',
  'otis is it still broken if I tape the cord',
  // 10: bare words with a floor meaning
  'is the old pipe lagging asbestos',
  'how do I install lagging in a trench',
  'how do I operate a concrete buggy safely',
  'does the power buggy operator need training',
  'the robot arm is glitching and moving on its own',
  'the light curtain glitched and the press cycled',
  'can I force close a stuck gate valve',
  'the foreman booted me out of the area for refusing unsafe work, what are my rights',
  'my supervisor kicked me out for not wearing a hard hat, can he do that',
  'my coworker signed me out of the confined space log while I was still inside',
  'a trailer is stuck at the loading dock, can I push it with the forklift',
  'a pallet is stuck on the loading dock plate',
  'the die is stuck at setup, can I reach in',
  'what ladder do I use to reach the support beams',
  'how do I safely reach the support bracket on the mezzanine',
  'I put in a ticket and maintenance still has not fixed the guard',
  'do I need to open a ticket before I lock out the mixer',
  'hay que levantar un ticket para arreglar la guarda',
  'how do I report a bug in the flour bin',
  // 15: machine and safety questions
  'the e-stop is glitching',
  'the conveyor keeps glitching and starts by itself',
  'the light curtain is glitchy, can we keep running',
  'the forklift is buggy, the brakes stick',
  'is the lagging on the steam pipe asbestos',
  'pipe lagging is falling off, is it safe to touch',
  'the crane remote is lagging',
  'the robot cell screen went black and the arm is still moving',
  'the HMI screen froze while the press was cycling',
  'the vibrating screen will not open, how do I lock it out',
  'my coworker signed me out of the confined space permit while I was inside',
  'the permit app crashed, is it ok to enter the confined space without a permit',
  'our gas monitor app is not working, can I enter the tank',
  "I can't find the sheet for acetone",
  // named in the design
  'who do I report a near miss to',
  'how do I write an accident report',
  'the guard is broken',
  'the e-stop is not working',
  'there is a problem with the forklift brakes',
];

describe('safety questions reach the safety answers, never a support entry or a report offer', () => {
  test.each(SAFETY_QUESTIONS)('%p', (q) => {
    const r = answer(q);
    expect([r.kind, q]).toEqual(['safety', q]);
  });
});

// Item 5: the app questions the support entries were written for (backend/talks/tests_kb_support.py).
const pairs = questions as unknown as { en: [string, string][]; es: [string, string][] };
const APP_QUESTIONS = [...pairs.en, ...pairs.es];

test('app questions reach their own support entry through the real order', () => {
  const rows = APP_QUESTIONS.map(([q, want]) => {
    const r = answer(q);
    const got = 'entry' in r ? (r.entry?.title ?? '(report offer, no entry)') : `safety: ${'sources' in r ? r.sources[0]?.title ?? 'not covered' : ''}`;
    return { q, want, got, ok: got === want, support: r.kind !== 'safety' };
  });
  const hit = rows.filter((r) => r.ok).length;
  const support = rows.filter((r) => r.support).length;
  // On this payload: 89 of 91. The two misses are on purpose: "otis no responde" fires the 911 rail ("no responde"
  // is also how a person who is down is described), so it gets the banner and a safety answer; "app not working"
  // names nothing an entry is about, so OTIS offers to file a report instead of guessing an entry.
  // Two more since the pure-app gate's second round, on purpose: a bare "sheet" is also a safety data sheet or a
  // permit, and "la cámara" is also a walk-in cold room, so neither names the app on its own any more. They get the
  // safety answer with the Report a problem link.
  expect(rows.filter((r) => !r.ok).map((r) => r.q)).toEqual(['app not working', 'i went back and the sheet is gone', 'otis no responde', 'la camara no abre']);
  expect(hit).toBe(87);
  expect(support).toBe(88);
});

test('typing an entry\'s own title shows that entry (the one that fires the 911 rail aside)', () => {
  const wrong = KB.filter((d) => d.kind === 'support')
    .map((d) => ({ d, r: answer(d.title) }))
    .filter(({ d, r }) => !('entry' in r && r.entry === d));
  // "Who to contact for help" holds "help", which the 911 rail fires on. "OTIS says it does not have that" and
  // "OTIS says it needs an update" share every word that matters, so the first stands in for the second.
  // "What a crash report sends and how to turn it off" holds "turn it off", which is a machine as often as the phone
  // since the gate's third round, so it gets the safety answer (asked as "how do I turn off crash reports" it is found).
  expect(wrong.map(({ d }) => d.title).sort()).toEqual([
    'OTIS says it does not have that',
    'What a crash report sends and how to turn it off',
    'Who to contact for help',
  ]);
});

// Item 18: complaints that used to show an unrelated entry word for word. Now the right entry, or none.
test.each([
  ['la app no abre', null],
  ['the app keeps logging me out', null],
  ['my phone gets hot', null],
  ['the screen went blank', null],
  ['the keyboard is not showing', null],
  ['the video is not playing', null],
  ['zero hour is not loading', null],
  ['app is slow', null],
  ["the app won't update", 'The app shows old content or will not update'],
  ['notifications are not working on my iphone', 'Notifications are not arriving'],
  ['notifications not working', 'Notifications are not arriving'],
] as const)('%p shows %p', (q, want) => {
  const r = answer(q);
  expect('entry' in r ? (r.entry?.title ?? null) : null).toBe(want);
});

// Item 30: a cry for help never gets an app entry under the banner, and one stray word does not pick one.
test.each(['ayúdame', '¡ayúdame!', 'ayudame por favor', 'help', 'I need help'])('%p: banner and the safety path only', (q) => {
  expect(answer(q)).toMatchObject({ urgent: true, kind: 'safety', link: false });
});
test.each(['email', 'the', 'does it support the load', 'where do I sign in for training', 'sense of humor in toolbox talks'])('%p does not pick a support entry', (q) => {
  expect(answer(q).kind).toBe('safety');
});

// Every routine question the 911 rail's spec keeps quiet stays with the safety answers here too.
test.each([
  'how often do forklifts need inspection', 'what is the OSHA rule for guardrail height', 'what PPE for welding',
  'how do I fill out a JSA', 'toolbox talk on heat stress', 'how do I inspect a harness before use',
  'when is my CPR training due', 'where do I find the SDS for bleach', 'how do I use a fire extinguisher',
  'how often should eyewash stations be flushed', 'first aid kit requirements', 'bloodborne pathogens training',
  'what is a wheel chock', 'chocking the wheels on a trailer', 'flame resistant clothing requirements',
  'how do I bleed the hydraulic lines', 'aed inspection checklist', 'smoke detector batteries', 'fall arrest system inspection',
  'how do I calibrate the gas monitor', 'what is a bump test for a gas detector', 'where is the emergency stop',
  'how often should lanyards be replaced', 'how do I troubleshoot the conveyor', 'how do I download the OSHA 300 form',
  'what is the notification rule for a fatality', 'the roof needs support', 'I found a bug in the flour',
  'the video shows a broken guard', 'scope and application of the lockout standard', 'the Otis elevator is stuck',
  '¿cómo uso el extintor?', '¿qué EPP necesito para soldar?', '¿dónde está el botiquín?', 'ruta de evacuación', '¿cómo se usa el lavaojos?',
])('routine %p stays with the safety answers', (q) => {
  expect(answer(q).kind).toBe('safety');
});
