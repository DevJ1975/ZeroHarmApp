/**
 * The pure-app gate after its second independent check. The checkers found messages made only of the app's words
 * that describe an emergency or a hazard ("the app froze and my dude talks funny", "stuck in the frezer and my phone
 * has no signal", "app froze and the stop button doesn't work", "the sign is missing", "do I have to work Monday",
 * "i had contact with it what do i do"), and report-flow inputs taken as an answer ("rats", "wet floor @ dock 2").
 *
 * Every input of both checks is in __tests__/fixtures/otis-gate-cases-2.json, run through the same looksUrgent,
 * routeQuestion and stepFlow the chat screen calls, with the knowledge base the server really sends.
 */
import cases from './fixtures/otis-gate-cases-2.json';
import served from './fixtures/otis-kb-served.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { startFlow, stepFlow, type Flow } from '@/lib/support/flow';
import { onlyAboutTheApp, onlyAppWords, spelledOut, wordsNotOfTheApp } from '@/lib/support/intent';

jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() } }));
jest.mock('@/lib/otis/manifest', () => ({ kbVersionKey: 'otis_kb_version' }));

const KB = (served as { items: KbItem[] }).items;
const lang = (q: string) => (looksSpanish(q) ? 'es' : 'en');
function answer(q: string) {
  const urgent = looksUrgent(q);
  return { urgent, ...routeQuestion(KB, q, lang(q), urgent) };
}
const about = { device: { app_version: '1.0.0', platform: 'ios' as const, os_version: '18.1', device: 'iPhone 15' } };

/** A report flow started by `first`, walked to `step` the way the screen walks it. */
function at(first: string, step: Flow['step']): Flow {
  let f = startFlow(first, lang(first), true).flow as Flow;
  if (step === 'offer') return f;
  f = stepFlow(f, { tap: 'report' }, about).flow as Flow;
  if (step === 'confirm') return f;
  f = stepFlow(f, { tap: 'ok' }, about).flow as Flow;
  if (step === 'describe') return f;
  return stepFlow(f, { say: 'the app closes by itself every time I open a talk' }, about).flow as Flow;
}

const urgent = [...cases.urgent, ...cases.mine.urgent];
const hazard = [...cases.hazard, ...cases.mine.hazard];

describe('emergencies: the 911 banner, then the safety answer, never a support path', () => {
  test.each(urgent)('%p', (q) => {
    const r = answer(q);
    expect([q, r.urgent, r.kind]).toEqual([q, true, 'safety']);
  });
  test('every emergency that failed before is in the list above', () => {
    expect(cases.failing.urgent.filter((q) => !cases.urgent.includes(q))).toEqual([]);
  });
});

describe('hazards, rights and paperwork, even in nothing but app words: the safety answer, never a support entry or a report offer', () => {
  test.each(hazard)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(supportReply(KB, q, lang(q))).toBeNull();
  });
  test.each(cases.failing.hazard)('was diverted before: %p is not only about the app', (q) => {
    expect(onlyAboutTheApp(q)).toBe(false);
  });
});

