/**
 * The pure-app gate after the two independent checks of round 5. Round 5's rules held for the exact phrasings it was
 * tested on, but they were closed lists, so nearby phrasings built from the same gate words got through: the person
 * after "and" with "did", "have", "keep" or "the same" ("the app froze and i did too", "and im the same", "and so i
 * did", "as am i"), OTIS or the app giving the go-ahead as an order, "should", "will" or "yes" ("otis says go", "otis
 * said run it", "otis says i will be fine", "otis dijo dale"), a trailing "otis" calling OTIS by name ("what is
 * happening to me otis"), someone else as "another" or "otro", Spanish no-answer with a time, and an alarm word typed
 * as an email at the email step ("stuck@silo").
 *
 * The fixes are rules, not phrases:
 *  - a join (and, but, then, so, now, as) and a first-person subject that ends the message with a state word, a helper
 *    ("did", "have", "am") or "too", "to", "also", "as well" is the person, never the app;
 *  - what OTIS or the app said counts as the app only when it holds app talk (an update, an error, a sign-in, storage,
 *    the internet, a talk, a sheet...): with no app talk in it, a saying is a go-ahead for the work;
 *  - a last "otis" only calls OTIS by name unless the word before it takes it ("open otis", "para otis");
 *  - a comma or a stop is a clause break for the state words ("no signal, lost").
 * These run as a second look (SECOND_LOOK in lib/support/intent.ts), after the older lines. Every input of both checks,
 * and attacks of our own, are in __tests__/fixtures/otis-gate-cases-6.json.
 */
import cases from './fixtures/otis-gate-cases-6.json';
import served from './fixtures/otis-kb-served.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { CALL_911_FIRST, startFlow, stepFlow, type Flow } from '@/lib/support/flow';
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
const neverSupport = (q: string) => onlyAboutTheApp(q) || supportReply(KB, q, lang(q)) !== null;

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

describe('ambiguous emergencies without a banner: the safety answer, never a support path', () => {
  test.each(cases.urgentNoBanner)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(neverSupport(q)).toBe(false);
  });
});

describe('hazards, rights and go-aheads in app words: the safety answer, and the gate never passes', () => {
  test.each(cases.hazard)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(neverSupport(q)).toBe(false);
  });
});

describe('every route and flow that failed either check is in the lists above', () => {
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
    if (cat === 'E' && !(cases.flowsNoBanner as string[]).includes(said)) expect(next.urgent).toBe(true);
  });
  test('a near-miss email is asked for again, with the 911 line, since it was typed in place of a question', () => {
    const r = stepFlow(at('the app keeps crashing when i open the talk', 'email'), { say: 'maria@gmail' }, about);
    expect(r.lines).toEqual(['Check the email address, or tap Skip.']);
    expect(r.notice).toBe(CALL_911_FIRST.en);
    expect(r.send).toBeUndefined();
  });
  test.each(['stuck@silo', 'down@pit2', 'caido@rampa', 'gas@dock3', 'trapped@tank2', 'fuga@linea3'])('%p at the email step is held, with the banner', (said) => {
    const r = stepFlow(at('the app keeps crashing when i open the talk', 'email'), { say: said }, about);
    expect(r).toMatchObject({ passOn: true, flow: { step: 'email', paused: true } });
    expect(looksUrgent(said)).toBe(true);
  });
  test.each(['nope still frozen on the loading screen', 'still crashing when i open the talk', 'it still crashes on the home screen'])(
    '%p at the offer step is the answer "it is still broken"',
    (said) => {
      const r = stepFlow(at('the app keeps crashing when i open the talk', 'offer'), { say: said }, about);
      expect(r.passOn).toBeUndefined();
      expect(r.flow?.step).toBe('confirm');
    },
  );
});

