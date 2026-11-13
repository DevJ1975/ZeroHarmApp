/**
 * Problem reports a person chooses to send: "the app keeps closing", typed to OTIS or on the Report a problem screen,
 * and "Report this answer" under an OTIS reply. A report is saved in an outbox on the phone first and then sent, so one
 * made in a dead spot is never lost: it goes out the next time the app comes to the front. The same idea as the sign-up
 * outbox in account.ts.
 *
 * What is sent: the person's own words, an email only if they typed one, the phone model, the system version, the app
 * version, and a random install id (the server keeps only a salted hash). Nothing else. The OTIS chat is never
 * attached; "Report this answer" sends the one question and answer the person just chose to send, with the same phone
 * facts and id (ANSWER_REPORT_SENDS says so on the confirm). Both stay tied to that install id, so they can be linked
 * to a sign-up from the same phone.
 *
 * Each report carries a key made on the phone. The server gives the same ticket back for the same key, so a report
 * that is sent twice (the answer got lost in a tunnel) never becomes two tickets.
 */
import Storage from 'expo-sqlite/kv-store';

import { api, ApiError, isConfigured } from '../config';
import { installId } from '../install';
import { tidyEmail, validEmail } from '../profile';
import { deviceInfo } from './device';

/**
 * One of this phone's reports, as "My reports" shows it. `queued` means it is still waiting on the phone. `failed`
 * means it waited on the phone and the server then turned it down for good, so it was never received.
 */
export type Report = { ref: string; number?: string; status: 'queued' | 'failed' | 'new' | 'in_progress' | 'fixed' | 'closed'; title: string; created_at: string; reply?: string };

export type ReportInput = {
  text: string;
  source: 'otis' | 'form';
  email?: string;
  name?: string;
  may_contact?: boolean;
  /** The language the person wrote in, when the caller knows it. */
  lang?: 'en' | 'es';
  /** The route the person was on, e.g. "/talk/12". Anything after a ? is dropped. */
  screen?: string;
};

/**
 * What became of a report. `number` ("ZH-123") when the server has it. `queued` when it is waiting on the phone for a
 * signal; `ref` is the phone's own key for it. `failed` when the server turned it down for good or reports are
 * switched off there: nothing is waiting and nothing was kept. `status` is the server's answer when it turned the
 * report down (422: the text did not pass its check, so "try again later" would be wrong). `full` when the phone
 * already holds OUTBOX_MAX reports waiting for a signal and this one was not saved.
 */
export type Filed = { ref: string; number?: string; queued: boolean; failed?: boolean; status?: number; full?: boolean };

/** The server takes 5 to 4000 characters. Check on the screen with longEnough() before calling fileReport. */
export const REPORT_MIN = 5;
export const REPORT_MAX = 4000;

const OUTBOX_KEY = 'support_outbox';
const KNOWN_KEY = 'support_reports';
const OUTBOX_MAX = 30; // far more than anyone files in a dead spot; keeps a runaway loop from filling the phone
const LIST_MAX = 30; // the server lists the newest 30
const SEND_TIMEOUT = 8000; // the person is looking at a spinner
const JUST_SENT_MS = 10 * 60 * 1000;

/**
 * True when the text is long enough for the server. It counts characters the way the server does: an emoji is one,
 * where JavaScript's length counts most emoji as two.
 */
export const longEnough = (text: string) => [...text.trim()].length >= REPORT_MIN;

/**
 * The one line every report path shows before sending (shared decision D4), in both languages. The person must know
 * a report does not reach their employer, and where a hazard or an injury goes instead.
 */
export const BEFORE_SENDING = {
  en: 'This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.',
  es: 'Esto va a Trainovate, que hace la app, no a su empleador. Si hay un peligro en el trabajo, dígaselo a su supervisor. Si alguien está herido, llame al 911.',
} as const;

/**
 * The line for a report that was not sent when "try again later" would be wrong: the server said the text needs more
 * (422), or the phone already holds as many waiting reports as it keeps. null otherwise; then use flowSent().
 */
export function whyNotSent(lang: 'en' | 'es', filed: Filed): string | null {
  if (!filed.failed) return null;
  if (filed.full)
    return lang === 'es'
      ? `Este teléfono ya tiene ${OUTBOX_MAX} reportes esperando señal. Envíe este cuando esos se hayan enviado.`
      : `This phone already has ${OUTBOX_MAX} reports waiting for a signal. Send this one after those go out.`;
  if (filed.status === 422) return lang === 'es' ? 'Cuéntenos un poco más de lo que pasó y envíelo otra vez.' : 'Tell us a little more about what happened, then send it again.';
  return null;
}

/**
 * The confirm for "Report this answer", naming everything reportAnswer() sends. The OTIS screen asks this before
 * calling reportAnswer. If what reportAnswer sends ever changes, this changes with it.
 */
