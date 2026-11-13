/**
 * The pure-app gate after its third independent check. The checker found emergencies told only in app words: Spanish
 * "él" (he) is "el" once the accent is off ("la app se cerró y el no sale"); short English cries are made of words
 * the app also uses ("app froze get me out", "it shut on me", "it got me", "something went off", "won't let go");
 * "crash" is also a noun ("otis there was a crash"). And hazards in app words: a sign on the wall, reporting at work,
 * a signature to start, a machine's settings, "my records", a phone on the floor, "that was close", "heat card says 108".
 *
 * The fix is structural: the words that commonly carry an event or a person in a hazard sentence are no longer app
 * words on their own. Each is taken only inside a fixed app phrase ("on my phone", "logs me out", "the video won't
 * play", "app settings", "report a problem"). Every input of the check, and attacks of our own on what is left, are in
 * __tests__/fixtures/otis-gate-cases-3.json, run through the same looksUrgent, routeQuestion and stepFlow the chat
 * screen calls, with the knowledge base the server really sends.
 */
import cases from './fixtures/otis-gate-cases-3.json';
import served from './fixtures/otis-kb-served.json';
import type { KbItem } from '@/lib/otis/kb';
import { looksSpanish } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';
import { routeQuestion, supportReply } from '@/lib/support/answer';
import { CALL_911_FIRST, startFlow, stepFlow, type Flow } from '@/lib/support/flow';
import { aboutSomeoneElse, onlyAboutTheApp, onlyAppWords, TESTED_PATTERNS, wordsNotOfTheApp } from '@/lib/support/intent';

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
  test('every emergency that failed before is in the list above', () => {
    expect(cases.failing.urgent.filter((q) => !cases.urgent.includes(q))).toEqual([]);
  });
});

describe('hazards, rights and paperwork in app words: the safety answer, never a support entry or a report offer', () => {
  test.each(cases.hazard)('%p', (q) => {
    expect([q, answer(q).kind]).toEqual([q, 'safety']);
    expect(supportReply(KB, q, lang(q))).toBeNull();
  });
  test.each(cases.failing.hazard)('failed before (diverted, or safe only because no entry matched): %p does not pass the gate', (q) => {
    expect(onlyAboutTheApp(q)).toBe(false);
  });
});

