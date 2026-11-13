import type { KbItem } from '@/lib/otis/kb';
import { looksUrgent } from '@/lib/otis/safety';
import { entryText, supportReply } from '@/lib/support/answer';
import type { DeviceInfo } from '@/lib/support/device';
import { ANSWER_REPORT, answerReported, DESCRIBE_MIN, flowSent, pauseFlow, REPORT_GOES_TO, saysNo, saysYes, startFlow, startReport, stepFlow, whatIsSent, type Flow, type FlowResult } from '@/lib/support/flow';
import { ANSWER_REPORT_SENDS, REPORT_MIN } from '@/lib/support/reports';

jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() } }));
jest.mock('@/lib/otis/manifest', () => ({ kbVersionKey: 'otis_kb_version' }));

const iphone: DeviceInfo = { app_version: '1.0.0', platform: 'ios', os_version: '18.1', device: 'iPhone 15' };
const about = { device: iphone };
const typed = 'the app keeps closing when I open a talk';

/** Walks the flow the way the screen does, checking it never ends early. */
const next = (result: FlowResult, input: Parameters<typeof stepFlow>[1], more: { email?: string } = {}) => {
  expect(result.flow).not.toBeNull();
  return stepFlow(result.flow as Flow, input, { ...about, ...more });
};
const labels = (result: FlowResult) => result.actions.map((a) => a.label);
const taps = (result: FlowResult) => result.actions.map((a) => a.tap);

describe('the report flow, start to finish', () => {
  it('after a support answer: offer, confirm, describe, email, send', () => {
    const offer = startFlow(typed, 'en', true);
    expect(offer.flow).toEqual({ step: 'offer', lang: 'en', first: typed, text: '', paused: false });
    expect(offer.lines).toEqual(['If that did not fix it, want me to send a report to Trainovate, who make the app?']);
    expect(labels(offer)).toEqual(['Report this problem', 'That fixed it']);
    expect(offer.send).toBeUndefined();

    const confirm = next(offer, { tap: 'report' });
    expect(confirm.flow?.step).toBe('confirm');
    expect(confirm.lines).toEqual([
      'This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.',
      'A report sends Trainovate what you write, your email if you give one, your phone model (iPhone 15, iOS 18.1), the app version (1.0.0) and a random id for this app, so you can see your reports later. Nothing else. Your chat with OTIS is not sent. OK?',
    ]);
    expect(labels(confirm)).toEqual(['OK', 'Cancel']);
    expect(confirm.send).toBeUndefined();

    const describe = next(confirm, { tap: 'ok' });
    expect(describe.flow?.step).toBe('describe');
    expect(describe.lines).toEqual(['What went wrong with the app? I put what you typed in the box. Change it or add to it, then send. Leave out names.']);
    expect(describe.prefill).toBe(typed); // they do not have to type it twice
    expect(labels(describe)).toEqual(['Cancel']);

    const email = next(describe, { say: `${typed}. It started after the update.` });
    expect(email.flow).toMatchObject({ step: 'email', text: `${typed}. It started after the update.` });
    expect(email.lines).toEqual(['Want a reply? Type your email. Or tap Skip to send without one.']);
    expect(email.keyboard).toBe('email');
    expect(labels(email)).toEqual(['Skip', 'Cancel']);
    expect(email.send).toBeUndefined();

    const done = next(email, { say: ' Maria@Example.com. ' });
    expect(done.flow).toBeNull();
    expect(done.lines).toEqual([]);
    expect(done.send).toEqual({ text: `${typed}. It started after the update.`, source: 'otis', lang: 'en', email: 'maria@example.com', may_contact: true });
  });

  it('skipping the email sends no email and no contact flag', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    r = next(r, { say: typed });
    const done = next(r, { tap: 'skip' });
    expect(done.send).toEqual({ text: typed, source: 'otis', lang: 'en' });
    expect(done.flow).toBeNull();
  });

  it('typed answers work as well as taps: yes, ok, then no at the email step', () => {
    let r = startFlow(typed, 'en', false);
    r = next(r, { say: 'Yes please' });
    expect(r.flow?.step).toBe('confirm');
    r = next(r, { say: 'ok' });
    expect(r.flow?.step).toBe('describe');
    r = next(r, { say: typed });
    expect(r.flow?.step).toBe('email');
    expect(next(r, { say: 'no thanks' }).send).toEqual({ text: typed, source: 'otis', lang: 'en' });
  });

  it('with no support answer it offers to report straight away', () => {
    const offer = startFlow(typed, 'en', false);
    expect(offer.lines).toEqual(["I don't have a fix for that yet. If this is a problem with the Zero Harm app, I can send a report to Trainovate, who make the app."]);
    expect(labels(offer)).toEqual(['Report this problem', 'No thanks']);
    expect(taps(offer)).toEqual(['report', 'cancel']);
  });

  it('the Report a problem button starts at the confirm step, with nothing typed yet', () => {
    const confirm = startReport('', 'en', about);
    expect(confirm.flow).toEqual({ step: 'confirm', lang: 'en', first: '', text: '', paused: false });
    expect(confirm.lines[0]).toBe(REPORT_GOES_TO.en);
    expect(confirm.lines[1]).toMatch(/Your chat with OTIS is not sent\. OK\?$/);
    const describe = next(confirm, { tap: 'ok' });
    expect(describe.lines).toEqual(['What went wrong with the app? Tell me in a sentence or two. Leave out names.']);
    expect(describe).not.toHaveProperty('prefill');
  });

  it('nothing is sent before the last step, whatever the path', () => {
    const results: FlowResult[] = [startFlow(typed, 'en', true)];
    for (const input of [{ tap: 'report' as const }, { tap: 'ok' as const }, { say: 'too' }, { say: typed }, { say: 'not an email' }]) results.push(next(results[results.length - 1], input));
    expect(results.every((r) => r.send === undefined && r.flow !== null)).toBe(true);
  });

  it('is pure: the same step twice gives the same result and does not change the flow it was given', () => {
    const offer = startFlow(typed, 'en', true);
    const before = JSON.stringify(offer.flow);
    expect(next(offer, { tap: 'report' })).toEqual(next(offer, { tap: 'report' }));
    expect(JSON.stringify(offer.flow)).toBe(before);
  });
});

