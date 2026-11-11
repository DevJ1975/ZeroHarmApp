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
export type Account = { state: 'in' | 'out' | 'fix'; name: string; email: string };

function readPair(raw: string | null): { name: string; email: string } {
  try {
    const v = JSON.parse(raw ?? '{}') as { name?: unknown; email?: unknown } | null;
    return { name: typeof v?.name === 'string' ? v.name : '', email: typeof v?.email === 'string' ? v.email : '' };
  } catch {
    return { name: '', email: '' };
  }
}

export async function getAccount(): Promise<Account> {
  if (await signedIn()) return { state: 'in', ...readPair(await Storage.getItem(ACCOUNT_KEY)) };
  const fix = await Storage.getItem(NEEDS_FIX_KEY);
  if (fix) return { state: 'fix', ...readPair(fix) };
  return { state: 'out', name: '', email: '' };
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
const changeOutbox = (change: (box: Outbox) => Outbox) => inLine(async () => Storage.setItem(OUTBOX_KEY, JSON.stringify(change(await readOutbox()))));

/** True when the server said no for good (a bad email, say). "Slow down" (429) and timeouts are worth another try. */
const refused = (err: unknown) => err instanceof ApiError && err.status >= 400 && err.status < 500 && err.status !== 408 && err.status !== 429;
/** True when the server said what was sent is wrong (a bad email, say), so the person needs to fix it and sign in again. */
const badInput = (err: unknown) => err instanceof ApiError && (err.status === 400 || err.status === 422);

/** Sends what is waiting. Returns false when the signal dropped and the rest should wait for next time. */
async function sendWaiting(): Promise<boolean> {
  const { remove, signup } = await readOutbox();
  if (remove) {
    try {
      await api('/signups/remove/', { method: 'POST', body: JSON.stringify({ install_id: await installId() }) });
    } catch (err) {
      if (!refused(err)) return false; // keep it, and hold the sign-up behind it so the order stays right
    }
    // Cleared only if it is still the same one: the person may have tapped something while the request was in the air.
    await changeOutbox((now) => (now.remove?.at === remove.at ? { ...now, remove: undefined } : now));
  }
  if (signup) {
    // A removal that arrived while the first request was out comes first. The next pass sends it.
    if ((await readOutbox()).remove) return true;
    let bad = false;
    try {
      await api('/signups/', { method: 'POST', body: JSON.stringify({ ...signup.body, install_id: await installId() }) });
    } catch (err) {
      if (!refused(err)) return false;
      bad = badInput(err);
    }
    await inLine(async () => {
      const now = await readOutbox();
      if (now.signup?.at !== signup.at) return; // signed in again or removed meanwhile: that newer tap wins
      await Storage.setItem(OUTBOX_KEY, JSON.stringify({ ...now, signup: undefined }));
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
    await Storage.setItem(OUTBOX_KEY, JSON.stringify({ ...(await readOutbox()), signup: { at: stamp(), body } }));
  });
  flushAccount(); // not awaited: the person never waits on the network
}

/**
 * "Remove my info": asks the server to unlink this phone from the sign-up (the server removes the sign-up, and the
 * newsletter with it, only when no other phone of that person is linked), and clears the name, email and signed-in
 * state here. A sign-up that never left the phone is cancelled.
 */
export async function removeMyInfo(): Promise<void> {
  // The sign-in sheet profile is cleared only while it still holds the account's details. If someone else on the crew
  // has since put their own details there, theirs stay.
  const account = readPair(await Storage.getItem(ACCOUNT_KEY));
  const sheet = await getProfile();
  if (!sheet.email || (account.email && sheet.email.toLowerCase() === account.email.toLowerCase())) {
    await saveProfile({ name: '', email: '', company: '' });
  }
  await inLine(async () => {
    await Storage.removeItem(SIGNED_IN_KEY);
    await Storage.removeItem(ACCOUNT_KEY);
    await Storage.removeItem(NEEDS_FIX_KEY);
    await Storage.setItem(OUTBOX_KEY, JSON.stringify({ remove: { at: stamp() } }));
  });
  flushAccount();
}
