/**
 * The second independent check of the OTIS routing, run through the same routeQuestion() the chat screen calls and
 * the knowledge base the server really sends. The messages are in __tests__/fixtures/otis-recheck-cases.json.
 *
 *   1. An emergency told next to an app complaint ("the app crashed and he is dizzy") never takes the problem path.
 *   2. A lock or unlock question is a lockout question, not "A talk is locked".
 *   3. A short safety or rights question ("heat", "do I get a break", "necesito un permiso") gets no app entry.
 *   6. Emergencies the 911 rail missed now get the banner.
 *   8. Under the banner, a message about the app and nothing else still gets the small Report a problem link.
 */
import served from './fixtures/otis-kb-served.json';
import cases from './fixtures/otis-recheck-cases.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksUrgent } from '@/lib/otis/safety';
import { looksSpanish } from '@/lib/otis/prompt';
import { routeQuestion } from '@/lib/support/answer';
import { aboutSomeoneElse, mentionsSafety } from '@/lib/support/intent';

jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() } }));
jest.mock('@/lib/otis/manifest', () => ({ kbVersionKey: 'otis_kb_version' }));

const KB = (served as { items: KbItem[] }).items;
function answer(q: string) {
  const urgent = looksUrgent(q);
  return { urgent, ...routeQuestion(KB, q, looksSpanish(q) ? 'es' : 'en', urgent) };
}

describe('problem 1: the app named next to an emergency never takes the problem path', () => {
  test.each(cases.appAndEmergency)('%p', (q) => {
    expect([answer(q).kind, q]).toEqual(['safety', q]);
  });
});

describe('problem 2: lock and unlock questions go to the safety answers', () => {
  test.each(cases.lockQuestions)('%p', (q) => {
    expect([answer(q).kind, q]).toEqual(['safety', q]);
  });
});

describe('problem 3: short safety and rights questions get no app entry', () => {
  test.each(cases.shortSafetyQuestions)('%p', (q) => {
    expect([answer(q).kind, q]).toEqual(['safety', q]);
  });
});

describe('problem 6: emergencies the 911 rail used to miss', () => {
  test.each(cases.railMisses)('%p gets the banner and the safety answer', (q) => {
    expect(answer(q)).toMatchObject({ urgent: true, kind: 'safety' });
  });
});

describe('problem 8: the banner over a message only about the app keeps the Report a problem link', () => {
  test.each(cases.urgentAboutTheAppOnly)('%p', (q) => {
    expect(answer(q)).toMatchObject({ urgent: true, kind: 'safety', link: true });
  });
  test.each(['my phone froze and my partner is still in the tank and not answering', 'the app froze, he is not answering on the radio from inside the vessel', 'help', 'ayúdame'])(
    '%p: no link under the banner',
    (q) => {
      expect(answer(q)).toMatchObject({ urgent: true, kind: 'safety', link: false });
    },
  );
});

describe('app questions near the new words still reach their entry', () => {
  test.each(cases.stillAppQuestions as [string, string][])('%p shows %p', (q, want) => {
    const r = answer(q);
    expect('entry' in r ? r.entry?.title : r.kind).toBe(want);
  });
});

describe('the words behind it', () => {
  test.each([
    ['do I get a break', true],
    ['otis is taking a short break', false],
    ['the lights went out', true],
    ['why are there christmas lights', false],
    ['necesito un permiso', true],
    ['la app no tiene permiso para la cámara', false],
    ['can I leave', true],
    ['heat', true],
    ['heat card missing', false],
    ['kill the power before work', true],
    ['I keep killing the app and it still crashes', false],
    ['is it locked', true],
    ['the talk is locked', false],
    ['I got locked out of the app', false],
    ['is there a phone number for support', false],
  ] as const)('mentionsSafety(%p) is %p', (q, want) => {
    expect(mentionsSafety(q)).toBe(want);
  });

  test.each([
    ['the app crashed and he is dizzy', true],
    ['this screen froze and the guy next to me is not okay', true],
    ['la app no funciona y mi compañero está mareado', true],
    ['it crashes on my coworker’s phone too', false],
    ['the worker sign in sheet is not saving', false],
    ['the app keeps crashing', false],
  ] as const)('aboutSomeoneElse(%p) is %p', (q, want) => {
    expect(aboutSomeoneElse(q)).toBe(want);
  });

  test.each(['the light is faint', 'how do I treat a bee sting', 'what causes dizziness', 'kill the power before work', 'la bomba de agua no funciona', 'the app keeps freezing'])(
    '%p does not fire the 911 rail',
    (q) => {
      expect(looksUrgent(q)).toBe(false);
    },
  );
});
