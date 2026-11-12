/**
 * The steps OTIS walks through when a person wants to report a problem with the app, written as a plain function so
 * the chat screen stays thin and every step can be tested: (where the flow is, what the person just said or tapped)
 * gives (where it is now, what OTIS says, which buttons to show, and what to send, if anything).
 *
 *   offer     "Report this problem" or "That fixed it", shown after a tech-support answer
 *   confirm   says who a report goes to (the app maker, not the employer), exactly what it sends, and that the chat
 *             is not sent
 *   describe  the person's own words about the app, starting from what they already typed
 *   email     optional, only if they want a reply
 *   then the report is filed (fileReport) and flowSent says how it went
 *
 * Rules that keep people safe:
 *   - The 911 rail runs on every message. If it fires while a flow is open, stepFlow puts the report on hold
 *     (pauseFlow) and hands the message back (passOn), so the banner is followed by the safety answer. Nothing typed
 *     after that is taken as part of the report until the person taps to go on.
 *   - A description that is not only about the app ("forklift 3 has no brakes", "the app froze and the floor is
 *     slippery", any word that is not one of the app's) is not filed either: it is a question for OTIS, so the report
 *     goes on hold the same way. So does anything typed where the email goes that is not an email address.
 *   - At "offer" and "confirm" a typed message that is not a yes or a no ends the flow and is handed back (passOn),
 *     so a safety question asked in the middle is answered as a safety question.
 *   - Nothing is sent before the confirm step, and the OTIS chat is never part of a report.
 *
 * Every line comes in English and Spanish. The language is chosen once, from the message that started the flow, and
 * kept: a one-word "si" or "ok" later cannot be read for its language.
 */
import { looksUrgent } from '../otis/safety';
import { tidyEmail, validEmail } from '../profile';
import type { DeviceInfo } from './device';
import { aboutSomeoneElse, hazardInReport, mentionsSafety, onlyAboutTheApp, onlyAppWords, saysSoftwareFails } from './intent';
import type { Filed, ReportInput } from './reports';

export type Lang = 'en' | 'es';
export type FlowStep = 'offer' | 'confirm' | 'describe' | 'email';
export type FlowTap = 'report' | 'fixed' | 'ok' | 'cancel' | 'skip' | 'resume';

/**
 * Where a report flow is. `first` is the message that started it; `text` is the description once given. `held` is a
 * description that was put on hold because it read like a hazard: sent again after "Go on with the report", it is
 * taken as written, so a real app report that names a machine is never stuck.
 */
export type Flow = { step: FlowStep; lang: Lang; first: string; text: string; paused: boolean; held?: string };

/**
 * The one fixed line every report path shows before anything is sent, in OTIS and on the Report a problem screen:
 * a report goes to the people who make the app, not to the employer, and is no way to report a hazard or an injury.
 */
export const REPORT_GOES_TO: Record<Lang, string> = {
  en: 'This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.',
  es: 'Esto va a Trainovate, que hace la app, no a su empleador. Si hay un peligro en el trabajo, avise a su supervisor. Si alguien está herido, llame al 911.',
};

/**
 * The one short line at the top of every support reply shown in place of the safety answer: a help entry, the offer
 * to report a problem, and the report taken up from a typed "still broken". The gate (lib/support/intent.ts) keeps
 * hazards off those paths, but a diversion nobody foresaw still tells the person to call 911. Calm on purpose: it sits
 * on top of normal app complaints. Not shown when the 911 banner is already showing.
 */
export const CALL_911_FIRST: Record<Lang, string> = {
  en: 'If anyone is hurt or in danger, call 911 now.',
  es: 'Si alguien está herido o en peligro, llame al 911 ahora.',
};

/** Words only Spanish has, for a message too short for looksSpanish ("otis 1 no contesta", "otis hay 110 hoy"). */
const SPANISH_WORDS =
  /\b(?:que|esta|estan|hay|hoy|puedo|puede|entro|entrar|contesta|quedo|queda|ya|se|la|el|los|las|apago|apagar|tengo|pegado|pegada|responde|aparece|sirve|funciona|cuando|porque|donde|como|mi|muy|sale|nada|celular|aplicacion|ahora|tambien|pero|sigue|anda|aqui|alli|ahi|esto|eso|carga|descarga|abre|traba|cierra|congela|jala|falla|me deja|no me)\b/;

