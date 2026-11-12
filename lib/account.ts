/**
 * The free sign-in: a name and an email, no password. It is asked for once on the welcome screen and can be skipped.
 * Signing in saves the name and email on the phone (so sign-in sheets fill themselves in) and puts the person on the
 * Zero Harm Weekly email list. Nothing here waits on the network: the request sits in an outbox on the phone and goes
 * out when there is a signal, the same idea as the vote outbox in monday.ts.
 */
import Storage from 'expo-sqlite/kv-store';

import { api, ApiError, isConfigured } from './config';
import { installId } from './install';
import { getProfile, saveProfile, tidyEmail, validEmail } from './profile';

/** The exact line shown under the button. It is sent with the sign-up so the server keeps what the person agreed to. */
export const CONSENT_LINE = "You'll get Zero Harm Weekly by email each week. Unsubscribe anytime.";
export const FREE_LINE = 'Free for every crew. No cost, no trial, no card.';

const WELCOME_KEY = 'welcome_done';
const HOWTO_KEY = 'howto_done';
const SIGNED_IN_KEY = 'account_signed_in';
// The name and email this phone signed up with. Kept apart from the sign-in sheet profile, which crew sign-in can change.
const ACCOUNT_KEY = 'account_profile';
// Set when the server turned the sign-up down as bad input. Holds what was typed, so Settings can show it to fix.
const NEEDS_FIX_KEY = 'account_needs_fix';
const OUTBOX_KEY = 'account_outbox';
// What the server last said that the person has to be told. See AccountNotice.
const NOTICE_KEY = 'account_notice';

const NAME_MAX = 120;
const COMPANY_MAX = 120;

// ---- Pure helpers (tested) --------------------------------------------------------------------------

/** Trims, and turns runs of spaces into one, so "  Maria   Lopez " is saved as "Maria Lopez". */
export const cleanName = (name: string) => name.replace(/\s+/g, ' ').trim().slice(0, NAME_MAX);

export const cleanEmail = tidyEmail;

export type SignInErrors = { name?: string; email?: string };

/** Checks what was typed. Hands back the cleaned values and a plain message for each field that needs fixing. */
export function checkSignIn(input: { name: string; email: string }): { name: string; email: string; errors: SignInErrors; ok: boolean } {
  const name = cleanName(input.name);
  const email = cleanEmail(input.email);
  const errors: SignInErrors = {};
  if (!name) errors.name = 'Enter your name.';
  if (!email) errors.email = 'Enter your email.';
  else if (!validEmail(email)) errors.email = 'Check the email address. It should look like name@example.com.';
  return { name, email, errors, ok: !errors.name && !errors.email };
}

export type FirstRun = { welcomeDone: boolean; howToDone: boolean };
export type FirstScreen = 'opening' | 'welcome' | 'howto' | 'app';

/**
 * What is on screen when the app starts. The holiday opening screen always plays alone and first. Then, one time only,
 * the welcome sign-in, then the how-to. After that the app opens straight on the Monday tab.
 */
export function whatToShow({ opening, welcomeDone, howToDone }: FirstRun & { opening: boolean }): FirstScreen {
  if (opening) return 'opening';
  if (!welcomeDone) return 'welcome';
  if (!howToDone) return 'howto';
  return 'app';
}

// ---- First run --------------------------------------------------------------------------------------

/**
 * Read at launch, before the first frame, so the tabs never flash ahead of the welcome screen. If the phone's storage
 * can't be read, the app just opens: a welcome screen that came back on every launch would be worse than none.
 */
export function firstRun(): FirstRun {
  try {
    return { welcomeDone: Storage.getItemSync(WELCOME_KEY) === 'yes', howToDone: Storage.getItemSync(HOWTO_KEY) === 'yes' };
  } catch {
    return { welcomeDone: true, howToDone: true };
  }
}

export const markHowToDone = () => Storage.setItem(HOWTO_KEY, 'yes');

/** "Not now": the person goes in without signing in, and the welcome screen does not come back. */
export async function skip(): Promise<void> {
  await Storage.setItem(WELCOME_KEY, 'yes');
}

export async function signedIn(): Promise<boolean> {
  return (await Storage.getItem(SIGNED_IN_KEY)) === 'yes';
}

/**
 * What Settings shows under "Your account". 'in' with the name and email signed up with; 'fix' when the server turned
 * the sign-up down, with what was typed so it can be corrected; 'out' otherwise.
 */