export const ANSWER_REPORT_SENDS = {
  en: 'Send this question and answer to Trainovate so a person can review it? Which OTIS model answered, iPhone or Android, your phone model, the system version, the app version and a random id for this app go with it.',
  es: '¿Enviar esta pregunta y esta respuesta a Trainovate para que una persona las revise? También se envían qué modelo de OTIS respondió, si es iPhone o Android, el modelo de su teléfono, la versión del sistema, la versión de la app y un número al azar de esta app.',
} as const;

type Body = Record<string, string | boolean>;
/** `mine` is false for a flagged OTIS answer: it is sent like a report but is not listed under My reports. */
type Waiting = { key: string; at: string; body: Body; mine: boolean };

// ---- Pure helpers (tested) --------------------------------------------------------------------------

/** Cuts to a length without leaving half an emoji on the end, and drops characters a database refuses. */
export function tidyText(text: unknown, max: number): string {
  const cut = (typeof text === 'string' ? text : '').split('\u0000').join('').trim().slice(0, max);
  return /[\uD800-\uDBFF]$/.test(cut) ? cut.slice(0, -1) : cut;
}

/** The first line of what the person wrote, at most 120 characters. The server titles the ticket the same way. */
export function titleOf(text: string): string {
  const first = text.split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? '';
  return tidyText(first, 120);
}

