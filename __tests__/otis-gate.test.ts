/**
 * The pure-app gate: a tech-support path (the report offer, a help entry in place of the safety answer) runs only for
 * a message that is about the app and nothing else. Every word of it must be one of the app's words (a closed list,
 * lib/support/intent.ts onlyAboutTheApp), so a hazard nobody put on a list still gets the safety answer.
 *
 * The messages are from two independent checks of the routing (English crew slang; Spanish, Spanglish and very short),
 * saved in __tests__/fixtures/otis-gate-cases.json, run through the same looksUrgent, routeQuestion and stepFlow the
 * chat screen calls, with the knowledge base the server really sends.
 */
import cases from './fixtures/otis-gate-cases.json';
import served from './fixtures/otis-kb-served.json';
import questions from './fixtures/support-questions.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { startFlow, stepFlow, type Flow } from '@/lib/support/flow';
import { hazardInReport, onlyAboutTheApp, onlyAppWords, TESTED_PATTERNS, wordsNotOfTheApp } from '@/lib/support/intent';

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

describe('emergencies next to an app complaint: banner, then the safety answer, never a support path', () => {
  test.each(cases.urgent)('%p', (q) => {
    expect([answer(q).urgent, answer(q).kind, q]).toEqual([true, 'safety', q]);
  });
  test.each(cases.failing.urgent)('was failing: %p', (q) => {
    expect(answer(q)).toMatchObject({ urgent: true, kind: 'safety' });
  });
});

describe('hazards, injuries and rights next to an app complaint: the safety answer, never a support entry or a report offer', () => {
  test.each(cases.hazard)('%p', (q) => {
    expect([answer(q).kind, q]).toEqual(['safety', q]);
  });
  test.each(cases.failing.hazard)('was failing: %p gets the safety answer with the Report a problem link', (q) => {
    const r = answer(q);
    expect(r.kind).toBe('safety');
    expect(supportReply(KB, q, lang(q))).toBeNull();
    // Named the app with a failure but not only about it: the link goes under the safety answer, unless the banner shows.
    if (!r.urgent) expect(r).toMatchObject({ link: true });
  });
});

describe('a hazard typed into a report in progress is never filed, never taken as an answer, and is answered as safety', () => {
  test.each(cases.flows as [string, Flow['step'], string, boolean][])('started with %p, at %p: %p', (first, step, said, emergency) => {
    const flow = at(first, step);
    expect(flow.step).toBe(step);
    const r = stepFlow(flow, { say: said }, about);
    expect(r.send).toBeUndefined();
    expect(r.passOn).toBe(true);
    // Either the report is over or it is on hold: it never moved on to another step.
    if (r.flow) expect(r.flow).toMatchObject({ step, paused: true });
    const next = answer(said);
    expect(next.kind).toBe('safety');
    if (emergency) expect(next.urgent).toBe(true);
  });
  test('every flow input the checkers listed as failing is in the cases above', () => {
    const typed = new Set((cases.flows as [string, string, string, boolean][]).map(([, , said]) => said));
    expect(cases.failing.flows.filter((said) => !typed.has(said))).toEqual([]);
  });
});

describe('app complaints: a support path, or the safety answer with the Report a problem link', () => {
  test.each(cases.appComplaints as [string, string | null][])('%p', (q) => {
    const r = answer(q);
    if (r.kind === 'safety') expect(r.link).toBe(true);
  });
  test('most of them still reach a support path', () => {
    const reached = (cases.appComplaints as [string, string | null][]).filter(([q]) => answer(q).kind !== 'safety').map(([q]) => q);
    // 57 of 61 on this payload. The four that get the safety answer and the link: two name a talk or video by a safety
    // topic ("the lockout talk", "the forklift video"), which the safety-word check keeps from the support paths;
    // "i need help with the app" fires the 911 rail on "help"; "how do i update the app" matches no entry clearly.
    expect(reached.length).toBe(57);
  });
});

describe('the 91 app help questions still reach their entry through the gate', () => {
  const { en, es } = questions as unknown as { en: [string, string][]; es: [string, string][] };
  const pairs = [...en, ...es];
  test('every one of them is only about the app, except two whose word has a floor meaning, and one the 911 rail fires on', () => {
    // "sheet" alone is also a safety data sheet or a permit; "la cámara" is also a walk-in cold room.
    expect(pairs.filter(([q]) => !onlyAboutTheApp(q)).map(([q]) => q)).toEqual(['i went back and the sheet is gone', 'la camara no abre']);
    expect(pairs.filter(([q]) => answer(q).kind === 'safety').map(([q]) => q)).toEqual(['i went back and the sheet is gone', 'otis no responde', 'la camara no abre']);
  });
});