describe('ways out of the flow', () => {
  it('"That fixed it" ends it kindly and sends nothing', () => {
    const offer = startFlow(typed, 'en', true);
    for (const input of [{ tap: 'fixed' as const }, { say: 'that fixed it' }, { say: 'It works now, thanks' }]) {
      expect(next(offer, input)).toEqual({ flow: null, lines: ['Good. Glad that helped.'], actions: [] });
    }
  });

  it('Cancel ends it at every step and sends nothing', () => {
    let r = startFlow(typed, 'en', true);
    const steps = [r];
    for (const input of [{ tap: 'report' as const }, { tap: 'ok' as const }, { say: typed }]) steps.push((r = next(r, input)));
    expect(steps.map((s) => s.flow?.step)).toEqual(['offer', 'confirm', 'describe', 'email']);
    for (const step of steps) expect(next(step, { tap: 'cancel' })).toEqual({ flow: null, lines: ['OK. Nothing was sent.'], actions: [] });
    expect(next(steps[0], { say: 'no' }).lines).toEqual(['OK. Nothing was sent.']);
    expect(next(steps[1], { say: 'not now' }).lines).toEqual(['OK. Nothing was sent.']);
    expect(next(steps[2], { say: 'never mind' }).lines).toEqual(['OK. Nothing was sent.']);
    expect(next(steps[3], { say: 'cancel' }).lines).toEqual(['OK. Nothing was sent.']);
  });

  it('a question typed at the offer or the confirm ends the flow and is handed back, so it gets a safety answer', () => {
    const offer = startFlow(typed, 'en', true);
    const confirm = next(offer, { tap: 'report' });
    for (const step of [offer, confirm]) {
      expect(next(step, { say: 'what PPE do I need for grinding' })).toEqual({ flow: null, lines: [], actions: [], passOn: true });
    }
  });

  it('a description that is too short is asked for again', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    // "slow" (an app word, shorter than the minimum). Not "bad": a word that is not one of the app's is held and
    // answered before the length is looked at ("ice", "gas", "rats").
    const short = next(r, { say: 'slow' });
    expect(short.flow?.step).toBe('describe');
    expect(short.lines).toEqual(['Tell me a little more, so a person can understand the problem.']);
    expect(short.prefill).toBeUndefined();
    expect(DESCRIBE_MIN).toBe(REPORT_MIN);
    // The shortest description taken. (Five x's are no longer taken: a word that is not one of the app's puts the
    // report on hold, see lib/support/intent.ts onlyAboutTheApp. Nor is "stuck" since the gate's fourth round: with
    // no part of the app as its subject it is a person or a machine as often as the app.)
    expect('crash'.length).toBe(DESCRIBE_MIN);
    expect(next(r, { say: 'crash' }).flow?.step).toBe('email');
  });

  it('an email that does not look like one is asked for again, not sent', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    r = next(r, { say: typed });
    // Not 'maria' any more: text with no "@" that is not "x at y dot z" is held and answered as a question.
    for (const bad of ['maria@', 'maria at example dot com', 'maria@example']) {
      const again = next(r, { say: bad });
      expect(again.flow?.step).toBe('email');
      expect(again.lines).toEqual(['Check the email address, or tap Skip.']);
      expect(again.keyboard).toBe('email');
      expect(again.send).toBeUndefined();
    }
  });

  it('offers an email already on the phone at the email step', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    expect(next(r, { say: typed }, { email: ' Maria@Example.com ' }).prefill).toBe('maria@example.com');
    expect(next(r, { say: typed }, { email: 'not an email' })).not.toHaveProperty('prefill');
  });

  it('a button from an earlier step does nothing', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    expect(next(r, { tap: 'fixed' })).toEqual({ flow: r.flow, lines: [], actions: [] });
    expect(next(r, { tap: 'skip' })).toEqual({ flow: r.flow, lines: [], actions: [] });
  });
});