/**
 * The 911 line for a support reply to `text`. In Spanish when the message is; in both languages when looksSpanish
 * said English but the message holds Spanish words, so a short Spanish message is never told only in English.
 */
export function callFirst(text: string, lang: Lang): string {
  if (lang === 'es') return CALL_911_FIRST.es;
  return SPANISH_WORDS.test(bare(text)) ? `${CALL_911_FIRST.en}\n${CALL_911_FIRST.es}` : CALL_911_FIRST.en;
}

/** A button under OTIS's last line. Tapping it is the same as stepFlow(flow, { tap }). */
export type FlowAction = { tap: FlowTap; label: string };

/** What the person did: typed something, or tapped a button. */
export type FlowInput = { say: string } | { tap: FlowTap };

export type FlowResult = {
  /** The flow after this step. null when it is over. */
  flow: Flow | null;
  /** What OTIS says now, in order. Mark these so they do not count toward the long-chat notice. */
  lines: string[];
  /** Buttons to show under the last line. */
  actions: FlowAction[];
  /** Put this in the message box, for the person to send or change. */
  prefill?: string;
  /** The next answer is an email address: show the email keyboard. */
  keyboard?: 'email';
  /** File this now with fileReport(), then show flowSent() with what comes back. */
  send?: ReportInput;
  /** The message was not an answer to the flow. Treat it as a normal question. */
  passOn?: boolean;
  /** Show this line (CALL_911_FIRST) at the top of the first line: a typed message was taken in place of a question. */
  notice?: string;
};

/** The shortest description worth sending. The same as REPORT_MIN in reports.ts, which the server enforces. */
export const DESCRIBE_MIN = 5;

// ---- Words ------------------------------------------------------------------------------------------

const LABELS: Record<Lang, Record<FlowTap | 'nothanks', string>> = {
  en: { report: 'Report this problem', fixed: 'That fixed it', ok: 'OK', cancel: 'Cancel', skip: 'Skip', resume: 'Go on with the report', nothanks: 'No thanks' },
  es: { report: 'Reportar este problema', fixed: 'Ya se arregló', ok: 'De acuerdo', cancel: 'Cancelar', skip: 'Omitir', resume: 'Seguir con el reporte', nothanks: 'No, gracias' },
};

const LINES = {
  // Asked so that a typed "yes" means "send a report" and a typed "no" means "do not".
  offerAfterAnswer: {
    en: 'If that did not fix it, want me to send a report to Trainovate, who make the app?',
    es: 'Si eso no lo arregló, ¿quiere que envíe un reporte a Trainovate, que hace la app?',
  },
  offerNoAnswer: {
    en: "I don't have a fix for that yet. If this is a problem with the Zero Harm app, I can send a report to Trainovate, who make the app.",
    es: 'Todavía no tengo una solución para eso. Si es un problema con la app Zero Harm, puedo enviar un reporte a Trainovate, que hace la app.',
  },
  describeTyped: {
    en: 'What went wrong with the app? I put what you typed in the box. Change it or add to it, then send. Leave out names.',
    es: '¿Qué falló en la app? Puse lo que usted escribió en el cuadro. Cámbielo o agregue más, y envíelo. No ponga nombres.',
  },
  describeBlank: {
    en: 'What went wrong with the app? Tell me in a sentence or two. Leave out names.',
    es: '¿Qué falló en la app? Cuéntemelo en una o dos frases. No ponga nombres.',
  },
  tooShort: {
    en: 'Tell me a little more, so a person can understand the problem.',
    es: 'Cuénteme un poco más, para que una persona pueda entender el problema.',
  },
  email: {
    en: 'Want a reply? Type your email. Or tap Skip to send without one.',
    es: '¿Quiere una respuesta? Escriba su correo. O toque Omitir para enviar sin correo.',
  },
  emailPrefilled: {
    en: 'Want a reply? I put your email in the box. Send to include it, or tap Skip to send without one.',
    es: '¿Quiere una respuesta? Puse su correo en el cuadro. Envíelo para incluirlo, o toque Omitir para enviar sin correo.',
  },
  badEmail: {
    en: 'Check the email address, or tap Skip.',
    es: 'Revise el correo, o toque Omitir.',
  },
  cancelled: {
    en: 'OK. Nothing was sent.',
    es: 'De acuerdo. No se envió nada.',
  },
  fixed: {
    en: 'Good. Glad that helped.',
    es: 'Qué bueno. Me alegra que haya servido.',
  },
  paused: {
    en: 'Your report is on hold. Nothing was sent. If your message was about the app, open Settings and tap Report a problem.',
    es: 'Su reporte está en pausa. No se envió nada. Si su mensaje era sobre la app, abra Settings y toque Report a problem.',
  },
  saved: {
    en: 'Saved on this phone. It will send when you have signal.',
    es: 'Guardado en este teléfono. Se enviará cuando tenga señal.',
  },
  failed: {
    en: 'That report could not be sent. Try again later.',
    es: 'Ese reporte no se pudo enviar. Intente de nuevo más tarde.',
  },
} satisfies Record<string, Record<Lang, string>>;

