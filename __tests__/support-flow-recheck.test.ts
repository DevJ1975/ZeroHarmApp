/**
 * The report flow after the second independent check: a hazard, an illness or another person typed at the offer, the
 * description or the email step is answered as a question and never filed as an app report (problems 4 and 5).
 */
import { startFlow, stepFlow, type Flow, type FlowInput } from '@/lib/support/flow';

const about = { device: { platform: 'ios', device: 'iPhone 15', os_version: '18.1', app_version: '1.4.0' } as never, email: '' };
const typed = 'the app keeps crashing';
const next = (r: { flow: Flow | null }, input: FlowInput) => stepFlow(r.flow as Flow, input, about);
const toDescribe = () => next(next(startFlow(typed, 'en', true), { tap: 'report' }), { tap: 'ok' });
const toEmail = () => next(toDescribe(), { say: typed });

describe('problem 4: at the offer, "still" plus a hazard is not "the fix did not help"', () => {
  test.each([
    'still no guard on the saw',
    'no it still has no brakes',
    'still leaking from the tank',
    'still sparking at the panel',
    'sigue saliendo vapor de la válvula',
    'still the same, the forklift brakes are bad',
    "didn't work, he is still dizzy",
  ])('%p is handed back as a question and nothing goes on to the report', (said) => {
    const r = next(startFlow(typed, 'en', true), { say: said });
    expect(r.passOn).toBe(true);
    expect(r.flow?.step ?? null).not.toBe('confirm');
    expect(r.send).toBeUndefined();
  });

  test.each(['still broken', 'no it still crashes', 'igual', 'it still closes'])('%p still goes on to the report', (said) => {
    expect(next(startFlow(typed, 'en', true), { say: said }).flow?.step).toBe('confirm');
  });
});

describe('problem 5: the description step holds hazards, illness and other people', () => {
  test.each([
    'my chest hurts',
    'his finger is gone',
    'there is a bomb threat',
    'he is throwing up',
    'my coworker is dizzy and confused',
    'mi compañero está mareado',
    'le duele el pecho',
    'the app froze and the forklift has no brakes',
    'the app crashed while I was checking the lockout and the press started',
    'the app keeps crashing and he is dizzy',
  ])('%p is held, handed back and not filed', (said) => {
    const r = next(toDescribe(), { say: said });
    expect(r.passOn).toBe(true);
    expect(r.flow).toMatchObject({ step: 'describe', paused: true });
    expect(r.send).toBeUndefined();
  });

  // Changed with the pure-app gate's second round: a talk named by a topic that is not one of the app's words
  // ("lockout", "forklift") is no longer let through, so the description is held and answered first. It goes back in
  // the box on Go on, and sending it again is taken as written.
  test.each(['the app crashed when I opened the lockout talk', 'the forklift video will not load in the app'])(
    'an app description that names a talk by its topic, %p, is held once, then taken as written',
    (said) => {
      const held = next(toDescribe(), { say: said });
      expect(held.passOn).toBe(true);
      expect(held.flow).toMatchObject({ step: 'describe', paused: true });
      const back = next(held, { tap: 'resume' });
      expect(back.prefill).toBe(said);
      expect(next(back, { say: said }).flow?.step).toBe('email');
    },
  );

  test('a held description is put back in the box on Go on, and sending it again is taken as written', () => {
    const said = 'the app froze on the forklift brakes page';
    const held = next(toDescribe(), { say: said });
    expect(held.flow).toMatchObject({ paused: true, held: said });
    const back = next(held, { tap: 'resume' });
    expect(back.flow?.step).toBe('describe');
    expect(back.prefill).toBe(said);
    const email = next(back, { say: said });
    expect(email.flow).toMatchObject({ step: 'email', text: said });
  });

  test.each(['bomb threat', 'knife fight', 'me mareo', 'chest pain'])('%p typed where the email goes is held, not "check the email"', (said) => {
    const r = next(toEmail(), { say: said });
    expect(r.passOn).toBe(true);
    expect(r.flow?.paused).toBe(true);
    expect(r.send).toBeUndefined();
  });

  test('only a near-miss email where the email goes is met with "Check the email address"', () => {
    expect(next(toEmail(), { say: 'maria@example' }).lines).toEqual(['Check the email address, or tap Skip.']);
    expect(next(toEmail(), { say: 'maria at example dot com' }).lines).toEqual(['Check the email address, or tap Skip.']);
    // Any other text with no "@" is held and answered: it may be a hazard the word lists do not know ("rebar exposed").
    expect(next(toEmail(), { say: 'maria' })).toMatchObject({ passOn: true, flow: { paused: true } });
  });
});