describe('an emergency in the middle of a report', () => {
  it('puts the report on hold, and nothing typed after that is taken as part of it', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    expect(r.flow?.step).toBe('describe');

    const emergency = "he's not breathing";
    expect(looksUrgent(emergency)).toBe(true);
    const held = next(r, { say: emergency });
    expect(held.passOn).toBe(true); // the screen answers it as a safety question, after the banner
    expect(held.flow).toEqual({ ...r.flow, paused: true });
    expect(held.lines).toEqual(['Your report is on hold. Nothing was sent. If your message was about the app, open Settings and tap Report a problem.']);
    expect(labels(held)).toEqual(['Go on with the report', 'Cancel']);
    expect(held.send).toBeUndefined();

    const after = next(held, { say: 'where is the AED' });
    expect(after).toEqual({ flow: held.flow, lines: [], actions: [], passOn: true }); // answered as a question, flow still on hold
    expect(next(held, { say: typed }).send).toBeUndefined();
    expect(next(held, { say: 'yes' }).passOn).toBe(true);
  });

  it('goes on from the same step when the person taps to, or ends on Cancel', () => {
    let r = startFlow(typed, 'en', true);
    r = next(r, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    const held = pauseFlow(r.flow as Flow);
    const back = next(held, { tap: 'resume' });
    expect(back.flow).toEqual({ ...r.flow, paused: false });
    expect(back.lines).toEqual(r.lines);
    expect(back.prefill).toBe(typed);
    expect(next(held, { tap: 'cancel' })).toEqual({ flow: null, lines: ['OK. Nothing was sent.'], actions: [] });
  });

  it('can be paused at any step', () => {
    let r = startFlow(typed, 'es', true);
    for (const input of [{ tap: 'report' as const }, { tap: 'ok' as const }, { say: typed }]) {
      const held = pauseFlow(r.flow as Flow);
      expect(held.lines).toEqual(['Su reporte está en pausa. No se envió nada. Si su mensaje era sobre la app, abra Settings y toque Report a problem.']);
      expect(next(held, { tap: 'resume' }).flow).toEqual(r.flow);
      r = next(r, input);
    }
  });
});