/** "iPhone 15, iOS 18.1", or a plain word when the phone will not say. */
function phoneName(device: DeviceInfo, lang: Lang): string {
  const system = device.platform === 'ios' ? 'iOS' : device.platform === 'android' ? 'Android' : '';
  const model = device.device || (device.platform === 'ios' ? 'iPhone' : device.platform === 'android' ? 'Android' : lang === 'es' ? 'este dispositivo' : 'this device');
  return system && device.os_version ? `${model}, ${system} ${device.os_version}` : model;
}

/**
 * The sentence that says exactly what a report sends. Shown at the confirm step, and fit for the line under the Send
 * button on the Report a problem screen. If what fileReport sends ever changes, this changes with it.
 */
export function whatIsSent(lang: Lang, device: DeviceInfo): string {
  const phone = phoneName(device, lang);
  const version = device.app_version || (lang === 'es' ? 'desconocida' : 'unknown');
  return lang === 'es'
    ? `Un reporte envía a Trainovate lo que usted escriba, su correo si lo da, el modelo de su teléfono (${phone}), la versión de la app (${version}) y un número al azar de esta app, para que usted pueda ver sus reportes después. Nada más.`
    : `A report sends Trainovate what you write, your email if you give one, your phone model (${phone}), the app version (${version}) and a random id for this app, so you can see your reports later. Nothing else.`;
}

const CHAT_NOT_SENT = { en: 'Your chat with OTIS is not sent. OK?', es: 'Su conversación con OTIS no se envía. ¿De acuerdo?' };

/** How it went, in the person's language: the ticket number, "saved on this phone", or that it could not be sent. */
export function flowSent(lang: Lang, filed: Filed): string {
  if (filed.number) return lang === 'es' ? `Reportado. Su referencia es ${filed.number}.` : `Reported. Your reference is ${filed.number}.`;
  return (filed.queued ? LINES.saved : LINES.failed)[lang];
}

/**
 * The words for "Report this answer" under an OTIS reply. Google Play asks for a way to flag AI answers. The person
 * confirms first, because this sends the one question and answer to Trainovate.
 */
export const ANSWER_REPORT = {
  en: {
    button: 'Report this answer',
    title: 'Report this answer?',
    // The same words as ANSWER_REPORT_SENDS in reports.ts (a test keeps them equal). Copied, not imported, because
    // screen tests mock reports.ts.
    body: 'Send this question and answer to Trainovate so a person can review it? Which OTIS model answered, iPhone or Android, your phone model, the system version, the app version and a random id for this app go with it.',
    send: 'Send',
    cancel: 'Cancel',
    sent: 'Sent. A person will review it.',
    saved: LINES.saved.en,
    failed: 'That could not be sent. Try again later.',
  },
  es: {
    button: 'Reportar esta respuesta',
    title: '¿Reportar esta respuesta?',
    body: '¿Enviar esta pregunta y esta respuesta a Trainovate para que una persona las revise? También se envían qué modelo de OTIS respondió, si es iPhone o Android, el modelo de su teléfono, la versión del sistema, la versión de la app y un número al azar de esta app.',
    send: 'Enviar',
    cancel: 'Cancelar',
    sent: 'Enviado. Una persona lo va a revisar.',
    saved: LINES.saved.es,
    failed: 'No se pudo enviar. Intente de nuevo más tarde.',
  },
} satisfies Record<Lang, Record<string, string>>;

/** The line to show after reportAnswer(): sent, saved for later, or could not be sent. */
export function answerReported(lang: Lang, filed: Filed): string {
  const words = ANSWER_REPORT[lang];
  return filed.number ? words.sent : filed.queued ? words.saved : words.failed;
}

