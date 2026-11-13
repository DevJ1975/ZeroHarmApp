/**
 * The pure-app gate after its fifth independent check. The check found emergencies and hazards told only in app words
 * that still reached a support reply (with the 911 line, but no banner): a person's state said after "and" ("the app
 * froze and i am too", "me too", "same with me", "y yo igual"), "me and my phone are stuck", no answer for a time or a
 * count, "crashing into me", "cant find the way", OTIS or the app giving the go-ahead in "i can" order ("otis says i
 * can go in now", "otis dice que lo puedo cambiar ahora"), a swollen battery, "i broke something" and messages
 * "telling me to quit". In the report flow the same messages were taken as the report text.
 *
 * The fixes are structural where the cause is. A first-person subject (i, im, me, yo, we) with "too", "igual" or "as
 * well" after it, or joined to the phone or the app with "and" or "y", is how the person is, never the app. "Says" or
 * "dice" followed by a go-ahead ("i can", "puedo", "its ok to", "to go in") is a question about doing the work, never
 * the app. "N of M" is an app count only after step, page, talk, episode or downloading. "Ya no quiero nada" gets the
 * safety answer, not support; it is left off the 911 rail on purpose (a product decision, see the fixture). Every input
 * of the check, and attacks of our own, are in __tests__/fixtures/otis-gate-cases-5.json.
 */
import cases from './fixtures/otis-gate-cases-5.json';
import served from './fixtures/otis-kb-served.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { startFlow, stepFlow, type Flow } from '@/lib/support/flow';
import { onlyAboutTheApp, onlyAppWords, TESTED_PATTERNS } from '@/lib/support/intent';

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

describe('emergencies told in app words: the 911 banner, then the safety answer, never a support path', () => {
  test.each(cases.urgent)('%p', (q) => {
    const r = answer(q);
    expect([q, r.urgent, r.kind]).toEqual([q, true, 'safety']);
  });
});

describe('distress and ambiguous emergencies without a banner: the safety answer, never a support path', () => {
  test.each(cases.urgentNoBanner)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(onlyAboutTheApp(q)).toBe(false);
    expect(supportReply(KB, q, lang(q))).toBeNull();
  });
});

describe('hazards, rights and go-aheads in app words: the safety answer, never a support entry or a report offer', () => {
  test.each(cases.hazard)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(onlyAboutTheApp(q)).toBe(false);
    expect(supportReply(KB, q, lang(q))).toBeNull();
  });
});

describe('every route and flow that failed the check is in the lists above', () => {
  test('routes', () => {
    const all = new Set([...cases.urgent, ...cases.urgentNoBanner, ...cases.hazard]);
    expect(cases.failing.routes.filter((q) => !all.has(q))).toEqual([]);
  });
  test('flows', () => {
    const all = new Set(cases.flows.map((f) => JSON.stringify(f)));
    expect(cases.failing.flows.filter((f) => !all.has(JSON.stringify(f)))).toEqual([]);
  });
});

describe('the report flow: an emergency or a hazard is never filed and never taken as an answer', () => {
  test.each(cases.flows as [string, Flow['step'], string, 'E' | 'H' | 'A'][])('started with %p, at %p: %p (%s)', (first, step, said, cat) => {
    const r = stepFlow(at(first, step), { say: said }, about);
    expect(r.send).toBeUndefined();
    if (cat === 'A') {
      expect(r.passOn).toBeUndefined();
      return;
    }
    expect(r.passOn).toBe(true);
    if (r.flow) expect(r.flow).toMatchObject({ step, paused: true });
    const next = answer(said);
    expect(next.kind).toBe('safety');
    if (cat === 'E' && !cases.flowsNoBanner.includes(said)) expect(next.urgent).toBe(true);
  });
});