describe('the report flow: a hazard or an emergency is never filed and never taken as an answer', () => {
  test.each(cases.flows as [string, Flow['step'], string, 'E' | 'H' | 'A'][])('started with %p, at %p: %p (%s)', (first, step, said, cat) => {
    const flow = at(first, step);
    expect(flow.step).toBe(step);
    const r = stepFlow(flow, { say: said }, about);
    expect(r.send).toBeUndefined();
    if (cat === 'A') {
      expect(r.passOn).toBeUndefined();
      return;
    }
    expect(r.passOn).toBe(true);
    if (r.flow) expect(r.flow).toMatchObject({ step, paused: true });
    const next = answer(said);
    expect(next.kind).toBe('safety');
    if (cat === 'E') expect(next.urgent).toBe(true);
  });
  test('every flow input that failed before is in the cases above', () => {
    const typed = new Set((cases.flows as string[][]).map(([, , said]) => said));
    expect(cases.failing.flows.filter((said) => !typed.has(said))).toEqual([]);
  });
  test('a short word that is not the app’s is held and answered before the length is looked at', () => {
    for (const said of ['rats', 'ice', 'gas', 'rata']) {
      const r = stepFlow(at('the app keeps crashing', 'describe'), { say: said }, about);
      expect(r).toMatchObject({ passOn: true, flow: { step: 'describe', paused: true } });
    }
    expect(stepFlow(at('the app keeps crashing', 'describe'), { say: 'slow' }, about).lines[0]).toMatch(/^Tell me a little more/);
  });
  test('at the email step only one word with an "@", or "name at site dot com", is met with Check the email address', () => {
    const email = at('the app keeps crashing', 'email');
    for (const near of ['maria@', 'maria@example', 'maria at example dot com', 'maria@@gmail.com'])
      expect(stepFlow(email, { say: near }, about).lines[0]).toMatch(/^Check the email address/);
    for (const said of ['wet floor @ dock 2', 'guard off @ press 4', 'slipped at the dot yard', 'brakes failed at the DOT check', 'hole at dock 4 dot on the map'])
      expect(stepFlow(email, { say: said }, about)).toMatchObject({ passOn: true, flow: { step: 'email', paused: true } });
  });
});

describe('real app complaints still reach a support path where the words allow it', () => {
  const app = [...cases.app, ...cases.mine.app];
  test('the count that reaches a support path', () => {
    const reached = app.filter((q) => answer(q).kind !== 'safety');
    // 118 of 131 on this payload (the two checks' 116 and 15 more of mine). The rest get the safety answer, most with
    // the Report a problem link: a word outside the app's (a safety topic, "bad", "mucho", "stop button"), a support
    // entry that does not match clearly, or the 911 rail on "help" or "no responde".
    expect(reached.length).toBe(118);
  });
  test.each(cases.failing.appUnreached.filter((q) => onlyAboutTheApp(q)))('was unreached before and passes the gate now: %p', (q) => {
    expect(wordsNotOfTheApp(q)).toEqual([]);
  });
});

describe('the gate, word by word', () => {
  test.each([
    // "the X talks" is not a talk title that lets any word through
    ['the app froze and my dude talks funny', ['dude']],
    ['app froze and my lead talks slow', ['lead']],
    // freezer and its typos are not "freezing"
    ['stuck in the frezer and my phone has no signal', ['stuck in', 'stuck', 'frezer']],
    ['app wont load and i been stuck in the frezzer', ['i been stuck', 'stuck in', 'stuck', 'frezzer']],
    ['stuck in the freezr phone wont work', ['stuck in', 'stuck', 'freezr']],
    // words with a floor meaning, outside an app phrase
    ['my phone froze and a bug bit me', ['a bug bit me', 'bit']],
    ['app froze and the stop button doesnt work', ['stop', 'button']],
    ['the sign is missing', ['missing', 'sign']],
    ['where is the sheet', ['sheet']],
    ['app is broken and so is the support', ['support']],
    ['app crashed and the load is stuck', ['stuck', 'load']],
    ['la app se cierra y la carga esta colgada', ['carga']],
    ['the app froze and the alert keeps going off', ['keeps going', 'alert', 'off']],
    ['do i have to work monday', ['have to work', 'do i have to work', 'monday']],
    ['do i get the holiday off', ['get the holiday off', 'get', 'holiday', 'off']],
    ['no abre la camara', ['camara']],
    ['necesito asistencia ahora', ['asistencia']],
    // phrases of app words that are about a person, a machine or a right
    ['i had contact with it what do i do', ['had contact', 'what do i do']],
    ['can you sign my name on the sheet', ['can you sign', 'sign', 'sheet']],
    ['my name is on the sheet but i wasnt there', ['but i wasnt', 'sheet']],
    ['can i get in trouble for reporting', ['get in trouble', 'get', 'reporting']],
    ['the app froze and im not okay', ['im not okay']],
    ['app froze and i cant see', ['i cant see']],
    ['app crashed and i crashed too', ['i crashed']],
    ['the app crashed and i had an episode', ['i had an episode']],
    ['please save me', ['save me']],
    ['everything is spinning when i look at the screen', ['everything is spinning', 'everything is spinning', 'screen']],
    ['it wont stop when i push the button', ['wont stop', 'stop', 'push', 'button']],
    ['do i need to sign in before i go in', ['before i go in']],
    ['no contesta el celular', ['no contesta el celular']],
  ] as const)('%p is not only about the app: %p', (q, extra) => {
    expect(wordsNotOfTheApp(q)).toEqual(extra);
    expect(onlyAboutTheApp(q)).toBe(false);
  });

  test.each([
    'the share button does nothing',
    'app wont let me sign',
    'my sigs keep disappearing from the sheet',
    'otis wont dl on my phone',
    'app keeps crashin every time i open it',
    'app is laggy af',
    'la aplicasion se cierra sola',
    'la charla esta bloqueada',
    'no me deja firmar la hoja',
    'how do i switch the app to spanish',
    'the monday minute aint showin up',
    'didnt get the monday notification',
    'no tengo espacio para otis',
    'the app wont load',
    'la app no carga',
    'sign-in sheet won’t save',
    'how do i contact support',
    'como contacto a soporte',
  ])('%p is only about the app', (q) => {
    expect([q, wordsNotOfTheApp(q)]).toEqual([q, []]);
    expect(onlyAboutTheApp(q)).toBe(true);
  });

  test('a changed letter is forgiven only in the app’s longest names, never in a failure word', () => {
    expect(onlyAboutTheApp('la aplicasion no funciona')).toBe(true);
    expect(onlyAppWords('the app crushed')).toBe(false);
    expect(onlyAppWords('the app frozer')).toBe(false);
  });

  test('slang and typos are written out only to find the entry', () => {
    expect(spelledOut('otis wont dl')).toBe('otis wont download');
    expect(spelledOut('notifs stopped comin thru')).toBe('notifications stopped coming through');
    expect(spelledOut('la aplicasion se cierra')).toBe('la aplicacion se cierra');
  });
});