export type Account = { state: 'in' | 'out' | 'fix'; name: string; email: string; notice?: AccountNotice };

/**
 * Two answers from the server that the screen must not paper over.
 * 'not_changed': the email was already signed up from another phone, or from this phone before the app was deleted and
 *   installed again (a new install gets a new id, so the server cannot tell the two apart). This phone is linked to
 *   it, but the name, company and offers choice just typed were NOT saved. Never show them as saved.
 * 'removal_pending': "Remove my info" came from a phone that did not make the sign-up. Nothing was deleted; a person at
 *   Trainovate was asked to do it. Never say "Removed".
 */
export type AccountNotice = 'not_changed' | 'removal_pending';

/** What "Remove my info" did. 'waiting': no signal yet, the request is saved on the phone and goes out later. */
export type RemoveOutcome = 'removed' | 'pending' | 'waiting';

/** Plain lines for these answers, so every screen says the same thing. */
export const NOT_CHANGED_LINE =
  'This email is already signed up from another phone or an earlier install of the app, so your name, company and offers choice were not changed. Contact support and we will change them.';
/** The same line for a build with no support address, where there is no "Contact support" button to point to. */
export const NOT_CHANGED_LINE_NO_CONTACT =
  'This email is already signed up from another phone or an earlier install of the app, so your name, company and offers choice were not changed.';
/** The line to show: it says "Contact support" only when the screen can show a way to do it. */
export const notChangedLine = (supportEmail: string): string => (supportEmail.trim() !== '' ? NOT_CHANGED_LINE : NOT_CHANGED_LINE_NO_CONTACT);
export const REMOVED_LINE = 'Removed. Your name and email are cleared from this phone. If this phone made your sign-up, the sign-up is deleted too.';
export const REMOVAL_PENDING_LINE = 'We got your request. A person will remove your info.';
export const REMOVAL_WAITING_LINE = 'Cleared from this phone. Your request will send when you have signal.';
/** The text of the "Remove my info?" question. It describes what really happens, for the phone that signed up and for any other. */
export const REMOVE_CONFIRM_TEXT =
  'This clears your name and email from this phone. If this phone made your sign-up, the sign-up is deleted and the app stops adding you to Zero Harm Weekly. ' +
  'If another phone made it, nothing is deleted yet: we ask a person at Trainovate to remove it. If you joined Zero Harm Weekly another way, use Unsubscribe in any of its emails.';

/** The line for what "Remove my info" did. */
export const removalLine = (outcome: RemoveOutcome) => (outcome === 'pending' ? REMOVAL_PENDING_LINE : outcome === 'waiting' ? REMOVAL_WAITING_LINE : REMOVED_LINE);

/** "Signed in as Maria Lopez, maria@example.com". Just the email when the server did not take the name from this phone. */
export const signedInAs = (account: { name: string; email: string }) => `Signed in as ${[account.name, account.email].filter(Boolean).join(', ')}`;

const REMOVAL_NOTICE_DAYS = 30; // after this the line has done its job and Settings goes quiet again

async function readNotice(): Promise<AccountNotice | null> {
  try {
    const v = JSON.parse((await Storage.getItem(NOTICE_KEY)) ?? 'null') as { kind?: unknown; at?: unknown } | null;
    if (v?.kind === 'not_changed') return 'not_changed';
    if (v?.kind === 'removal_pending' && typeof v.at === 'number' && Date.now() - v.at < REMOVAL_NOTICE_DAYS * 86_400_000) return 'removal_pending';
  } catch {
    // a damaged value is the same as no notice
  }
  return null;
}
const saveNotice = (kind: AccountNotice) => Storage.setItem(NOTICE_KEY, JSON.stringify({ kind, at: Date.now() }));

function readPair(raw: string | null): { name: string; email: string } {
  try {
    const v = JSON.parse(raw ?? '{}') as { name?: unknown; email?: unknown } | null;
    return { name: typeof v?.name === 'string' ? v.name : '', email: typeof v?.email === 'string' ? v.email : '' };
  } catch {
    return { name: '', email: '' };
  }
}

export async function getAccount(): Promise<Account> {
  const notice = await readNotice();
  if (await signedIn()) return { state: 'in', ...readPair(await Storage.getItem(ACCOUNT_KEY)), ...(notice === 'not_changed' ? { notice } : {}) };
  const fix = await Storage.getItem(NEEDS_FIX_KEY);
  if (fix) return { state: 'fix', ...readPair(fix) };
  return { state: 'out', name: '', email: '', ...(notice === 'removal_pending' ? { notice } : {}) };
}