/** The route without its query: "/talk/12?from=push" is sent as "/talk/12". */
export const cleanScreen = (screen: unknown) => tidyText(typeof screen === 'string' ? screen.split(/[?#]/)[0] : '', 120);

const STATUSES = ['new', 'in_progress', 'fixed', 'closed'] as const;
const FAILED_KEEP_MS = 30 * 24 * 60 * 60 * 1000; // a "could not be sent" row has said its piece after a month
const statusOf = (value: unknown): Report['status'] => (STATUSES.includes(value as (typeof STATUSES)[number]) ? (value as Report['status']) : 'new');

/** Newest first. A report still waiting on the phone has no server time yet, so its own time is used. */
const newestFirst = (list: Report[]) => [...list].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));

/**
 * Puts the server's list over the saved one. The server's word wins for status, title and reply. A report the phone
 * sent in the last few minutes is kept even if this answer does not hold it yet (the answer may have left first).
 */
export function mergeReports(saved: Report[], tickets: unknown[], now = Date.now()): Report[] {
  const fresh: Report[] = [];
  for (const raw of tickets) {
    const t = raw as { number?: unknown; status?: unknown; title?: unknown; created_at?: unknown; reply?: unknown } | null;
    const number = typeof t?.number === 'string' ? t.number.trim() : '';
    if (!number || fresh.some((r) => r.number === number)) continue;
    const reply = tidyText(t?.reply, 2000);
    fresh.push({
      ref: saved.find((r) => r.number === number)?.ref ?? number,
      number,
      status: statusOf(t?.status),
      title: tidyText(t?.title, 120),
      created_at: typeof t?.created_at === 'string' ? t.created_at : '',
      ...(reply ? { reply } : {}),
    });
  }
  const justSent = saved.filter((r) => r.number && !fresh.some((f) => f.number === r.number) && now - (Date.parse(r.created_at) || 0) < JUST_SENT_MS);
  // The server never had these, so its list cannot hold them: keep them on the phone for a while.
  const failed = saved.filter((r) => r.status === 'failed' && !r.number && now - (Date.parse(r.created_at) || 0) < FAILED_KEEP_MS);
  return newestFirst([...fresh, ...justSent, ...failed]).slice(0, LIST_MAX);
}

// ---- Outbox -----------------------------------------------------------------------------------------

async function readList<T>(key: string): Promise<T[]> {
  try {
    const list = JSON.parse((await Storage.getItem(key)) ?? '[]') as unknown;
    return Array.isArray(list) ? (list.filter((item) => item && typeof item === 'object') as T[]) : [];
  } catch {
    return []; // a damaged value must not jam the queue
  }
}
const readOutbox = async () => (await readList<Waiting>(OUTBOX_KEY)).filter((w) => typeof w.key === 'string' && w.body && typeof w.body === 'object');
const readKnown = async () => (await readList<Report>(KNOWN_KEY)).filter((r) => typeof r.ref === 'string');

// Changes go one at a time, each on a fresh read, so a report filed while another is being sent is never overwritten.
let line: Promise<unknown> = Promise.resolve();
function inLine(step: () => Promise<void>): Promise<void> {
  const next = line.then(step);
  line = next.catch(() => {});
  return next;
}

/**
 * True when the server said no to this report for good: it is malformed (400), too big (413) or failed a check (422).
 * Any other 4xx (a 404 before the server has the support address, 401, 403, 429, a timeout) is kept for later.
 */
const refused = (err: unknown) => err instanceof ApiError && (err.status === 400 || err.status === 413 || err.status === 422);

/**
 * sent: the server has it. dropped: turned down for good (or reports are off there); `status` is its answer.
 * later: no signal, a timeout or an answer that will hold for every report; stop and try all of them next time.
 * skip: the server failed on this one (5xx); try the ones behind it now and this one again next time.
 */
type Outcome = { kind: 'sent'; number: string; status: Report['status'] } | { kind: 'dropped'; status?: number } | { kind: 'later' } | { kind: 'skip' };

async function sendOne(item: Waiting): Promise<Outcome> {
  try {
    const res = await api<{ number?: unknown; status?: unknown } | null>(
      '/v2/support/report',
      { method: 'POST', body: JSON.stringify({ ...item.body, client_key: item.key, install_id: await installId() }) },
      SEND_TIMEOUT,
    );
    const number = typeof res?.number === 'string' ? res.number.trim() : '';
    // No number means reports are switched off on the server: it answered politely and kept nothing.
    return number ? { kind: 'sent', number, status: statusOf(res?.status) } : { kind: 'dropped' };
  } catch (err) {
    if (refused(err)) return { kind: 'dropped', status: (err as ApiError).status };
    return err instanceof ApiError && err.status >= 500 ? { kind: 'skip' } : { kind: 'later' };
  }
}

// What happened to a report filed just now, so fileReport can tell the person. Only reports someone is waiting on are
// noted, and each is read once, then forgotten.
const watching = new Set<string>();
const results = new Map<string, Outcome>();

/**
 * Takes a report out of the outbox once the server has answered, and remembers its ticket number for My reports. A
 * report of the person's own that waited on the phone and was then turned down stays listed as "could not be sent",
 * so it does not vanish without a word; one the person is looking at the screen for is told to them there instead.
 */
function settle(item: Waiting, out: Outcome, told: boolean): Promise<void> {
  return inLine(async () => {
    await Storage.setItem(OUTBOX_KEY, JSON.stringify((await readOutbox()).filter((w) => w.key !== item.key)));
    if (!item.mine) return;
    const title = titleOf(String(item.body.text ?? ''));
    const report: Report | null =
      out.kind === 'sent'
        ? { ref: item.key, number: out.number, status: out.status, title, created_at: item.at }
        : out.kind === 'dropped' && !told
          ? { ref: item.key, status: 'failed', title, created_at: item.at }
          : null;
    if (!report) return;
    const number = report.number;
    const known = (await readKnown()).filter((r) => r.ref !== item.key && (!number || r.number !== number));
    await Storage.setItem(KNOWN_KEY, JSON.stringify([report, ...known].slice(0, LIST_MAX)));
  });
}

/**
 * Sends what is waiting, oldest first. Returns false when the signal dropped and the rest should wait for next time.
 * A report the server failed on (5xx) is passed over for now, so one bad report never holds up the ones behind it.
 */
async function sendWaiting(): Promise<boolean> {
  const tried = new Set<string>();
  for (;;) {
    // A fresh read each time: a report filed while this runs is seen too. One already tried this round (passed over,
    // or it could not be taken out of the outbox) is not sent again now.
    const next = (await readOutbox()).find((w) => !tried.has(w.key));
    if (!next) return true;
    tried.add(next.key);
    const out = await sendOne(next);
    const told = watching.has(next.key);
    if (told) results.set(next.key, out);
    if (out.kind === 'later') return false;
    if (out.kind === 'skip') continue;
    await settle(next, out, told);
  }
}

let running: Promise<boolean> | null = null;
let again = false;

/** One send at a time. True when it went through the whole outbox; false when it stopped to wait for a signal. */
function runFlush(): Promise<boolean> {
  if (!isConfigured()) return Promise.resolve(true);
  if (running) {
    // Launch, foreground and a tap on Send can all land here. One send at a time; a late call gets one more look after.
    again = true;
    return running;
  }
  running = (async () => {
    try {
      do {
        again = false;
        if (!(await sendWaiting())) return false;
      } while (again);
      return true;
    } catch {
      return false; // Storage hiccup. Nothing is lost; the next foreground tries again.
    }
  })().finally(() => {
    running = null;
    again = false;
  });
  return running;
}

/** Sends reports that were made with no signal. Safe to call often; it never throws. */
export function flushReports(): Promise<void> {
  return runFlush().then(() => {});
}

// A counter keeps two reports made in the same millisecond apart.
let last = 0;
function newKey(): string {
  last = Math.max(Date.now(), last + 1);
  const hex = () => Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
  return `p-${last.toString(36)}-${hex()}${hex()}${hex()}${hex()}`;
}

/** Saves a report to the outbox, tries to send it once, and says what happened. Never throws. */
async function file(body: Body, mine: boolean): Promise<Filed> {
  const item: Waiting = { key: newKey(), at: new Date().toISOString(), body, mine };
  let full = false;
  try {
    await inLine(async () => {
      const waiting = await readOutbox();
      // Full: say so, rather than quietly deleting an older report the person was told is saved.
      if (waiting.length >= OUTBOX_MAX) full = true;
      else await Storage.setItem(OUTBOX_KEY, JSON.stringify([...waiting, item]));
    });
  } catch {
    // The phone could not save it (storage full?). Send it straight away instead; if that fails too, say so.
    const out: Outcome = isConfigured() ? await sendOne(item) : { kind: 'later' };
    if (out.kind === 'sent') return { ref: item.key, number: out.number, queued: false };
    return { ref: item.key, queued: false, failed: true, ...(out.kind === 'dropped' && out.status ? { status: out.status } : {}) };
  }
  if (full) return { ref: item.key, queued: false, failed: true, full: true };
  watching.add(item.key);
  const reachedEnd = await runFlush();
  // The call above may have joined a send that was already finishing and never looked at this report. If instead it
  // stopped to wait for a signal, do not try again now: that would only send the older report a second time.
  if (!results.has(item.key) && reachedEnd) await runFlush();
  const out = results.get(item.key);
  watching.delete(item.key);
  results.delete(item.key);
  if (out?.kind === 'sent') return { ref: item.key, number: out.number, queued: false };
  if (out?.kind === 'dropped') return { ref: item.key, queued: false, failed: true, ...(out.status ? { status: out.status } : {}) };
  return { ref: item.key, queued: true };
}

// ---- Report, my reports -----------------------------------------------------------------------------

/**
 * Files a problem report. It is saved on the phone first, then sent once; with no signal it waits and `queued` is
 * true. Check the text length (REPORT_MIN) and the email (validEmail) on the screen first: an email that does not
 * look like one is left out rather than letting the server turn the whole report away.
 */
export function fileReport(input: ReportInput): Promise<Filed> {
  const email = tidyEmail(input.email ?? '');
  const name = tidyText(input.name, 120);
  const screen = cleanScreen(input.screen);
  const body: Body = {
    text: tidyText(input.text, REPORT_MAX),
    source: input.source === 'form' ? 'form' : 'otis',
    ...(email && validEmail(email) ? { email, may_contact: input.may_contact === true } : {}),
    ...(name ? { name } : {}),
    ...(input.lang === 'en' || input.lang === 'es' ? { lang: input.lang } : {}),
    ...(screen ? { screen } : {}),
    ...deviceInfo(),
  };
  return file(body, true);
}

/**
 * "Report this answer" under an OTIS reply. Sends that one question and answer so a person can review it, through
 * the same outbox. This is the one time an OTIS question leaves the phone here, and only because the person just
 * chose to send it. Ask them to confirm before calling this.
 */
export function reportAnswer(input: { question: string; answer: string; modelKey: string; lang: 'en' | 'es'; note?: string }): Promise<Filed> {
  const body: Body = {
    text: tidyText(input.note, REPORT_MAX) || 'Flagged OTIS answer',
    source: 'otis_answer',
    question: tidyText(input.question, 500),
    answer: tidyText(input.answer, 2000),
    model_key: tidyText(input.modelKey, 60),
    lang: input.lang === 'es' ? 'es' : 'en',
    ...deviceInfo(),
  };
  return file(body, false);
}

const waitingReports = async (): Promise<Report[]> =>
  (await readOutbox()).filter((w) => w.mine).map((w) => ({ ref: w.key, status: 'queued' as const, title: titleOf(String(w.body.text ?? '')), created_at: w.at }));

/** This phone's reports as saved on the phone, newest first. No network: use it to draw the screen at once. */
export async function savedReports(): Promise<Report[]> {
  try {
    return newestFirst([...(await waitingReports()), ...(await readKnown())]);
  } catch {
    return [];
  }
}

/**
 * This phone's reports, newest first: the ones still waiting to send, then what the server holds, with each one's
 * status and the reply if there is one. With no signal it is the list saved on the phone. Never throws.
 */
export async function myReports(): Promise<Report[]> {
  if (isConfigured()) {
    try {
      // POST, so the install id is never part of a web address.
      const res = await api<{ tickets?: unknown } | null>('/v2/support/mine', { method: 'POST', body: JSON.stringify({ install_id: await installId() }) }, SEND_TIMEOUT);
      const tickets = res?.tickets;
      if (Array.isArray(tickets)) await inLine(async () => Storage.setItem(KNOWN_KEY, JSON.stringify(mergeReports(await readKnown(), tickets))));
    } catch {
      // No signal, or the phone could not save the list. Show what is saved.
    }
  }
  return savedReports();
}