describe('Spanish', () => {
  it('keeps the language of the message that started the flow, even for one-word answers', () => {
    const offer = startFlow('la app se cierra sola', 'es', true);
    expect(offer.lines).toEqual(['Si eso no lo arregló, ¿quiere que envíe un reporte a Trainovate, que hace la app?']);
    expect(labels(offer)).toEqual(['Reportar este problema', 'Ya se arregló']);

    const confirm = next(offer, { say: 'sí' });
    expect(confirm.flow).toMatchObject({ step: 'confirm', lang: 'es' });
    expect(confirm.lines).toEqual([
      'Esto va a Trainovate, que hace la app, no a su empleador. Si hay un peligro en el trabajo, avise a su supervisor. Si alguien está herido, llame al 911.',
      'Un reporte envía a Trainovate lo que usted escriba, su correo si lo da, el modelo de su teléfono (iPhone 15, iOS 18.1), la versión de la app (1.0.0) y un número al azar de esta app, para que usted pueda ver sus reportes después. Nada más. Su conversación con OTIS no se envía. ¿De acuerdo?',
    ]);
    expect(labels(confirm)).toEqual(['De acuerdo', 'Cancelar']);

    const describe = next(confirm, { say: 'ok' }); // "ok" alone says nothing about language
    expect(describe.lines).toEqual(['¿Qué falló en la app? Puse lo que usted escribió en el cuadro. Cámbielo o agregue más, y envíelo. No ponga nombres.']);
    const email = next(describe, { say: 'la app se cierra cuando abro una plática' });
    expect(email.lines).toEqual(['¿Quiere una respuesta? Escriba su correo. O toque Omitir para enviar sin correo.']);
    expect(labels(email)).toEqual(['Omitir', 'Cancelar']);
    expect(next(email, { say: 'maria@correo' }).lines).toEqual(['Revise el correo, o toque Omitir.']);
    expect(next(email, { say: 'correo' })).toMatchObject({ passOn: true, flow: { paused: true } });
    expect(next(email, { say: 'omitir' }).send).toEqual({ text: 'la app se cierra cuando abro una plática', source: 'otis', lang: 'es' });
  });

  it('has every other line too', () => {
    expect(startFlow('x', 'es', false).lines).toEqual(['Todavía no tengo una solución para eso. Si es un problema con la app Zero Harm, puedo enviar un reporte a Trainovate, que hace la app.']);
    expect(labels(startFlow('x', 'es', false))).toEqual(['Reportar este problema', 'No, gracias']);
    const offer = startFlow('x', 'es', true);
    expect(next(offer, { tap: 'fixed' }).lines).toEqual(['Qué bueno. Me alegra que haya servido.']);
    expect(next(offer, { say: 'ya funciona' }).lines).toEqual(['Qué bueno. Me alegra que haya servido.']);
    expect(next(offer, { say: 'ahora no' }).lines).toEqual(['De acuerdo. No se envió nada.']);
    let r = next(offer, { tap: 'report' });
    r = next(r, { tap: 'ok' });
    // "cel", not "mal": since the gate's fourth round "mal" with no part of the app before it is how a person is.
    expect(next(r, { say: 'cel' }).lines).toEqual(['Cuénteme un poco más, para que una persona pueda entender el problema.']);
    expect(startReport('', 'es', about).flow?.step).toBe('confirm');
    expect(next(startReport('', 'es', about), { tap: 'ok' }).lines).toEqual(['¿Qué falló en la app? Cuéntemelo en una o dos frases. No ponga nombres.']);
  });
});