// ---- Outbox -----------------------------------------------------------------------------------------

type Signup = {
  email: string;
  name: string;
  company?: string;
  wants_offers?: boolean; // left out unless the person chose, so an earlier "yes" on the server is not switched off
  source: 'welcome' | 'settings';
  consent: string;
};
/** At most one removal and one sign-up wait here. The removal always goes first: it is always the older of the two. */
type Outbox = { remove?: { at: number }; signup?: { at: number; body: Signup } };

async function readOutbox(): Promise<Outbox> {
  try {
    const box = JSON.parse((await Storage.getItem(OUTBOX_KEY)) ?? '{}') as Outbox | null;
    return box && typeof box === 'object' ? box : {};
  } catch {
    return {}; // a damaged value must not jam the queue
  }
}

// Changes go one at a time, each on a fresh read, so a tap that lands while a send is finishing is never overwritten.
let line: Promise<unknown> = Promise.resolve();
function inLine(step: () => Promise<void>): Promise<void> {
  const next = line.then(step);
  line = next.catch(() => {});
  return next;
}

/** True when the server said no for good (a bad email, say). "Slow down" (429) and timeouts are worth another try. */
const refused = (err: unknown) => err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429;
/** True when the server said what was sent is wrong (a bad email, say), so the person needs to fix it and sign in again. */
const badInput = (err: unknown) => err instanceof ApiError && (err.status === 400 || err.status === 422);

// What became of the removal that was last sent, so removeMyInfo can tell the person. `at` is the removal's own stamp.
let removalTried = 0;
let removalDone: { at: number; pending: boolean } | null = null;

/** Sends what is waiting. Returns false when the signal dropped and the rest should wait for next time. */
async function sendWaiting(): Promise<boolean> {
  const { remove, signup } = await readOutbox();
  if (remove) {
    let pending = false;
    removalTried = remove.at;
    try {
      const res = await api<{ pending?: unknown } | null>('/signups/remove/', { method: 'POST', body: JSON.stringify({ install_id: await installId() }) });
      // This phone did not make the sign-up, so the server deleted nothing and asked a person to look at it.
      pending = res?.pending === true;
    } catch (err) {
      if (!refused(err)) return false; // keep it, and hold the sign-up behind it so the order stays right
    }
    removalDone = { at: remove.at, pending };
    await inLine(async () => {
      const now = await readOutbox();
      // Cleared only if it is still the same one: the person may have tapped something while the request was in the air.
      if (now.remove?.at !== remove.at) return;
      await Storage.setItem(OUTBOX_KEY, JSON.stringify({ ...now, remove: undefined }));
      // A sign-in made since then is the newer wish: the notice would only confuse.
      if (pending && !now.signup) await saveNotice('removal_pending');
    });
  }
  if (signup) {
    // A removal that arrived while the first request was out comes first. The next pass sends it.
    if ((await readOutbox()).remove) return true;
    let bad = false;
    let unchanged = false;
    try {
      const res = await api<{ changed?: unknown } | null>('/signups/', { method: 'POST', body: JSON.stringify({ ...signup.body, install_id: await installId() }) });
      // Another phone made this sign-up. This one is linked to it, and nothing that was typed here was saved.
      unchanged = res?.changed === false;
    } catch (err) {
      if (!refused(err)) return false;
      bad = badInput(err);
    }
    await inLine(async () => {
      const now = await readOutbox();
      if (now.signup?.at !== signup.at) return; // signed in again or removed meanwhile: that newer tap wins
      await Storage.setItem(OUTBOX_KEY, JSON.stringify({ ...now, signup: undefined }));
      if (unchanged) {
        // The phone must not show a name the server did not take. The email is true: this phone is linked to it.
        await Storage.setItem(ACCOUNT_KEY, JSON.stringify({ name: '', email: signup.body.email }));
        await saveNotice('not_changed');
      } else {
        await Storage.removeItem(NOTICE_KEY);
      }
      if (bad) {
        // The phone must not keep saying "Signed in" for a sign-up the server never kept.
        await Storage.removeItem(SIGNED_IN_KEY);
        await Storage.removeItem(ACCOUNT_KEY);
        await Storage.setItem(NEEDS_FIX_KEY, JSON.stringify({ name: signup.body.name, email: signup.body.email }));
      }
    });
  }
  return true;
}