describe('the 911 rail, after the second check', () => {
  test.each([
    'the app crashed and my boss is havin chest pains',
    'app freezes and my arm is numb and chest real tight',
    'app crashed n bro got clipped by the forklift',
    'app froze my coworker is seizin',
    'app froze n dude got his finger took off',
    'app crashed, the guy in the silo stopped talkin',
    'app wont load, i cant feel my legs after the fall',
    'mike down',
    'app crashed n mike down',
    'please save me',
    'can you save me',
    'necesito asistencia ahora',
    'the guy on the roof aint answerin',
    'the operator talks weird',
    'the app froze and my dude talks funny',
    'otis froze and the driver talks funny all of a sudden',
    'stuck in the frezer and my phone has no signal',
    'stuck in freezer phone dead',
    'my phone froze and a bug bit me',
    'everything is spinning when i look at the screen',
    'i black out when i look at the screen',
    'the app was open and everything went black',
    'cnt breth',
    'cant feel my arm',
    'im having chest pains',
    'the tank guy aint coming out',
    'the forklift clipped me',
    'me atoré',
    'me atore la mano en la banda',
    'me agarró la máquina el brazo',
    'me pegué',
    'me pegue en la cabeza con la viga',
    'me picó un alacrán y se me hincha la mano',
    'no siento las piernas',
    'mi compa se esta poniendo morado',
    'le está dando un ataque',
    'estoy encerrado en el cuarto frío',
    'el señor esta tirado en el piso',
    'se me fue el dedo en la sierra',
    'se siente muy mal y está sudando frío',
    'hay chispas en el panel',
  ])('%p fires', (q) => {
    expect(looksUrgent(q)).toBe(true);
  });

  test.each([
    'is otis down',
    'the app is down',
    'app keeps shutting down',
    'otis is slow, everything is down',
    'thumbs down',
    'the talk is slow',
    'otis talks weird',
    'the app froze',
    'la app se atora',
    'me cae bien',
    'kill the app',
    'heat card missing',
    'the screen turned gray',
    'save my sheet',
  ])('%p stays quiet', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
});
