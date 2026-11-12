/**
 * Automatic crash reports. When the app's own code throws an error nobody caught, a short report is saved on the
 * phone and sent the next time the app comes to the front, so Trainovate hears about a bug without anyone having to
 * write in. It only sees errors in the app's JavaScript. If the phone itself closes the app (out of memory while OTIS
 * loads, say) nothing here runs, so never tell a person that every crash is reported.
 *
 * What a report holds: the error's name, message and stack, the screen's route, the app version, iPhone or Android,
 * the system version, the phone model, the time, and a random install id (the server keeps only a salted hash).
 * What it never holds: anything a person typed, OTIS questions or answers, names, emails, photos or location. Error
 * text is scrubbed before it is saved, because an error message can echo what was typed: web addresses lose
 * everything after the "?" or "#", a long id (a UUID, a hex token) becomes "[id]", and emails, phone numbers and long
 * numbers are blanked. A name inside an error message can still get through, so the screens say the report is built
 * to leave out what was typed, not that it never can.
 *
 * The switch in Settings ("Crash reports") is on unless the person turns it off. Off means off: nothing is recorded,
 * nothing is sent, and whatever was waiting on the phone is deleted, the same rule the usage count follows.
 *
 * Everything here is written so it cannot make a bad moment worse: saving is synchronous (the app may be about to
 * close), nothing throws, repeats are dropped, the queue is capped, and a failure to send a report is never itself
 * recorded as a crash.
 */
import Storage from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';

import { api, ApiError, isConfigured } from '../config';
import { installId } from '../install';
import { deviceInfo, type DeviceInfo } from './device';

const ON_KEY = 'crash_reports';
const BOX_KEY = 'crash_outbox';

/** At most this many wait on the phone. A screen that throws on every frame must not fill the phone or the server. */
export const CRASH_QUEUE_MAX = 20;
const NAME_MAX = 120;
const MESSAGE_MAX = 500;
const STACK_MAX = 6000;
const SAME_ERROR_MS = 10 * 60 * 1000; // the same error again within ten minutes says nothing new
const SEND_TIMEOUT = 5000;

type Crash = DeviceInfo & { client_key: string; name: string; message: string; stack: string; fatal: boolean; screen: string; at: string };

const onPhone = () => Platform.OS === 'ios' || Platform.OS === 'android';

/**
 * Everything a crash report sends, in plain words, for the Settings switch and the error screen. If what recordError
 * saves or sendWaiting adds ever changes, this changes with it.
 */
export const CRASH_REPORT_HOLDS =
  "what the error said and where in the app's code it happened, whether the app had to close, the screen you were on, the time, the app version, iPhone or Android, the system version, your phone model, and a random id for this app";

// ---- Scrubbing (pure, tested) -----------------------------------------------------------------------

/**
 * What follows the "?" or "#" in an address, up to a space, a quote mark or a bracket. A quote or a closing bracket
 * inside it does not end it ("?q=O'Brien" goes whole); only one that is followed by a space or the end does, so the
 * closing quote or bracket around an address stays.
 */
const QUERY = `[^\\s"<>]*?(?=['")\\].,;:!]*(?:\\s|$))`;
const URL_QUERY = new RegExp(`\\b([a-z][a-z0-9+.-]*:\\/\\/[^\\s?#"'<>)\\]]*)[?#]${QUERY}`, 'gi');
const PATH_QUERY = new RegExp(`(\\S)\\?[\\w%.~+-]*=${QUERY}`, 'g');

/**
 * Takes out what could name a person or a place: everything after the "?" or "#" in a web address, long ids (a UUID,
 * an iPhone app folder, a push token), emails, phone numbers and long runs of digits (coordinates). Short numbers stay:
 * "status 404" is useful and harmless.
 *
 * A whole id becomes one "[id]". It is never cut up by the number rules below: half an id left in the message would
 * differ on every phone, and the server would file one crash as hundreds of different ones.
 */
export function scrub(text: string): string {
  return text
    .replace(URL_QUERY, '$1')
    .replace(PATH_QUERY, '$1?')
    .replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, '[email]') // before the ids: "fred.ab12345678@acme.com" is an email, not an id
    // An id is cut where the hex ends, not where a word ends, so "cache_<id>.bin" and "<id>_<id>" are caught whole.
    .replace(/(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])/gi, '[id]')
    .replace(/(?<![0-9a-f])(?:0x)?[0-9a-f]{16,}(?![0-9a-f])/gi, '[id]')
    // A shorter hex id (a session, a cache key) that mixes digits and letters. Only standing on its own, so a word
    // with hex letters in it ("embedded2024") is left alone.
    .replace(/(?<![0-9a-z])(?:0x)?(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,15}(?![0-9a-z])/gi, '[id]')
    .replace(/\+?\d[\d\s().-]{7,}\d/g, '[number]')
    .replace(/\d{6,}/g, '[number]')
    .replace(/-?\d{1,3}\.\d{4,}/g, '[number]');
}