// ---- Reading short answers --------------------------------------------------------------------------

/** Lower case, no accents, no punctuation: "¡Sí, por favor!" becomes "si por favor". */
const bare = (text: string) =>
  text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const POLITE = '(?: please| pls| thanks| thank you| por favor| porfa| gracias)?';
const YES = new RegExp(`^(?:yes|yeah|yep|yup|sure|ok|okay|please|do it|go ahead|report|report it|report this|report this problem|send|send it|si|claro|dale|de acuerdo|esta bien|adelante|reportar|reportalo|reportar este problema|enviar|envialo)${POLITE}$`);
const NO = new RegExp(`^(?:no|nope|nah|not now|cancel|never ?mind|stop|forget it|dont|do not|ahora no|cancelar|olvidalo|dejalo|mejor no)${POLITE}$`);
const FIXED = new RegExp(`^(?:fixed|that fixed it|it fixed it|that worked|it worked|it works|it works now|works now|all good|solved|ya funciona|ya quedo|ya se arreglo|se arreglo|funciono|listo|ya sirve)${POLITE}$`);
/**
 * "No, it still crashes", "didn't work", "sigue igual": the fix did not help, so the answer to the offer is a report.
 * Only an app failure counts after "still", "sigue" or "todavía": "still water all over the floor", "sigue goteando
 * aceite" and "still crashing and mike is not moving" are not answers to the offer, they are questions for OTIS.
 */
const STILL_BROKEN = new RegExp(
  '^(?:(?:no|nope|nah)\\s+)?(?:it\\s+|that\\s+|the app\\s+|otis\\s+)?(?:(?:is|s|keeps)\\s+)?(?:' +
    'still\\s+(?:(?:is|keeps)\\s+)?(?:crash\\w*|freez\\w*|froze|frozen|clos\\w*|stuck|broken|broke|not (?:work\\w*|load\\w*|open\\w*|fixed)|' +
    'doesn ?t work|does not work|won ?t (?:open|load|work)|the same(?: thing| problem)?|happening|does it|does that)|' +
    'didn ?t (?:work|help|fix it)|did not (?:work|help|fix it)|doesn ?t work|does not work|not fixed|same (?:thing|problem)|' +
    'sigue igual (?:no (?:sirve|funciona|abre|carga|jala))|sigue (?:igual|fallando|sin (?:funcionar|servir|abrir|arreglarse)|cerrandose|trabandose|congelandose|pasando|trabada|congelada|lo mismo)|' +
    'todavia (?:no (?:funciona|sirve|abre|carga)|falla|se (?:cierra|traba|congela))|no (?:funciono|sirvio|se arreglo)|igual)' +
    // "nope still frozen on the loading screen", "still crashing when i open the talk": where in the app it happens
    '(?:\\s+(?:on|at|in)\\s+(?:the\\s+|my\\s+)?(?:loading|splash|sign in|login|home|start|first|white|black|blank|same)?\\s*(?:screen|page|logo)|' +
    '\\s+(?:when|whenever|every time)\\s+i\\s+(?:open|tap|start|sign in|log in)(?:\\s+(?:it|the app|otis|a talk|the talk))?|\\s+again|\\s+for me|\\s+on my phone)?$',
);
const CANCEL = /^(?:cancel|cancel it|never ?mind|cancelar|olvidalo)$/;
/** What a mistyped email looks like: one word with an "@" ("maria@gmail", "maria@@gmail.com"), or "maria at gmail dot com". */
const NEAR_EMAIL = /^\S*@\S*$|^\S+\s+at\s+\S+\s+dot\s+(?:com|net|org|edu|gov|mil|us|mx|ca|co|io|me|info|biz)$/i;
const SKIP = new RegExp(`^(?:skip|skip it|none|no email|no|nope|omitir|saltar|sin correo|ninguno|no tengo)${POLITE}$`);

/** True for a plain yes in English or Spanish ("yes", "ok", "sí", "dale"). A longer sentence is not a yes. */
export const saysYes = (text: string) => YES.test(bare(text));
/** True for a plain no ("no", "not now", "cancel", "ahora no"). */
export const saysNo = (text: string) => NO.test(bare(text));

// ---- The steps --------------------------------------------------------------------------------------

const button = (lang: Lang, tap: FlowTap, label: keyof (typeof LABELS)['en'] = tap): FlowAction => ({ tap, label: LABELS[lang][label] });
const over = (line: string): FlowResult => ({ flow: null, lines: [line], actions: [] });