let running: Promise<void> | null = null;
let again = false;

/** Sends a sign-up or removal that was made with no signal. Safe to call often; it never throws. */
export function flushAccount(): Promise<void> {
  if (!isConfigured()) return Promise.resolve();
  if (running) {
    // Launch, foreground and a tap can all land here. One send at a time; a late call gets one more look after.
    again = true;
    return running;
  }
  running = (async () => {
    try {
      do {
        again = false;
        if (!(await sendWaiting())) break;
      } while (again);
    } catch {
      // Storage hiccup. Nothing is lost; the next foreground tries again.
    }
  })().finally(() => {
    running = null;
    again = false;
  });
  return running;
}

// A counter keeps two taps in the same millisecond apart.
let last = 0;
const stamp = () => (last = Math.max(Date.now(), last + 1));

// ---- Sign in, remove --------------------------------------------------------------------------------

/**
 * Signs the person in. The name and email are saved on the phone right away and the welcome screen is marked done, so
 * they are in the app at once even in a dead spot. The sign-up itself is queued and sent in the background.
 * Check the input with checkSignIn first.
 */
export async function signIn(input: { name: string; email: string; company?: string; source?: 'welcome' | 'settings'; wantsOffers?: boolean }): Promise<void> {
  const name = cleanName(input.name);
  const email = cleanEmail(input.email);
  const prev = await getProfile();
  const company = (input.company ?? prev.company).trim().slice(0, COMPANY_MAX);
  await saveProfile({ name, email, company });
  const body: Signup = {
    email,
    name,
    ...(company ? { company } : {}),
    ...(input.wantsOffers === undefined ? {} : { wants_offers: input.wantsOffers }),
    source: input.source ?? 'welcome',
    consent: CONSENT_LINE,
  };
  // In line with the outbox, so a refusal of an older sign-up that lands now cannot sign this one out.
  await inLine(async () => {
    await Storage.setItem(ACCOUNT_KEY, JSON.stringify({ name, email }));
    await Storage.setItem(SIGNED_IN_KEY, 'yes');
    await Storage.setItem(WELCOME_KEY, 'yes');
    await Storage.removeItem(NEEDS_FIX_KEY);
    await Storage.removeItem(NOTICE_KEY); // what the server said about an earlier sign-in or removal no longer applies
    await Storage.setItem(OUTBOX_KEY, JSON.stringify({ ...(await readOutbox()), signup: { at: stamp(), body } }));
  });
  flushAccount(); // not awaited: the person never waits on the network
}

/**
 * "Remove my info": clears the name, email and signed-in state on this phone at once, and asks the server to remove
 * the sign-up. What the server does depends on which phone asks. The phone that made the sign-up: it is deleted, and
 * the newsletter with it ('removed'). Any other phone: nothing is deleted, the phone is unlinked and a person at
 * Trainovate is asked to remove it ('pending'), so say "We got your request", never "Removed". With no signal the
 * request waits on the phone ('waiting'). A sign-up that never left the phone is cancelled.
 * This one does wait for the server (a few seconds at most), because the screen has to tell the truth about it.
 */
export async function removeMyInfo(): Promise<RemoveOutcome> {
  // The sign-in sheet profile is cleared only while it still holds the account's details. If someone else on the crew
  // has since put their own details there, theirs stay.
  const account = readPair(await Storage.getItem(ACCOUNT_KEY));
  const sheet = await getProfile();
  if (!sheet.email || (account.email && sheet.email.toLowerCase() === account.email.toLowerCase())) {
    await saveProfile({ name: '', email: '', company: '' });
  }
  const at = stamp();
  await inLine(async () => {
    await Storage.removeItem(SIGNED_IN_KEY);
    await Storage.removeItem(ACCOUNT_KEY);
    await Storage.removeItem(NEEDS_FIX_KEY);
    await Storage.removeItem(NOTICE_KEY);
    await Storage.setItem(OUTBOX_KEY, JSON.stringify({ remove: { at } }));
  });
  await flushAccount();
  // The call above may have joined a send that was already on its way out and never looked at this removal.
  if (removalTried !== at) await flushAccount();
  if (removalDone?.at !== at) return 'waiting';
  return removalDone.pending ? 'pending' : 'removed';
}
