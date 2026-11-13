/**
 * The pure-app gate after its fourth independent check. Two checkers found emergencies and hazards told only in app
 * words that still reached a support reply (with the 911 line, but no banner): a leading "otis" counted as naming the
 * app ("otis 1 is down", "otis can i run it now", "otis what do i do now"), a bare number was an app word and stood for
 * people ("2 down", "the app is stuck and so is 1 of mine"), and words for how a person is were free-standing app
 * words ("stuck up there", "lost contact", "3 are missing", "esta pegado", "se ve muy mal", "no contesta"). And at the
 * report flow's describe step a description that named nothing of the app was taken as the report, with no 911 line.
 *
 * The fixes are structural. A leading "otis" names the app only when OTIS is the subject of what follows. Numbers are
 * taken only in the app's own phrases (a percent, a size, an error or version number). The words for a state that a
 * person also has are taken only with a part of the app as their subject. "There" and "up" are taken only as "is
 * there" and as part of a verb ("set up"), never as a place. At the describe step a description that names nothing of
 * the app and says nothing only software does is held once, and a typed description carries the 911 line on the
 * email step. Every input of both checks, and attacks of our own, are in __tests__/fixtures/otis-gate-cases-4.json.
 */
import cases from './fixtures/otis-gate-cases-4.json';
import served from './fixtures/otis-kb-served.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { CALL_911_FIRST, callFirst, startFlow, stepFlow, type Flow } from '@/lib/support/flow';
import { aboutSomeoneElse, namesTheApp, onlyAboutTheApp, saysSoftwareFails, TESTED_PATTERNS } from '@/lib/support/intent';

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

describe('hazards, rights and lockout in app words: the safety answer, never a support entry or a report offer', () => {
  test.each(cases.hazard)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(supportReply(KB, q, lang(q))).toBeNull();
  });
});

describe('every route that failed before (diverted, no banner, or safe only because no entry matched) is in the lists above', () => {
  test('routes', () => {
    expect(cases.failing.routes.filter((q) => !cases.urgent.includes(q) && !cases.hazard.includes(q))).toEqual([]);
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
    if (cat === 'E') expect(next.urgent).toBe(true);
  });
});

test(`app complaints and help questions of both checks still reach support: ${cases.appReach} of ${cases.app.length}`, () => {
  const reached = cases.app.filter((q) => answer(q).kind !== 'safety');
  expect(reached.length).toBeGreaterThanOrEqual(cases.appReach);
});

describe('a leading "otis" names the app only when OTIS is the subject', () => {
  test.each([
    'otis 1 is down', 'otis 2 down', 'otis can i run it now', 'otis what do i do now', 'otis its frozen', 'otis it wont shut down',
    'otis do i have to give my name', 'otis who should i ask', 'otis there is 1 down', 'otis all of mine are down', 'otis now what',
    'otis is it stuck up there', 'otis i dont know where i am', 'otis hay 1 pegado', 'otis puedo entrar',
  ])('%p does not name the app, and does not pass the gate', (q) => {
    expect(namesTheApp(q)).toBe(false);
    expect(onlyAboutTheApp(q)).toBe(false);
  });
  test.each([
    'otis is slow', 'otis wont download', 'otis keeps crashing', 'otis gave a wrong answer', 'otis no descarga', 'otis stuck on setting up',
    'otis stopped answering', 'otis says it needs an update', 'otis is taking a short break', 'otis se traba', 'otis esta lento', 'otis ya no contesta',
  ])('%p names the app and passes the gate', (q) => {
    expect(namesTheApp(q)).toBe(true);
    expect(onlyAboutTheApp(q)).toBe(true);
  });
});

describe('words for how a person is count only with a part of the app as their subject', () => {
  test.each([
    'it all went black', 'stuck up there', 'lost contact', 'its gone', 'the app froze and 3 are missing', 'la app no sirve y esta pegado',
    'la app se trabo y no contesta', 'the app is stuck and so is 1 of mine', 'app froze and everything crashed down', 'otis no answer in there',
    'the app crashed and its hanging', 'la app se cerro y se quedo pegado', 'the app is down and so is my guy', 'my phone is down there',
  ])('%p is not only about the app', (q) => {
    expect(onlyAboutTheApp(q)).toBe(false);
  });
  test.each([
    'the app is down', 'the download is stuck at 40%', 'otis stopped answering', 'heat card missing', 'no aparece la charla del lunes',
    'la app se queda pegada', 'my phone is dead', 'the screen goes black when i open the app', 'stuck on the loading screen', 'i lost my signatures',
    'is there a way to change the language', 'there is no monday minute this week', 'the monday minute aint showin up', 'la foto del grupo no sale',
    'otis aint answering my question', 'the app keeps losing connection', 'the talk is missing from my phone',
  ])('%p is only about the app', (q) => {
    expect(onlyAboutTheApp(q)).toBe(true);
  });
});

describe('numbers are app words only in the app\'s own phrases', () => {
  test.each(['otis 108 today', 'its 108 today', 'otis hay 110 hoy', 'otis hoy esta en 110', 'the app froze and 1 of mine is gone', 'otis 1 no contesta'])(
    '%p is not only about the app',
    (q) => expect(onlyAboutTheApp(q)).toBe(false),
  );
  test.each(['the download is stuck at 40%', 'the app crashed 3 times today', 'it says error 404 in the app', 'my iphone 15 wont open the app', 'la descarga se queda en 40%'])(
    '%p is only about the app',
    (q) => expect(onlyAboutTheApp(q)).toBe(true),
  );
  test.each(['the app is stuck and so is 1 of mine', 'my phone froze and 1 is gone', 'otis 2 are down', 'la app se cerro y 1 no sale'])('%p names someone else', (q) => {
    expect(aboutSomeoneElse(q)).toBe(true);
  });
  test.each(['the app shows error 404', 'the app crashed 3 times today', 'version 2 of the app is out'])('%p names no one else', (q) => {
    expect(aboutSomeoneElse(q)).toBe(false);
  });
});