/** What OTIS says, and which buttons show, on arriving at a step. Also used to pick a paused report back up. */
function arrive(flow: Flow, about: { device: DeviceInfo; email?: string }): FlowResult {
  const { lang } = flow;
  switch (flow.step) {
    case 'offer':
      return { flow, lines: [LINES.offerAfterAnswer[lang]], actions: [button(lang, 'report'), button(lang, 'fixed')] };
    case 'confirm':
      return {
        flow,
        lines: [REPORT_GOES_TO[lang], `${whatIsSent(lang, about.device)} ${CHAT_NOT_SENT[lang]}`],
        actions: [button(lang, 'ok'), button(lang, 'cancel')],
      };
    case 'describe': {
      // Never put an emergency message in the box to be sent on as a report. A description held for a hazard goes back
      // in the box when the person picks the report up again.
      const start = flow.held || flow.first;
      const typed = start && !looksUrgent(start) ? start : '';
      return { flow, lines: [(typed ? LINES.describeTyped : LINES.describeBlank)[lang]], actions: [button(lang, 'cancel')], ...(typed ? { prefill: typed } : {}) };
    }
    case 'email': {
      const email = tidyEmail(about.email ?? '');
      const known = Boolean(email && validEmail(email));
      return {
        flow,
        lines: [(known ? LINES.emailPrefilled : LINES.email)[lang]],
        actions: [button(lang, 'skip'), button(lang, 'cancel')],
        keyboard: 'email',
        ...(known ? { prefill: email } : {}),
      };
    }
  }
}

/**
 * Opens the flow at the offer, right after OTIS has shown a tech-support answer (`answered` true) or found none.
 * `first` is the message the person typed, kept so they do not have to type it again.
 */
export function startFlow(first: string, lang: Lang, answered: boolean): FlowResult {
  const flow: Flow = { step: 'offer', lang, first: first.trim(), text: '', paused: false };
  return answered
    ? { flow, lines: [LINES.offerAfterAnswer[lang]], actions: [button(lang, 'report'), button(lang, 'fixed')] }
    : { flow, lines: [LINES.offerNoAnswer[lang]], actions: [button(lang, 'report'), button(lang, 'cancel', 'nothanks')] };
}

/** Opens the flow at the confirm step, for the "Report a problem" button: the person has already asked to report. */
export function startReport(first: string, lang: Lang, about: { device: DeviceInfo; email?: string }): FlowResult {
  return arrive({ step: 'confirm', lang, first: first.trim(), text: '', paused: false }, about);
}

/**
 * Puts an open flow on hold: the message is not taken as part of the report, and nothing else is until the person
 * taps "Go on with the report". stepFlow does this itself for an emergency, a hazard typed as the description, or a
 * sentence typed where the email goes; the screen also uses it to point back to a report already on hold.
 */
export function pauseFlow(flow: Flow): FlowResult {
  const { lang } = flow;
  return { flow: { ...flow, paused: true }, lines: [LINES.paused[lang]], actions: [button(lang, 'resume'), button(lang, 'cancel')] };
}

/**
 * One step of the flow. Pure: the same flow and input always give the same result. `about.device` is deviceInfo();
 * `about.email` is an email already on the phone (the sign-in or the sheet profile), offered at the email step.
 */