describe('the report flow: a hazard or an emergency is never filed and never taken as an answer', () => {
  test.each(cases.flows as [string, Flow['step'], string, 'E' | 'H' | 'A'][])('started with %p, at %p: %p (%s)', (first, step, said, cat) => {
    const flow = at(first, step);
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
});

describe('real app complaints still reach a support path where the words allow it', () => {
  test('the count that reaches a support path', () => {
    // 65 of 78 on this payload. The rest get the safety answer, most with the Report a problem link: a word kept out
    // on purpose ("hit", "lead", "luces"), or a message every word of which is the app's but that no entry matches
    // clearly ("my notifications stopped after the update", "la pantalla se queda en blanco"), which is ranking in
    // lib/otis/kb.ts.
    expect(cases.app.filter((q) => answer(q).kind !== 'safety').length).toBe(65);
  });
});

describe('the vocabulary: words that carry an event or a person are not app words on their own', () => {
  // Each is put after an app failure, where the old vocabulary took it: "the app froze and the X".
  test.each([
    'el', 'get', 'got', 'gets', 'getting', 'let', 'lets', 'out', 'off', 'on', 'went', 'come', 'coming', 'came', 'comes', 'shut', 'shuts',
    'take', 'takes', 'took', 'taking', 'close', 'saw', 'video', 'videos', 'screen', 'screens', 'settings', 'setting', 'ajustes', 'contacto',
    'firma', 'firmas', 'signature', 'signatures', 'report', 'reports', 'reported', 'reporting', 'reportar', 'reporto', 'reporte', 'records',
    'pantalla', 'buggy', 'spinning', 'drain', 'log', 'kicked',
  ])('%p', (word) => {
    const q = `the app froze and the ${word}`;
    expect(wordsNotOfTheApp(q)).toContain(word);
    expect(onlyAboutTheApp(q)).toBe(false);
  });

  test.each([
    // Spanish "él" (he), typed without the accent, is never the article
    ['la app se cerro y el no sale', ['el no', 'sale', 'el']],
    ['la app no sirve y el se quedo pegado', ['el se', 'se quedo pegado', 'quedo', 'pegado', 'el']],
    ['otis el no sale', ['el no', 'sale', 'el']],
    // English cries made of the app's words
    ['the app froze and it shut on me', ['shut on me', 'shut', 'on']],
    ['app froze get me out', ['get me out', 'get', 'out']],
    ['app froze and it got me', ['it got me', 'got']],
    ['app froze and i cant get it off me', ['cant get it off', 'get it off me', 'get', 'off']],
    ['my phone froze and something went off', ['something went off', 'went', 'off']],
    ['the app froze and it wont let go', ['wont let go', 'let']],
    ['app froze went in and aint coming out', ['went in and aint coming out', 'went', 'coming', 'out']],
    // "crash" the noun, and a phone or machine still on
    ['otis there was a crash', ['there was a crash']],
    ['otis big crash', ['big crash']],
    ['its still on and my phone froze', ['its still on', 'on']],
    ['it restarted by itself and my phone froze', ['restarted by itself']],
    // reporting, signing and records at work
    ['i reported and nothing happened', ['i reported', 'reported']],
    ['a quien reporto', ['a quien reporto', 'reporto']],
    ['do i need a signature to start', ['need a signature', 'signature']],
    ['puedo entrar sin firma', ['sin firma', 'puedo entrar', 'firma']],
    ['can i see my records', ['records']],
    ['the sign up there is missing', ['missing', 'sign', 'up', 'there']],
    ['my name is on the report and i wasnt there', ['and i wasnt', 'on', 'report']],
    // machine settings, phones on the floor, near misses, the weather, a card's reading
    ['can i change the settings with it on', ['with it on', 'settings', 'on']],
    ['puedo hacer ajustes sin apagar', ['sin apagar', 'ajustes']],
    ['can i take my phone in there', ['take my phone in', 'can i take', 'take', 'there']],
    ['otis that was close', ['that was close', 'close']],
    ['heat card says 108 what do i do', ['card says 108', 'what do i do', 'card says 108', '108']],
    ['quitaron los avisos', ['quitaron', 'avisos']],
    ['la descarga no para', ['descarga']],
    ['otis no veo', ['no veo']],
  ] as const)('%p is not only about the app: %p', (q, extra) => {
    expect(wordsNotOfTheApp(q)).toEqual(extra);
    expect(onlyAboutTheApp(q)).toBe(false);
  });

  test.each([
    // the same words, inside the fixed app phrases that keep them
    'otis wont download on my phone',
    'the app keeps freezing on my android',
    'app keeps kicking me out of my account',
    'the app logs me out every day',
    'how do i turn off crash reports',
    'how do i turn notifications off',
    'otis is turned off',
    'i never got the monday talk notification on my phone',
    'says i dont have enough storage to get otis',
    'app wont let me sign the sheet',
    'notifs not coming thru',
    'what time does the notification come',
    'talk isnt out yet',
    'otis takes forever to answer',
    'tapping take group photo does nothing at all',
    'the app keeps closing',
    'close the app',
    'the screen goes white when i open otis',
    'the app is stuck on the loading screen',
    'the video wont play in the app',
    'app settings wont open',
    'how do i change the language in settings',
    'como cambio el idioma en ajustes',
    'my signature wont save on the sheet',
    'la firma no se guarda',
    'se me borro la firma',
    'how do I report a problem',
    'quiero reportar un problema de la app',
    'how do i see my reports',
    'where does save sheet to my records go',
    'como cambio el idioma a español',
    'el video no carga',
    'la pantalla se queda en blanco',
    'the app is so buggy',
    'it keeps spinning on the loading screen',
    'app is draining my battery',
    'otis no descarga',
    'quiero darme de baja',
  ])('%p is only about the app', (q) => {
    expect([q, wordsNotOfTheApp(q)]).toEqual([q, []]);
    expect(onlyAboutTheApp(q)).toBe(true);
  });

  test('"él" before a verb is another person, as a second check the gate does not depend on', () => {
    for (const q of ['la app se cerro y el no sale', 'la app se cierra y el ya no contesta', 'la app falla y el va muy mal']) expect(aboutSomeoneElse(q)).toBe(true);
    for (const q of ['el video no carga', 'no aparece el clima', 'el celular no descarga la app']) expect(aboutSomeoneElse(q)).toBe(false);
  });

  test('no pattern carries the /g flag', () => {
    expect(TESTED_PATTERNS.filter((p) => p.flags.includes('g'))).toEqual([]);
  });
});

describe('the 911 line on a typed "still broken"', () => {
  test('a typed "still broken" at the offer carries it; a tap or a plain yes does not', () => {
    const offer = at('the app keeps crashing', 'offer');
    expect(stepFlow(offer, { say: 'no it still crashes' }, about)).toMatchObject({ flow: { step: 'confirm' }, notice: CALL_911_FIRST.en });
    expect(stepFlow(at('la app se cierra sola', 'offer'), { say: 'sigue igual' }, about)).toMatchObject({ flow: { step: 'confirm' }, notice: CALL_911_FIRST.es });
    expect(stepFlow(offer, { tap: 'report' }, about).notice).toBeUndefined();
    expect(stepFlow(offer, { say: 'yes' }, about).notice).toBeUndefined();
  });
  test('the lines are short, calm and say the same thing', () => {
    expect(CALL_911_FIRST).toEqual({ en: 'If anyone is hurt or in danger, call 911 now.', es: 'Si alguien está herido o en peligro, llame al 911 ahora.' });
  });
});

describe('the 911 rail, after the third check (additions only)', () => {
  test.each([
    // the checker's medium misses
    'app wont open and my lead is on the ground shaking',
    'otis froze, theres a guy hangin off the side of the trailer',
    'app wont sign me in and the roof guy slipped and is hangin by his lanyard',
    'the app keeps closing and it feels like an elephant is sitting on my chest',
    'se congelo la app, se volteo el montacargas con el chofer',
    'app not loading - grinder kicked back into my leg, deep gash',
    'the screen went black and the welder dropped, not waking',
    'app froze up n hes turnin blue',
    'the app glitched and i got hit in the head with a pipe',
    'otis is lagging and the guy in the manhole stopped answering',
    'la app se congela y me cayo acido en el brazo',
    'mi compa no contesta',
    'no, still broken and it shut on me',
    // cries made of app words
    'the app froze and it shut on me',
    'app froze get me out',
    'otis please get me out',
    'otis come get me',
    'otis let me out',
    'otis it got me',
    'the app froze and a bug got me',
    'app froze and i cant get it off me',
    'the app froze and it wont let go',
    'my phone froze and something went off',
    'app froze went in and aint coming out',
    'the app crashed and its on me',
    'otis there was a crash',
    'otis big crash',
    // Spanish él, and the rest
    'la app se cerro y el no sale',
    'la app se cierra y el se pone blanco',
    'el se quedo pegado',
    'mi compa se quedo pegado',
    'la app falla y el va muy mal',
    'otis entro y ya no sale',
    'otis no veo',
    'la descarga no para',
    'hay una descarga',
    // our own, on what the vocabulary left
    'otis something is wrong with me',
    'otis i cant move',
    'otis its on top of me',
    'app froze and its stuck on me',
    'otis it wont stop and its pulling me',
    'otis no puedo salir',
    'la app no abre y no me puedo mover',
    'otis me quede pegado',
    'otis i dont feel right',
  ])('%p fires', (q) => {
    expect(looksUrgent(q)).toBe(true);
  });

  test.each([
    // the earlier false-alarm list stays quiet
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
    // and the new patterns' near misses
    'the app shut down on me',
    'it wont let me out of the talk',
    'how do i get out of the app',
    'there was a crash report',
    'what does a crash report send',
    'the app keeps crashing',
    'my phone went off during the talk',
    'la app se pone blanca',
    'la pantalla se puso gris',
    'el video no sale',
    'no veo el video',
    'no me llega el codigo',
    'la descarga no avanza',
    'it got me logged out',
    'the app got hit with an update',
    'me cayo bien el nuevo supervisor',
    'the app froze',
  ])('%p stays quiet', (q) => {
    expect(looksUrgent(q)).toBe(false);
  });
});

describe('onlyAppWords inside the report flow follows the same vocabulary', () => {
  test.each(['the sign on it is gone', 'otis there was a crash', 'el se quedo pegado', 'app froze get me out', 'can i take a video of it', 'is it ok to remove the screen'])(
    '%p is not only the app’s words',
    (q) => {
      expect(onlyAppWords(q)).toBe(false);
    },
  );
});