describe('the describe step: a description that names nothing of the app is held once; a typed one carries the 911 line', () => {
  const describe_ = (first: string) => at(first, 'describe');
  test.each(['i left it running', 'can i run it now', 'its 108 today', 'ya puedo entrar', 'what do i do now', 'i give up', 'esta pegado'])(
    '%p is held and handed on',
    (said) => {
      const r = stepFlow(describe_('the app keeps crashing'), { say: said }, about);
      expect(r.passOn).toBe(true);
      // Held for the gate (kept to put back in the box), or for the 911 rail (never put back in the box)
      expect(r.flow).toMatchObject({ step: 'describe', paused: true });
      if (!looksUrgent(said)) expect(r.flow?.held).toBe(said);
      expect(r.send).toBeUndefined();
    },
  );
  test('sent again after Go on, a held description is taken as written', () => {
    const held = stepFlow(describe_('the app keeps crashing'), { say: 'i left it running' }, about).flow as Flow;
    const resumed = stepFlow(held, { tap: 'resume' }, about);
    expect(resumed.prefill).toBe('i left it running');
    expect(stepFlow(resumed.flow as Flow, { say: 'i left it running' }, about).flow?.step).toBe('email');
  });
  test.each([
    ['it keeps crashing when i open the talk', 'en'],
    ['it freezes when i tap save', 'en'],
    ['crash', 'en'],
    ['se cierra sola cada vez', 'es'],
  ] as const)('%p is taken, and the email step carries the 911 line (%s)', (said, l) => {
    const first = l === 'es' ? 'la app se cierra sola' : 'the app keeps crashing';
    const r = stepFlow(describe_(first), { say: said }, about);
    expect(r.flow?.step).toBe('email');
    expect(r.notice).toBe(CALL_911_FIRST[l]);
  });
  test('the first message, sent from the box as it is, gets no second 911 line: it already had one', () => {
    const r = stepFlow(describe_('the app keeps crashing when i open a talk'), { say: 'the app keeps crashing when i open a talk' }, about);
    expect(r.flow?.step).toBe('email');
    expect(r.notice).toBeUndefined();
  });
  test('only software does these', () => {
    for (const q of ['it keeps crashing', 'se cierra sola', 'wont load', 'no carga', 'it freezes when i tap save']) expect(saysSoftwareFails(q)).toBe(true);
    for (const q of ['stuck', 'i left it running', 'its down', 'esta mal', 'can i run it now']) expect(saysSoftwareFails(q)).toBe(false);
  });
});

describe('the 911 line in the person\'s language', () => {
  test('Spanish for a Spanish message, English for an English one, both when a short Spanish message reads as English', () => {
    expect(callFirst('la app se cierra sola', 'es')).toBe(CALL_911_FIRST.es);
    expect(callFirst('the app keeps crashing', 'en')).toBe(CALL_911_FIRST.en);
    for (const q of ['otis se traba', 'otis 1 no contesta', 'otis hay 110 hoy', 'otis no descarga', 'otis esta lento']) {
      expect(callFirst(q, 'en')).toBe(`${CALL_911_FIRST.en}\n${CALL_911_FIRST.es}`);
    }
  });
});

describe('the 911 rail, round 4 (additions only)', () => {
  test.each([
    'otis 1 is down', '2 down', 'i have 2 missing', '1 got stuck', '1 no sale', 'otis 1 esta pegado', 'otis hay 1 pegado', 'otis there are 2 still missing',
    'lost contact with 2 of mine', 'no answer in there', 'it all crashed down', 'stuck up there', 'im going down', 'things are going black',
    'all i see is black', 'i dont know where i am', 'i give up', 'no puedo mas', 'ya no puedo', 'otis entro y ya no contesta',
    'he went in the tank 10 min ago and wont answer', 'my chest is crushing and my arm is numb', 'the app crashed and we crashed',
    'otis cant get 1 out', 'ammonia smell by the compressor', 'mi compita ya no esta respirando', 'se rebano el dedo con la sierra',
    'se acaba de caer mi compa', 'no tengo aire', 'otis me quedo pegado', 'la app se cerro y se quedo colgado', 'la app no sirve y se ve muy mal',
    'otis no contesta y no se ve bien', 'la app se cierra y ya no veo bien nada', 'otis ya no sale', 'otis what do i do now', 'otis que hago',
    'otis no lo veo', 'otis it turned on with me in it', 'otis its crushing me', 'the app is stuck and so is my hand', 'otis its black in there',
    'otis its frozen and im in there', 'app froze and its all coming apart', 'otis all of mine are down', 'otis i went black',
  ])('%p fires', (q) => {
    expect(looksUrgent(q)).toBe(true);
  });
  test.each([
    'the app is down', 'otis is down', 'the server went down', 'it says error 2', 'version 2 is out', 'the download is stuck at 40%', 'my phone is out of space',
    'la app se queda pegada', 'no veo la charla de hoy', 'otis no contesta', 'what do i do if the app crashes', 'how do i change my email',
    'the app lost connection', 'no la veo en la app', 'the app keeps losing connection', 'step 2 is missing', 'el celular se quedo pegado',
    'la app anda muy mal', 'otis ya no contesta', 'the talk is missing', 'how do i turn off notifications', 'the screen goes black when i open the app',
  ])('%p stays quiet', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
});

test('no pattern tested with .test() carries the /g flag', () => {
  expect(TESTED_PATTERNS.filter((p) => p.global)).toEqual([]);
});