describe('what the person is told', () => {
  it('whatIsSent names the phone as well as it can', () => {
    expect(whatIsSent('en', { app_version: '1.2.0', platform: 'android', os_version: '15', device: 'Pixel 8' })).toMatch(/your phone model \(Pixel 8, Android 15\), the app version \(1\.2\.0\)/);
    expect(whatIsSent('en', { app_version: '', platform: 'android', os_version: '', device: '' })).toMatch(/your phone model \(Android\), the app version \(unknown\)/);
    expect(whatIsSent('en', { app_version: '1.0.0', platform: 'ios', os_version: '', device: '' })).toMatch(/\(iPhone\)/);
    expect(whatIsSent('en', { app_version: '1.0.0', os_version: '', device: '' })).toMatch(/\(this device\)/);
    expect(whatIsSent('es', { app_version: '', os_version: '', device: '' })).toMatch(/\(este dispositivo\), la versión de la app \(desconocida\)/);
  });

  it('flowSent gives the reference, or says it is saved, or says it could not be sent', () => {
    expect(flowSent('en', { ref: 'p-1', number: 'ZH-123', queued: false })).toBe('Reported. Your reference is ZH-123.');
    expect(flowSent('en', { ref: 'p-1', queued: true })).toBe('Saved on this phone. It will send when you have signal.');
    expect(flowSent('en', { ref: 'p-1', queued: false, failed: true })).toBe('That report could not be sent. Try again later.');
    expect(flowSent('es', { ref: 'p-1', number: 'ZH-123', queued: false })).toBe('Reportado. Su referencia es ZH-123.');
    expect(flowSent('es', { ref: 'p-1', queued: true })).toBe('Guardado en este teléfono. Se enviará cuando tenga señal.');
    expect(flowSent('es', { ref: 'p-1', queued: false, failed: true })).toBe('Ese reporte no se pudo enviar. Intente de nuevo más tarde.');
  });

  it('"Report this answer" asks first, in plain words, in both languages', () => {
    expect(ANSWER_REPORT.en.button).toBe('Report this answer');
    expect(ANSWER_REPORT.en.body).toBe(ANSWER_REPORT_SENDS.en);
    expect(ANSWER_REPORT.es.button).toBe('Reportar esta respuesta');
    expect(ANSWER_REPORT.es.body).toBe(ANSWER_REPORT_SENDS.es);
    expect(Object.keys(ANSWER_REPORT.es).sort()).toEqual(Object.keys(ANSWER_REPORT.en).sort());
    expect(answerReported('en', { ref: 'p-1', number: 'ZH-9', queued: false })).toBe('Sent. A person will review it.');
    expect(answerReported('en', { ref: 'p-1', queued: true })).toBe('Saved on this phone. It will send when you have signal.');
    expect(answerReported('en', { ref: 'p-1', queued: false, failed: true })).toBe('That could not be sent. Try again later.');
    expect(answerReported('es', { ref: 'p-1', number: 'ZH-9', queued: false })).toBe('Enviado. Una persona lo va a revisar.');
    expect(answerReported('es', { ref: 'p-1', queued: true })).toBe('Guardado en este teléfono. Se enviará cuando tenga señal.');
    expect(answerReported('es', { ref: 'p-1', queued: false, failed: true })).toBe('No se pudo enviar. Intente de nuevo más tarde.');
  });
});