describe('app complaints', () => {
  test.each(cases.app)('%p gets no 911 banner', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
  test(`still reach support: ${cases.appReach} of ${cases.app.length}`, () => {
    expect(cases.app.filter((q) => answer(q).kind !== 'safety').length).toBeGreaterThanOrEqual(cases.appReach);
  });
  test.each(cases.appNowReached)('%p, kept from support before, now reaches it', (q) => {
    expect(answer(q).kind).not.toBe('safety');
  });
});

// ---- The rules, word by word ----------------------------------------------------------------------

const APPS = ['the app is', 'my phone is', 'otis is', 'the screen is'];
const STATES = ['stuck', 'down', 'frozen', 'spinning', 'dead', 'black'];

describe('a join and a first-person subject at the end of the message is the person, never the app', () => {
  const tails = [
    'and i did too', 'and i have too', 'and im the same', 'and i am the same way', 'and me also now', 'and so i did', 'then i did', 'and me to',
    'and i am to', 'and i have been since 3am', 'and me with it', 'and i keep spinning', 'and i also froze', 'and we did too', 'and i did as well',
    'and i have also', 'and i am just the same', 'and now i am crashing too', 'and then i broke', 'and i am still', 'but im not', 'but i am not ok',
  ];
  const all = APPS.flatMap((app) => STATES.flatMap((s) => tails.map((t) => `${app} ${s} ${t}`)));
  test(`${all.length} English messages never pass the gate`, () => {
    expect(all.filter(neverSupport)).toEqual([]);
  });
  test(`and all ${all.length} fire the 911 rail`, () => {
    expect(all.filter((q) => !looksUrgent(q))).toEqual([]);
  });
  const es = ['la app', 'mi celular', 'otis'].flatMap((app) =>
    ['esta pegada', 'se trabo', 'no sirve', 'esta bien'].flatMap((s) => ['y yo tampoco', 'y yo sigo igual', 'y yo tambien estoy', 'y yo no puedo ya', 'pero yo no', 'y otro igual', 'y otro tambien'].map((t) => `${app} ${s} ${t}`)),
  );
  test(`${es.length} Spanish messages never pass the gate, and fire the rail`, () => {
    expect(es.filter(neverSupport)).toEqual([]);
    expect(es.filter((q) => !looksUrgent(q))).toEqual([]);
  });
  test.each(['i just froze and so did the app', 'i keep crashing and the app does too', 'the app is down, as am i', 'the app is frozen, same as me', 'app crashed, me too', 'otis went black and so did i'])(
    '%p never passes the gate, and fires the rail',
    (q) => {
      expect(neverSupport(q)).toBe(false);
      expect(looksUrgent(q)).toBe(true);
    },
  );
  test.each([
    'the app crashed and i lost my signatures', 'the app froze and i had to reinstall it', 'the app logs me out and i have to sign in again', 'the app keeps crashing on me too',
    'the app crashed and i tried reinstalling', 'my phone is fine but the app wont open', 'the app is slow but it works', 'the app froze but i fixed it',
  ])('%p is still only about the app, and the rail stays quiet', (q) => {
    expect(onlyAboutTheApp(q)).toBe(true);
    expect(looksUrgent(q)).toBe(false);
  });
});

describe('what OTIS or the app said is the app only when it holds app talk', () => {
  const who = ['otis says', 'otis said', 'the app says', 'the app said', 'otis keeps telling me', 'my phone says'];
  const what = [
    'go', 'start', 'run it', 'just do it', 'i should run it now', 'i will be fine', 'i need to run it', 'fix it now', 'its all ok now', 'nothing is wrong so i did it',
    'go for it', 'ok go', 'its ok for me to go in now', 'everything is fine so im going in', 'no problem to start now', 'yes', 'the answer is yes so i will run it',
    'do it now', 'i should go', 'i will be next',
  ];
  const all = who.flatMap((w) => what.map((x) => `${w} ${x}`));
  test(`${all.length} English go-aheads never pass the gate`, () => {
    expect(all.filter(neverSupport)).toEqual([]);
  });
  test.each([
    'otis keeps asking me to run it now', 'the app keeps asking me to start it', 'otis gave me the ok', 'otis gives the ok', 'otis dijo dale', 'otis dice dale nomas',
    'la app dice que dale', 'otis dice que si lo hago ahora', 'otis dice que esta bien entrar', 'otis me dijo que si', 'otis dice que ya puede entrar',
    'la app dice que lo cambio ya', 'otis dice que ya se puede', 'otis said yep', 'the app said go',
  ])('%p never passes the gate', (q) => expect(neverSupport(q)).toBe(false));
  test.each([
    'otis says it needs an update', 'the app says no internet', 'otis says it is on a break', 'it says error 404', 'the app says i need to update',
    'the app says something went wrong', 'the app keeps telling me to update', 'otis says it doesnt have that', 'the app says im offline', 'dice que no hay internet',
    'la app me dice que actualice', 'it keeps asking me to sign in', 'the app keeps asking me for my email', 'otis gave me a weird answer', 'otis gave a wrong answer',
    'otis says im not on a crew', 'otis keeps saying the same thing', 'otis says it cant answer that', 'la app dice que no tengo cuenta', 'otis gives no answer for 2 minutes',
    'the app says i can change the language in settings', 'otis says i can use it offline', 'otis dice que puedo cambiar el idioma',
  ])('%p is still only about the app', (q) => expect(onlyAboutTheApp(q)).toBe(true));
});

describe('a last "otis" only calls OTIS by name', () => {
  test.each(['what is happening to me otis', 'que me esta pasando otis', 'i dont know what to do otis', 'is it ok now otis', 'is it ok otis', 'am i ok otis', 'will i be ok otis', 'is it going to be ok otis'])(
    '%p never passes the gate',
    (q) => expect(neverSupport(q)).toBe(false),
  );
  test.each(['no tengo espacio para otis', 'i cant open otis', 'how do i update otis', 'the app froze otis', 'how do i delete otis', 'the app keeps crashing otis'])(
    '%p is still only about the app',
    (q) => expect(onlyAboutTheApp(q)).toBe(true),
  );
});

describe('the other holes the checks found', () => {
  test.each([
    'the app froze and i am not sure where i am', 'my phone has had no signal for 40 min and i dont know where', 'the app froze and something happened to me',
    'no signal, lost, phone at 4 percent', 'my phone is at 2 percent and its just me left', 'the app froze and another isnt responding', 'otis is stuck and another too',
    'otis no se ve nada', 'otis no puedo ya', 'otis ya no puedo hacer nada', 'otis no sirve y yo no puedo', 'mi celular 30 min sin respuesta', 'su celular sigue sin respuesta',
    'mi celular 5 min y nada', 'otis no contesta desde las 3pm', '20 minutes and still nothing on the phone', 'otis stuck since 3am', 'my phone looks bigger than before',
    'my phone is getting thicker', 'the back of my phone is popping up', 'my phone keeps telling me i should quit', 'otis keeps telling me im next',
    'can you put my name on the crew sheet', 'can i sign without seeing it', 'otis puedo firmar sin ver la charla', 'otis ya lo puedo cambiar', 'otis se puede iniciar ahora',
    'otis ya puedo cerrar', 'la app froze and i dont have my phone',
  ])('%p never passes the gate', (q) => expect(neverSupport(q)).toBe(false));
  test.each([
    'the app crashes in landscape mode', 'notifications come in at 3am', 'the screen is zoomed in', 'error code 12', 'error 503 otra vez', 'talk 3 wont load',
    'page 2 of 5 is blank', 'dark mode pls', 'the text is too small', 'can i make the font bigger', 'my sigs keep vanishing off the crew sheet', 'cant type in the chat box',
    'otis answer was wrong how do i flag that answer', 'how do i get rid of my account', 'the group photo button wont take the photo', 'the app is in english how do i change it',
    'the app logs me out every couple days', 'my reports tab is empty', 'la app no me deja guardar la hoja de la cuadrilla', 'otis so slow today fr', 'how much space does otis need',
    'i didnt get the sign in email', 'it wont let me sign in', 'how do i switch to the other language', 'the app says my session expired', 'otis se queda pensando y no contesta',
    'the app keeps crashin on me every morning',
  ])('%p is only about the app', (q) => expect(onlyAboutTheApp(q)).toBe(true));
  test('a typed description in the report flow uses the same gate', () => {
    for (const q of ['it froze and i did too', 'otis says run it so i did', 'otis dijo dale y entro', 'la app esta bien pero yo no', 'no signal, lost, phone at 3 percent']) {
      expect(onlyAppWords(q)).toBe(false);
    }
  });
});

describe('the 911 rail, round 6 (additions only)', () => {
  test.each([
    'someone ate it off the roof by bay 4', 'the trench walls gave on two guys', 'pallet came off the forks right onto my guys legs', 'se le vino encima la tarima a mi primo',
    'EL CILINDRO DE AMONIACO ESTA FUGANDO', 'mi companera esta temblando y no habla', 'otis 3 workers sick from fumes in bay 4', 'she stopped making sense and her skin is hot and dry',
    'no tengo nada de aire', 'what is happening to me otis', 'que me esta pasando otis', 'i dont know what to do otis', 'not sure where i am', 'i am not sure where i am and the app is stuck',
    'the app froze and something happened to me', 'my phone is at 2 percent and its just me left', 'no signal, lost, phone at 4 percent', 'su celular se apago y no contesta',
    'ya 30 min sin respuesta en su celular', 'sin respuesta 5 times on my phone', 'otis no contesta desde las 3pm', 'otis no hay senal y no se donde esta', 'y yo no puedo ya',
    'ya no puedo hacer nada', 'the app froze and another one is down', 'la app se cierra y otro esta tirado', 'stuck@silo', 'down@pit2', 'caido@rampa', 'gas@dock3',
  ])('%p fires', (q) => expect(looksUrgent(q)).toBe(true));
  test.each([
    'the app crashed and i lost my signatures', 'it told me to update and i did it', 'the app froze and i closed it', 'the app keeps crashing on me too', 'otis no contesta',
    'la app no carga desde ayer', 'the app is slow but it works', 'maria@gmail', 'maria@example', 'the screen is zoomed in', 'error code 12', 'dark mode please',
    'otis says i should update', 'my phone is fine but the app wont open', 'la pantalla no se ve nada', 'otis no habla espanol', 'the app isnt responding',
    'and another talk wont load', 'la app se trabo otra vez', 'the app crashed and so did my progress', 'how do i get rid of the reminders',
  ])('%p stays quiet', (q) => expect(looksUrgent(q)).toBe(false));
});

test('no pattern tested with .test() carries the /g flag', () => {
  expect(TESTED_PATTERNS.filter((p) => p.global)).toEqual([]);
});