describe('the gate', () => {
  test.each([
    'the app keeps crashing',
    'otis won’t download',
    'app crashd',
    'the app keeps frezing',
    'la aplicación no funciona',
    'la app se cierra sola',
    'how do I change my email',
    'the talk is locked',
    'heat card missing',
    'why are there christmas lights',
    'otis is taking a short break',
    'the worker sign in sheet is not saving',
    'I keep killing the app and it still crashes',
    'app crashes every time i open the new talk',
  ])('%p is only about the app', (q) => {
    expect([q, wordsNotOfTheApp(q)]).toEqual([q, []]);
    expect(onlyAboutTheApp(q)).toBe(true);
  });

  test.each([
    ['app froze and mike is not moving', ['mike', 'moving']],
    ['the app froze and the floor is slippery', ['floor', 'slippery']],
    ['la app se cerró y me torcí el tobillo', ['torci', 'el', 'tobillo']],
    ['otis keeps freezing and they make us work 14 hours without a break', ['make us work', 'they', 'make', 'us', '14', 'hours', 'without', 'break']],
    // A talk named by its topic is no longer let through (the topic word could be anything, "my dude talks funny")
    ['app crashes every time i open the lockout talk', ['lockout']],
    ['app crashd and hes bleding bad', ['hes', 'bleding', 'bad']],
    ['the app froze and im stuck', ['im stuck', 'stuck']],
    ['the app froze, my back is stuck', ['stuck', 'back']],
    ['the app crashed and the battery room smells funny', ['room', 'smells']],
    ['the app froze and the lights went out', ['lights', 'went', 'out']],
    ['the app froze, where do I get water', ['get', 'water']],
  ] as const)('%p is not only about the app: %p', (q, extra) => {
    expect(wordsNotOfTheApp(q)).toEqual(extra);
    expect(onlyAboutTheApp(q)).toBe(false);
  });

  test.each(['im stuck', 'i am stuck', 'its freezing', 'it is broken', 'stuck', 'it crashed', 'the battery is dead', 'no signal', 'it wont stop'])(
    '%p names nothing of the app: no support path',
    (q) => {
      expect(onlyAboutTheApp(q)).toBe(false);
      expect(answer(q).kind).toBe('safety');
    },
  );

  test('a typo is forgiven only for the app’s own words, never for a hazard', () => {
    expect(onlyAboutTheApp('the app keeps crahsing')).toBe(true);
    expect(onlyAboutTheApp('notificaton not working')).toBe(true);
    for (const q of ['the app crushed', 'the app froze, blading', 'app cashing', 'the app froze and he is bleding']) expect(onlyAboutTheApp(q)).toBe(false);
  });

  test('inside a report the talk is already about the app, so the words alone are checked', () => {
    expect(onlyAppWords('still broken')).toBe(true);
    expect(onlyAppWords('sigue igual')).toBe(true);
    expect(onlyAppWords('still water all over the floor')).toBe(false);
    expect(hazardInReport('the app froze and the floor is slippery')).toBe(true);
    expect(hazardInReport('the app crashed when I opened the lockout talk')).toBe(true);
    expect(hazardInReport('the app crashed when I opened the new talk')).toBe(false);
  });

  test('no pattern carries the /g flag', () => {
    expect(TESTED_PATTERNS.filter((rule) => rule.global || rule.sticky)).toEqual([]);
  });
});

describe('the 911 rail, after the checkers', () => {
  test.each([
    'mike is not moving',
    'tony aint movin',
    'hes bleding bad',
    'my bro is gushing from his arm',
    'coworker havin a seazure',
    'hes twitching on the ground by the line',
    'maria is shaking on the floor',
    'the guy is turning purple',
    'he is turning gray',
    'cnt breathe in here',
    'smells like propane in the shop',
    'it smells like ammonia',
    'homie got pinched in the press',
    'my chest feels real tight',
    'the guy in the tank aint answering',
    'the forklift hit me',
    'me caí',
    'me cai de la escalera',
    'me quemé con vapor',
    'me golpeé la cabeza',
    'me torcí el tobillo',
    'el montacargas me pegó',
    'me atropelló el montacargas',
    'hombre caído',
    'trabajador caído',
  ])('%p fires', (q) => {
    expect(looksUrgent(q)).toBe(true);
  });

  test.each(['me cae bien', 'kill the app', 'heat card missing', 'la bomba de agua no funciona', 'the screen turned gray', 'how do I bleed the hydraulic lines', 'the app keeps freezing', 'the line stopped moving'])(
    '%p stays quiet',
    (q) => {
      expect(looksUrgent(q)).toBe(false);
    },
  );
});