/**
 * Tidies a stack trace. Each "at ..." line is kept with its line and column, which carry no personal data and are
 * what finds the bug. A web address in a line is cut down to its file name, so the address of a development
 * computer is never sent. The lines above the first "at" repeat the error message and are dropped.
 */
export function scrubStack(stack: string): string {
  const frames = stack
    .split('\n')
    .map((frame) => frame.trim())
    .filter((frame) => /^at\b/.test(frame) || /^[^\s@]*@/.test(frame)) // Hermes and V8 say "at f (file:1:2)"; JavaScriptCore says "f@file:1:2"
    .map((frame) =>
      frame
        .replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, '[email]') // before the address is shortened, or "f@index.bundle" would look like one
        .replace(/[a-z][a-z0-9+.-]*:\/\/[^\s)]*/gi, (url) => {
          const where = /(:\d+){1,2}$/.exec(url)?.[0] ?? '';
          const path = url.slice(0, url.length - where.length).split(/[?#&]/)[0].replace(/\/+$/, '');
          return `${path.split('/').pop() || 'bundle'}${where}`;
        })
        .slice(0, 300),
    );
  return frames.join('\n').slice(0, STACK_MAX);
}

/** The route without its query, so an id or a search in the address is not sent: "/talk/12?x=1" becomes "/talk/12". */
const cleanScreen = (screen: unknown) => (typeof screen === 'string' ? screen.split(/[?#]/)[0].trim().slice(0, 120) : '');

/** The name, message and stack of whatever was thrown. People throw strings and plain objects too; an object is never printed, since it could hold anything. */
export function describeError(error: unknown): { name: string; message: string; stack: string } {
  let name = 'Error';
  let message = '';
  let stack = '';
  if (typeof error === 'string') message = error;
  else if (error && typeof error === 'object') {
    const e = error as { name?: unknown; message?: unknown; stack?: unknown };
    if (typeof e.name === 'string' && e.name) name = e.name;
    if (typeof e.message === 'string') message = e.message;
    if (typeof e.stack === 'string') stack = e.stack;
  } else if (error !== undefined && error !== null) message = String(error);
  // Cut before scrubbing as well as after: an error can carry a whole page of text, and this may run many times a second.
  return {
    name: scrub(name.slice(0, NAME_MAX * 4)).slice(0, NAME_MAX),
    message: scrub((message || 'No message').slice(0, MESSAGE_MAX * 4)).replace(/\s+/g, ' ').trim().slice(0, MESSAGE_MAX),
    stack: scrubStack(stack.slice(0, STACK_MAX * 4)),
  };
}

/** Two errors are the same when the name and the message match once numbers are ignored ("row 3" and "row 7"). */
const sameAs = (c: { name: string; message: string }) => `${c.name}|${c.message.replace(/\d+/g, '#')}`;

/**
 * Not a bug in the app: a request that found no signal or was cancelled, a server that answered with an error, and,
 * while developing, the bundler saying the code being typed does not compile yet. Expo's fetch (the app's fetch on
 * SDK 58) says "fetch failed: <the phone's own words>" for no signal and "The operation was aborted." for a timeout;
 * React Native's older fetch says "Network request failed" and "Aborted".
 */
function notABug(e: { name: string; message: string }): boolean {
  if (e.name === 'AbortError' || /^(Network request failed|Aborted|API \d{3})$/i.test(e.message)) return true;
  if (/^fetch failed:/i.test(e.message) || /^(the )?operation was aborted\.?$/i.test(e.message) || /^cancell?ed\.?$/i.test(e.message)) return true;
  return developing() && /^(Unable to resolve module|TransformError|SyntaxError: .*\(\d+:\d+\)|Metro |The development server)/.test(e.message);
}

/** True in a development build, where React Native shows its own red screen and warnings. */
const developing = () => typeof __DEV__ === 'undefined' || __DEV__ === true;

// ---- The switch -------------------------------------------------------------------------------------

/** On unless the person turned it off in Settings. If the phone's storage can't be read, nothing is recorded. */
export function crashReportsOn(): boolean {
  try {
    return Storage.getItemSync(ON_KEY) !== 'off';
  } catch {
    return false;
  }
}

/** The Settings switch. Off also deletes every report waiting on the phone: off means nothing is kept either. */
export function setCrashReportsOn(on: boolean): void {
  switchRead = null;
  try {
    Storage.setItemSync(ON_KEY, on ? 'on' : 'off');
    if (!on) {
      Storage.removeItemSync(BOX_KEY);
      seen.clear();
      fullUntil = 0;
    }
  } catch {
    // The phone could not save the choice. Nothing to do here; Settings reads it back and shows what was kept.
  }
}

// ---- Recording --------------------------------------------------------------------------------------

function readBox(): Crash[] {
  try {
    const list = JSON.parse(Storage.getItemSync(BOX_KEY) ?? '[]') as unknown;
    return Array.isArray(list) ? (list.filter((c) => c && typeof c === 'object' && typeof (c as Crash).client_key === 'string') as Crash[]) : [];
  } catch {
    return []; // a damaged value must not jam the queue
  }
}

const seen = new Map<string, number>(); // when each kind of error was last looked at, in this run of the app
let recording = false;
let screenNow = '';
let fullUntil = 0; // the box was full when last read: until then a new error that did not close the app is not looked at
const FULL_WAIT_MS = 60 * 1000;

// A screen that throws on every frame calls recordError hundreds of times a second. The switch is read from the
// phone's storage at most once a second for that, and each kind of error is looked at once in ten minutes, whether it
// was saved, was already waiting, found the box full or could not be written. So a storm of errors does not become a
// storm of storage reads.
let switchRead: { on: boolean; at: number } | null = null;
function switchOn(now: number): boolean {
  if (!switchRead || now - switchRead.at > 1000 || now < switchRead.at) switchRead = { on: crashReportsOn(), at: now };
  return switchRead.on;
}

/** The layout calls this as the route changes, so a crash caught by the global handler can say which screen it was on. */
export function noteScreen(route: string): void {
  screenNow = cleanScreen(route);
}

function newKey(): string {
  const hex = () => Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
  return `c-${Date.now().toString(36)}-${hex()}${hex()}${hex()}${hex()}`;
}

/**
 * Saves one error for sending later. Call it from an error boundary, or for an error that was caught and shown to the
 * person. `fatal` is true when the app cannot carry on. Synchronous and safe anywhere: it never throws, drops repeats
 * of the same error, and keeps at most CRASH_QUEUE_MAX waiting. Does nothing on the web or with crash reports off.
 */
export function recordError(error: unknown, opts: { fatal: boolean; screen?: string }): void {
  if (recording) return; // an error raised while saving an error must not loop
  recording = true;
  try {
    if (!onPhone()) return;
    const what = describeError(error);
    const fatal = opts?.fatal === true;
    if (!fatal && notABug(what)) return; // an error that closes the app is always worth a report
    const now = Date.now();
    const key = sameAs(what);
    // Looked at once in ten minutes for each kind of error, counted apart for errors that closed the app: a crash that
    // closes the app is still looked at after the same error was turned away (box full, a failed write) when it did not.
    const seenKey = `${key}|${fatal}`;
    if (now - (seen.get(seenKey) ?? -Infinity) < SAME_ERROR_MS) return; // checked first: it needs no storage
    if (!switchOn(now)) return;
    if (!fatal && now < fullUntil && now >= fullUntil - FULL_WAIT_MS) return; // the box was full a moment ago
    // Noted before anything below can return or throw: already waiting, no room, or a write that fails.
    if (seen.size >= 200) seen.clear();
    seen.set(seenKey, now);
    const box = readBox();
    const waiting = box.find((c) => sameAs(c) === key);
    if (waiting) {
      // Already waiting. If this time it closed the app, the report says so.
      if (fatal && !waiting.fatal) {
        waiting.fatal = true;
        Storage.setItemSync(BOX_KEY, JSON.stringify(box));
      }
      return;
    }
    if (box.length >= CRASH_QUEUE_MAX) {
      // Full. A crash that closes the app matters more than one that did not: it takes the place of the newest of those.
      const swap = fatal ? box.map((c) => c.fatal).lastIndexOf(false) : -1;
      if (swap < 0) {
        fullUntil = now + FULL_WAIT_MS;
        return;
      }
      box.splice(swap, 1);
    }
    box.push({ client_key: newKey(), ...what, fatal, screen: cleanScreen(opts?.screen) || screenNow, at: new Date(now).toISOString(), ...deviceInfo() });
    Storage.setItemSync(BOX_KEY, JSON.stringify(box));
  } catch {
    // Recording a crash must never cause one.
  } finally {
    recording = false;
  }
}

// ---- Catching ---------------------------------------------------------------------------------------

type Handler = (error: unknown, isFatal?: boolean) => void;
type Hermes = { enablePromiseRejectionTracker?: (options: { allRejections: boolean; onUnhandled: (id: number, rejection: unknown) => void; onHandled?: (id: number) => void }) => void };

let installed = false;

/**
 * Starts catching errors nobody else caught. Call it once when the app starts; more calls do nothing. It records the
 * error and then ALWAYS hands it on to the handler that was there before, so the red screen while developing and the
 * normal close in a store build behave exactly as they did. Skipped on the web.
 */
export function installCrashReporter(): void {
  if (installed) return;
  installed = true;
  try {
    if (!onPhone()) return;
    const utils = (globalThis as { ErrorUtils?: { getGlobalHandler?: () => Handler | undefined; setGlobalHandler?: (h: Handler) => void } }).ErrorUtils;
    if (utils && typeof utils.setGlobalHandler === 'function') {
      const previous = typeof utils.getGlobalHandler === 'function' ? utils.getGlobalHandler() : undefined;
      utils.setGlobalHandler((error, isFatal) => {
        try {
          recordError(error, { fatal: isFatal === true });
        } finally {
          previous?.(error, isFatal);
        }
      });
    }
    // A promise that fails with nobody listening is silent in a store build: React Native only watches for those
    // while developing. Hermes can tell us; the hook is internal, so it is used only if it is there, and left alone
    // while developing so React Native's own warning keeps working.
    const hermes = (globalThis as { HermesInternal?: Hermes | null }).HermesInternal;
    if (!developing() && hermes && typeof hermes.enablePromiseRejectionTracker === 'function') {
      hermes.enablePromiseRejectionTracker({
        allRejections: true,
        onUnhandled: (_id, rejection) => recordError(rejection, { fatal: false }),
        onHandled: () => {},
      });
    }
  } catch {
    // If the hooks cannot be set, the app runs as it did before. Errors caught by the error screen are still recorded.
  }
  // Send what earlier runs saved without waiting for the layout. If the layout throws on every launch, its own
  // "send at launch" never runs, and that is the crash Trainovate most needs to hear about.
  try {
    setTimeout(() => void flushCrashes(), 0);
  } catch {
    // No timers yet: the layout and the error screen send it instead.
  }
}

// ---- Sending ----------------------------------------------------------------------------------------

/**
 * True when the server said no to this report for good: it is malformed (400), too big (413) or failed a check (422).
 * Any other answer (a 404 before the server has the support address, 401, 429, a 5xx, a timeout) keeps it for later.
 */
const refused = (err: unknown) => err instanceof ApiError && (err.status === 400 || err.status === 413 || err.status === 422);

function dropFromBox(clientKey: string): void {
  fullUntil = 0;
  const left = readBox().filter((c) => c.client_key !== clientKey);
  if (left.length) Storage.setItemSync(BOX_KEY, JSON.stringify(left));
  else Storage.removeItemSync(BOX_KEY);
}

async function sendWaiting(): Promise<void> {
  const tried = new Set<string>();
  for (;;) {
    // Read again each time round: the switch may have been turned off, or a new crash saved, while one was sending.
    if (!crashReportsOn()) return;
    const next = readBox().find((c) => !tried.has(c.client_key));
    if (!next) return;
    tried.add(next.client_key);
    try {
      await api('/v2/support/crash', { method: 'POST', body: JSON.stringify({ ...next, install_id: await installId() }) }, SEND_TIMEOUT);
    } catch (err) {
      if (!refused(err)) return; // no signal: keep everything for next time
    }
    dropFromBox(next.client_key);
  }
}

let running: Promise<void> | null = null;

/**
 * Sends the crash reports waiting on the phone. Called at launch and each time the app comes to the front. Safe to
 * call often; it never throws, and a report that cannot be sent just waits. A failed send is never recorded as a crash.
 */
export function flushCrashes(): Promise<void> {
  if (!onPhone() || !isConfigured()) return Promise.resolve();
  if (running) return running;
  running = sendWaiting()
    .catch(() => {
      // Storage or network hiccup. The reports are still on the phone; the next foreground tries again.
    })
    .finally(() => {
      running = null;
    });
  return running;
}