describe('saysYes and saysNo', () => {
  test.each(['yes', 'Yes.', 'YES!', 'yeah', 'yep', 'ok', 'Okay', 'sure', 'yes please', 'ok thanks', 'go ahead', 'report it', 'send it', 'sí', 'Si', 'sí, por favor', 'claro', 'dale', 'de acuerdo', 'está bien', 'adelante'])('yes: %p', (text) => {
    expect(saysYes(text)).toBe(true);
    expect(saysNo(text)).toBe(false);
  });

  test.each(['no', 'No.', 'nope', 'nah', 'no thanks', 'not now', 'cancel', 'never mind', 'nevermind', 'stop', 'no gracias', 'ahora no', 'cancelar', 'mejor no'])('no: %p', (text) => {
    expect(saysNo(text)).toBe(true);
    expect(saysYes(text)).toBe(false);
  });

  // A sentence is never a yes: at the offer it is a new question and must reach the safety answers.
  test.each(['', '  ', 'yes but what PPE do I need', 'ok so the guard is broken', 'is it ok to bypass a guard', 'no guard on the saw', 'si la guarda está rota', 'not sure', 'he is not breathing', 'sure is hot today'])(
    'neither: %p',
    (text) => {
      expect(saysYes(text)).toBe(false);
      expect(saysNo(text)).toBe(false);
    },
  );
});

describe('supportReply: when OTIS answers from the tech-support entries', () => {
  const item = (id: string, title: string, text: string, extra: Partial<KbItem> = {}): KbItem => ({ id, title, text, source: 'Zero Harm app help', lang: 'en', issue: null, kind: 'support', ...extra });
  const kb: KbItem[] = [
    item('k90', 'The app crashes or closes by itself', '1. Close the app and open it again.\n2. Update the app.\n3. Restart the phone.', { tags: 'crash, crashed, crashing, closes, se cierra, no funciona' }),
    item('k91', 'OTIS download is stuck', '1. Connect to Wi-Fi.\n2. Keep the OTIS screen open.', { tags: 'download, stuck, frozen' }),
    item('k92', 'What OTIS is', 'OTIS is the Zero Harm safety assistant. OTIS runs on your phone.', { tags: 'otis, assistant, chatbot, who are you' }),
    item('k93', 'Finding past talks', 'Open the Archive from the Today screen to find every past talk.', { tags: 'archive, past talks, search, old issue' }),
    item('k94', 'How to report a problem with the app', 'Tap Settings, then Report a problem.', { tags: 'report, problem, bug, ticket, support' }),
    item('k1', 'Ladders: safe use', 'Check the ladder before you use it each shift. Report a damaged ladder.', { kind: undefined, source: 'Zero Harm Weekly' }),
    item('k2', 'Reporting an injury', 'Tell your supervisor right away and fill out the injury report.', { kind: undefined, source: 'Zero Harm Weekly' }),
  ];

  it('an app problem with a matching entry: the entry, word for word', () => {
    const reply = supportReply(kb, 'the app keeps crashing', 'en');
    expect(reply).toEqual({ kind: 'problem', entry: kb[0] });
    expect(entryText(kb[0])).toBe('The app crashes or closes by itself\n\n1. Close the app and open it again.\n2. Update the app.\n3. Restart the phone.');
  });

  it('an app problem with no matching entry: still a problem, so the screen offers to report', () => {
    expect(supportReply(kb, 'the app is broken', 'en')).toEqual({ kind: 'problem', entry: null });
    expect(supportReply([], 'the app keeps crashing', 'en')).toEqual({ kind: 'problem', entry: null });
  });

  it('a Spanish complaint finds the English entry through its tags', () => {
    expect(supportReply(kb, 'la app se cierra sola', 'es')).toEqual({ kind: 'problem', entry: kb[0] });
  });

  it('a plain question about the app that an entry answers: help, no report buttons', () => {
    expect(supportReply(kb, 'what is OTIS?', 'en')).toEqual({ kind: 'help', entry: kb[2] });
  });

  it('a question about the app with no entry goes on to the safety answers', () => {
    expect(supportReply(kb, 'is the app free', 'en')).toBeNull();
  });

  it('safety questions are never taken, even when a support entry shares their words', () => {
    for (const q of ['how do I report an injury', 'who do I report a near miss to', 'the ladder is broken', 'the guard is broken', 'what does OTIS say about ladders', 'he is not breathing', 'how do I inspect a ladder']) {
      expect(supportReply(kb, q, 'en')).toBeNull();
    }
  });

  it('never hands back a safety passage', () => {
    for (const q of ['the app crashed on the ladder talk', 'report a problem', 'problem with the app reporting an injury', 'what is OTIS']) {
      const reply = supportReply(kb, q, 'en');
      if (reply?.entry) expect(reply.entry.kind).toBe('support');
    }
  });

  it('answers an app question that does not name the app, but only on a clear match and with no hazard in it', () => {
    expect(supportReply(kb, 'how do I find past talks', 'en')).toEqual({ kind: 'help', entry: kb[3] });
    expect(supportReply(kb, 'where are the old talks', 'en')).toEqual({ kind: 'help', entry: kb[3] });
    expect(supportReply(kb, 'how do I download a JSA form', 'en')).toBeNull(); // one word in three is not enough
    expect(supportReply(kb, 'how do I report an injury', 'en')).toBeNull(); // "report" alone must not bring up the app entry
    expect(supportReply(kb, 'what is the capital of France', 'en')).toBeNull();
    expect(supportReply(kb, 'ladder inspection', 'en')).toBeNull(); // safety passages are never the answer here
    expect(supportReply(kb, 'report a problem', 'en')).toEqual({ kind: 'help', entry: kb[4] });
    expect(supportReply(kb, 'report a problem, the guard on the saw is missing', 'en')).toBeNull();
  });

  it('never takes a support path for a message the 911 rail fires on, or one that names a hazard', () => {
    for (const q of ["the app crashed and he's not breathing", 'I need help with the app', 'ayúdame', 'the app froze, can I still enter the tank', 'the app keeps crashing when I open the lockout talk']) {
      expect(supportReply(kb, q, 'en')).toBeNull();
    }
  });
});