export function stepFlow(flow: Flow, input: FlowInput, about: { device: DeviceInfo; email?: string }): FlowResult {
  const { lang } = flow;
  const tap = 'tap' in input ? input.tap : null;
  const said = 'say' in input ? input.say.trim() : '';

  if (tap === 'cancel') return over(LINES.cancelled[lang]);
  if (flow.paused) {
    if (tap === 'resume') return arrive({ ...flow, paused: false }, about);
    // On hold: whatever is typed now is a question for OTIS, not part of the report.
    return { flow, lines: [], actions: [], passOn: true };
  }
  // An emergency message is never an answer to a step: hold the report and let the safety answer follow the banner.
  const hold = (): FlowResult => ({ ...pauseFlow(flow), passOn: true });
  if (!tap && looksUrgent(said)) return hold();

  // A typed answer that is not only about the app (a hazard, an illness, another person, any word that is not one of
  // the app's) is a question for OTIS, not an answer to this step.
  const notOnlyApp = !tap && (!onlyAppWords(said) || mentionsSafety(said) || aboutSomeoneElse(said));

  switch (flow.step) {
    case 'offer':
      // "Still no guard on the saw" is not "it still crashes": it ends the flow below and is answered as a question.
      if (tap === 'report' || (!tap && saysYes(said))) return arrive({ ...flow, step: 'confirm' }, about);
      // A typed "still broken" is taken as the answer instead of being asked as a question, so it carries the 911 line.
      if (!tap && !notOnlyApp && STILL_BROKEN.test(bare(said))) return { ...arrive({ ...flow, step: 'confirm' }, about), notice: CALL_911_FIRST[lang] };
      if (tap === 'fixed' || (!tap && FIXED.test(bare(said)))) return over(LINES.fixed[lang]);
      if (!tap && saysNo(said)) return over(LINES.cancelled[lang]);
      break;
    case 'confirm':
      if (tap === 'ok' || tap === 'report' || (!tap && saysYes(said))) return arrive({ ...flow, step: 'describe' }, about);
      if (!tap && saysNo(said)) return over(LINES.cancelled[lang]);
      break;
    case 'describe': {
      if (tap) break;
      if (saysNo(said)) return over(LINES.cancelled[lang]);
      // Not only the app's words ("rats", "ice", "gas"): held and answered, before the length is even looked at.
      const typedFresh = said !== flow.first && said !== flow.held;
      if (typedFresh && !onlyAppWords(said)) return { ...pauseFlow({ ...flow, held: said }), passOn: true };
      if ([...said].length < DESCRIBE_MIN) return { ...arrive(flow, about), lines: [LINES.tooShort[lang]], prefill: undefined };
      // "What went wrong with the app?" answered with anything that is not only about the app (a hazard, an illness,
      // someone else, any word that is not one of the app's): that is a question for OTIS, not a report to the app
      // maker, even when it also names the app ("the app froze and the forklift has no brakes", "the app froze and
      // the floor is slippery", "the app crashed when I opened the lockout talk"). The person's own first words, or a
      // description already held once (put back in the box on Go on), is taken as written.
      if (typedFresh && hazardInReport(said)) return { ...pauseFlow({ ...flow, held: said }), passOn: true };
      // A fresh description that names nothing of the app and says nothing only software does ("i left it running",
      // "can i run it now", "what do i do now") is held once too: every word of it may be an app word and it can still
      // be about a person or a machine. "It keeps crashing" and "se cierra sola" are taken. Sent again after Go on, a
      // held description is taken as written.
      if (typedFresh && !onlyAboutTheApp(said) && !saysSoftwareFails(said)) return { ...pauseFlow({ ...flow, held: said }), passOn: true };
      // Anything the person typed here was taken in place of a question, so the next line carries the 911 line.
      const typed = said !== flow.first;
      return { ...arrive({ ...flow, step: 'email', text: said }, about), ...(typed ? { notice: CALL_911_FIRST[lang] } : {}) };
    }
    case 'email': {
      const report: ReportInput = { text: flow.text, source: 'otis', lang };
      if (tap === 'skip' || (!tap && SKIP.test(bare(said)))) return { flow: null, lines: [], actions: [], send: report };
      if (tap) break;
      if (CANCEL.test(bare(said))) return over(LINES.cancelled[lang]);
      const email = tidyEmail(said);
      // Typing an email here is the answer to "Want a reply?", so it is fine to write back to it.
      if (validEmail(email)) return { flow: null, lines: [], actions: [], send: { ...report, email, may_contact: true } };
      // Anything typed where the email goes that is not one word with an "@" in it, or "name at example dot com", is
      // a question for OTIS, not a typo: "wet floor", "snake", "me caí", "mike is not moving", "wet floor @ dock 2",
      // "slipped at the dot yard". Only a near-miss email is met with "Check the email address".
      if (!NEAR_EMAIL.test(said)) return hold();
      // A near-miss email was still typed in place of a question, so it carries the 911 line too.
      return { ...arrive(flow, about), lines: [LINES.badEmail[lang]], prefill: undefined, notice: CALL_911_FIRST[lang] };
    }
  }

  if (tap) return { flow, lines: [], actions: [] }; // a button from an earlier step: nothing to do
  if (flow.step === 'offer' || flow.step === 'confirm') return { flow: null, lines: [], actions: [], passOn: true };
  return { flow, lines: [], actions: [] };
}