describe('app complaints', () => {
  test.each(cases.app)('%p gets no 911 banner', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
  test(`still reach support: ${cases.appReach} of ${cases.app.length}`, () => {
    expect(cases.app.filter((q) => answer(q).kind !== 'safety').length).toBeGreaterThanOrEqual(cases.appReach);
  });
});

// ---- The structural rules, word by word ------------------------------------------------------------

const STATES = ['stuck', 'down', 'frozen', 'lost', 'hanging', 'gone', 'spinning', 'dead', 'black'];
const APPS = ['the app', 'my phone', 'otis', 'the screen'];

describe('a first-person subject joined to the state of the app is the person, never the app', () => {
  const tails = ['and i am too', 'and im too', 'and me too', 'and same with me', 'and so am i', 'and we are too', 'and i am going too', 'and me as well', 'and im {s} too', 'and i am also'];
  const cases_ = APPS.flatMap((app) => STATES.flatMap((s) => tails.map((t) => `${app} is ${s} ${t.replace('{s}', s)}`)));
  test(`${cases_.length} English messages never pass the gate`, () => {
    expect(cases_.filter((q) => onlyAboutTheApp(q) || supportReply(KB, q, 'en'))).toEqual([]);
  });
  test('the same with "esta" in Spanish', () => {
    const es = ['la app', 'mi celular', 'otis', 'el cel'].flatMap((app) =>
      ['pegada', 'trabado', 'mal', 'congelada'].flatMap((s) => ['y yo igual', 'y yo tambien', 'y yo tambien igual', 'y nosotros igual', 'y yo estoy igual'].map((t) => `${app} esta ${s} ${t}`)),
    );
    expect(es.filter((q) => onlyAboutTheApp(q) || supportReply(KB, q, 'es'))).toEqual([]);
  });
  test.each(['me and my phone are stuck', 'me and the app are frozen', 'my phone and i are stuck', 'mi celular y yo estamos pegados', 'me n my phone r down', 'we and the app are lost'])(
    '%p never passes the gate',
    (q) => expect(onlyAboutTheApp(q)).toBe(false),
  );
  test.each([
    'the app keeps crashing', 'the app crashes for me too', 'my phone froze for me too', 'the app crashed and i lost my signatures', 'the app crashed and i tried reinstalling',
    'how do i change my email', 'otis is slow', 'my phone is fine but the app wont open', 'the app keeps asking me to sign in',
  ])('%p is still only about the app', (q) => {
    expect(onlyAboutTheApp(q)).toBe(true);
  });
});

describe('the go-ahead, said by OTIS or the app, never counts as the app', () => {
  const who = ['otis says', 'otis said', 'the app says', 'the app said', 'otis keeps telling me', 'otis told me'];
  const what = ['i can go in now', 'i can run it now', 'i can start it again', 'i can remove it now', 'we can do it', 'i dont have to use it', 'its ok to go in', 'it is ok if i do it now', 'to go in now', 'yes so i can do it', 'good to go'];
  const all = who.flatMap((w) => what.map((x) => `${w} ${x}`));
  test(`${all.length} English messages never pass the gate`, () => {
    expect(all.filter((q) => onlyAboutTheApp(q) || supportReply(KB, q, 'en'))).toEqual([]);
  });
  test.each(['otis dice que lo puedo cambiar ahora', 'otis dice que si entro ahora', 'la app dice que ya puedo hacer eso', 'otis dijo que ya puedo entrar', 'la app dice que se puede hacer ahora', 'otis said i dont need it'])(
    '%p never passes the gate',
    (q) => expect(onlyAboutTheApp(q)).toBe(false),
  );
  test.each(['otis says it needs an update', 'the app says no internet', 'otis says it is on a break', 'otis says the talk is not out yet', 'it says error 404 in the app', 'the app says i need to update',
    'the app says i can change the language in settings', 'otis says i can use it offline', 'otis dice que puedo cambiar el idioma',
    'the app says i dont need an account'])(
    '%p is still only about the app',
    (q) => expect(onlyAboutTheApp(q)).toBe(true),
  );
});

describe('counts, time and words found by the check', () => {
  test.each([
    'no answer on my phone for 40 minutes now', 'tried the phone 5 times no answer', 'its been 20 minutes and still no answer on the phone', 'no answer on the phone',
    'the crew sign in says 5 of 6 and the other is still in', 'la hoja de asistencia dice 4 de 5 y no veo al otro', 'la hoja de asistencia dice 5 de 6',
    'my phone froze and it keeps crashing into me', 'my phone is at 2 percent and i cant find the way', 'the battery on my phone looks bigger than it was',
    'my phone battery is so big now', 'i broke something and my phone too', 'i keep getting messages on my phone telling me to quit', 'otis ya no quiero nada',
    'otis ya no quiero hacer nada', 'i dont want to do anything anymore', 'who do i send the photo to',
  ])('%p never passes the gate', (q) => {
    expect(onlyAboutTheApp(q)).toBe(false);
  });
  test.each([
    'step 3 of 5 wont load in the app', 'the app is downloading 2 of 4 talks', 'the talk video freezes at 2 minutes', 'the app crashed 3 times today',
    'the other talk wont load in the app', 'notifications come at 3am', 'the app keeps asking me to type my email', 'the talk audio is too quiet in the app',
    'the app looks zoomed in on my phone', 'my sign in link expired', 'otis stops in the middle of a sentence', 'the app crashes when i turn my phone sideways',
    'the app eats my battery', 'can i use otis without wifi', 'how do i delete my account for good', 'the signatures vanish when i hit save',
    'the keyboard covers the text box in the app', 'it says no internet but my wifi is fine',
  ])('%p is only about the app', (q) => {
    expect(onlyAboutTheApp(q)).toBe(true);
  });
  test('a typed description in the report flow uses the same gate', () => {
    for (const q of ['me and my phone are stuck now', 'otis says i can go in now so i am going', 'my phone battery looks bigger and bigger', 'i broke something and then the app froze']) {
      expect(onlyAppWords(q)).toBe(false);
    }
  });
});

describe('the 911 rail, round 5 (additions only)', () => {
  test.each([
    'the app is down and i am too', 'the app froze and im too', 'my phone keeps spinning and me too', 'the app is stuck and same with me', 'still stuck and same with me',
    'la app esta pegada y yo igual', 'sigue igual y yo igual', 'la app se queda pegada y yo tambien igual', 'the app is gone and i am going too',
    'the app is down and so am i really', 'wait my phone is stuck and i am too', 'the screen went black and i am too',
    'me and my phone are stuck', 'me and the app are frozen in here', 'my phone and i are stuck', 'mi celular y yo estamos pegados',
    'no answer on my phone for 40 minutes now', 'tried the phone 5 times no answer', 'its been 20 minutes and still no answer on the phone',
    'still no reply on the phone and its been 30 minutes', 'no answer on the phone for 40 min', 'no reply on the radio', 'tried his phone 3 times and nothing',
    'my phone froze and it keeps crashing into me', 'a big thing crashed in to me and my phone is busted', 'phone at 1 percent cant find my way out',
    'crew sign in only shows 3 of 4 and i cant find the other', 'la hoja de asistencia dice 4 de 5 y no veo al otro', 'no encuentro a juan',
    'my hand went numb and the app froze', 'guy in the pit cant get air', 'se le metio la mano a la prensa', 'kid on the line slashed his wrist deep on the band saw',
    'my lips are swelling up after the bee sting', 'trench caved on juan up to his chest', 'somebody odd in the parking lot barely breathing',
    'rebar went straight into his thigh', 'he overdosed in the truck',
  ])('%p fires', (q) => {
    expect(looksUrgent(q)).toBe(true);
  });
  test.each([
    'the app crashed and i also lost my signatures', 'the app keeps crashing on me too', 'otis gives no answer for 2 minutes', 'otis took 2 minutes and still no answer',
    'no answer from otis for 10 minutes', 'the screen goes black for 2 minutes', 'i cant find the way to change my email', 'step 3 of 5 and the other steps wont load',
    'the app is acting odd today', 'my phone froze and so did the app', 'i can open the app but it freezes', 'otis says i need to update', 'the app is down',
    'the talk video freezes at 2 minutes', 'my hands are cold', 'how do i make the font bigger', 'no la encuentro en la app', 'no encuentro a la app',
    'the battery icon looks bigger', 'la app no sirve',
  ])('%p stays quiet', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
});

test('no pattern tested with .test() carries the /g flag', () => {
  expect(TESTED_PATTERNS.filter((p) => p.global)).toEqual([]);
});