describe('the review fixes: what a report is for, and what is never taken as one', () => {
  const toDescribe = () => next(next(startFlow(typed, 'en', true), { tap: 'report' }), { tap: 'ok' });

  it('every way into a report says who it goes to before anything is sent, in both languages', () => {
    for (const lang of ['en', 'es'] as const) {
      expect(next(startFlow(typed, lang, true), { tap: 'report' }).lines[0]).toBe(REPORT_GOES_TO[lang]);
      expect(next(startFlow(typed, lang, false), { tap: 'report' }).lines[0]).toBe(REPORT_GOES_TO[lang]);
      expect(startReport('', lang, about).lines[0]).toBe(REPORT_GOES_TO[lang]);
    }
    expect(REPORT_GOES_TO.en).toBe('This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.');
  });

  it('at the offer after an entry, a typed yes means send a report and a typed no means do not', () => {
    const offer = startFlow(typed, 'en', true);
    expect(next(offer, { say: 'yes' }).flow?.step).toBe('confirm');
    expect(next(offer, { say: 'sí' }).flow?.step).toBe('confirm');
    expect(next(offer, { say: 'no' })).toEqual({ flow: null, lines: ['OK. Nothing was sent.'], actions: [] });
    expect(next(offer, { say: 'that worked' }).lines).toEqual(['Good. Glad that helped.']);
  });

  test.each(['no it still crashes', 'still broken', 'it still closes', "didn't work", 'did not fix it', 'nope, still the same', 'sigue igual', 'todavía no funciona', 'no funcionó'])(
    'at the offer, %p means the fix did not help: on to the report',
    (text) => {
      expect(next(startFlow(typed, 'en', true), { say: text }).flow?.step).toBe('confirm');
    },
  );

  it('an emergency typed at any step holds the report and is handed back, so the banner is followed by the safety answer', () => {
    let r = startFlow(typed, 'en', true);
    for (const input of [{ tap: 'report' as const }, { tap: 'ok' as const }, { say: typed }, null]) {
      const held = next(r, { say: 'a rack came down on top of Mike' });
      expect(held.passOn).toBe(true);
      expect(held.flow).toEqual({ ...r.flow, paused: true });
      expect(held.send).toBeUndefined();
      if (input) r = next(r, input);
    }
  });

  test.each(['forklift 3 has no brakes and they are still using it', 'there is a spill in aisle 4', 'the guard on the saw is missing', 'el montacargas no tiene frenos'])(
    'a hazard typed as the description, %p, is not filed: the report goes on hold and the message is a question',
    (hazard) => {
      const held = next(toDescribe(), { say: hazard });
      expect(held.passOn).toBe(true);
      expect(held.flow?.paused).toBe(true);
      expect(held.flow?.step).toBe('describe');
      expect(held.send).toBeUndefined();
    },
  );

  it('the description is still taken when it is about the app, even with a safety word in it, or is their first words', () => {
    // "the app crashed when I opened the lockout talk" is held once now ("lockout" is not one of the app's words),
    // then taken as written: see support-flow-recheck.test.ts.
    expect(next(toDescribe(), { say: 'the app crashed when I opened the new talk' }).flow?.step).toBe('email');
    expect(next(toDescribe(), { say: typed }).flow?.step).toBe('email');
    expect(next(toDescribe(), { say: 'it closes when I tap Start crew sign-in' }).flow?.step).toBe('email');
  });

  it('a sentence typed where the email goes is a question, not a bad email', () => {
    const email = next(toDescribe(), { say: typed });
    const held = next(email, { say: 'how do I lock out the mixer' });
    expect(held.passOn).toBe(true);
    expect(held.flow?.paused).toBe(true);
    expect(next(email, { say: 'maria' })).toMatchObject({ passOn: true, flow: { paused: true } });
    expect(next(email, { say: 'maria at example dot com' }).lines).toEqual(['Check the email address, or tap Skip.']);
  });

  it('says so when it puts an email already on the phone in the box', () => {
    const r = toDescribe();
    const known = next(r, { say: typed }, { email: 'sam@example.com' });
    expect(known.prefill).toBe('sam@example.com');
    expect(known.lines).toEqual(['Want a reply? I put your email in the box. Send to include it, or tap Skip to send without one.']);
    const es = next(next(next(startFlow('la app se cierra', 'es', true), { tap: 'report' }), { tap: 'ok' }), { say: 'la app se cierra sola' }, { email: 'sam@example.com' });
    expect(es.lines).toEqual(['¿Quiere una respuesta? Puse su correo en el cuadro. Envíelo para incluirlo, o toque Omitir para enviar sin correo.']);
    expect(next(r, { say: typed }).lines).toEqual(['Want a reply? Type your email. Or tap Skip to send without one.']);
  });

  it('never puts an emergency message in the box as the report text', () => {
    const r = next(next(startFlow('I need help with the app', 'en', false), { tap: 'report' }), { tap: 'ok' });
    expect(r).not.toHaveProperty('prefill');
    expect(r.lines).toEqual(['What went wrong with the app? Tell me in a sentence or two. Leave out names.']);
  });

  it('every line has a Spanish twin', () => {
    const en = [startFlow(typed, 'en', true), startFlow(typed, 'en', false), pauseFlow(startFlow(typed, 'en', true).flow as Flow)];
    const es = [startFlow(typed, 'es', true), startFlow(typed, 'es', false), pauseFlow(startFlow(typed, 'es', true).flow as Flow)];
    en.forEach((r, i) => expect(es[i].lines).toHaveLength(r.lines.length));
    for (const r of es) for (const line of r.lines) expect(en.flatMap((x) => x.lines)).not.toContain(line);
  });
});
