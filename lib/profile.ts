import Storage from 'expo-sqlite/kv-store';

/** The person running talks on this phone. Used to send finished sign-in sheets to their records. Stored on the phone only. */
export type Profile = { name: string; email: string; company: string };
const KEY = 'supervisor_profile';

export async function getProfile(): Promise<Profile> {
  const raw = await Storage.getItem(KEY);
  return raw ? (JSON.parse(raw) as Profile) : { name: '', email: '', company: '' };
}

export async function saveProfile(p: Profile) {
  await Storage.setItem(KEY, JSON.stringify({ name: p.name.trim(), email: tidyEmail(p.email), company: p.company.trim() }));
}

/**
 * Tidies an email the way people mistype it on a phone: spaces around it, a full stop or comma left on the end, capitals.
 * "Maria@Example.com. " becomes "maria@example.com".
 */
export const tidyEmail = (e: string) => e.trim().replace(/[\s.,;]+$/, '').toLowerCase();

// The part before the @: letters, digits and the symbols an address may hold, in dot-separated pieces (no leading,
// trailing or double dots). Each domain label starts and ends with a letter or digit, and the last one is 2+ letters.
const LOCAL = /^[a-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*$/i;
const DOMAIN = /^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;

/**
 * True when the server will take the address. This is a little stricter than the server (plain ASCII only), never
 * looser, so a sign-up the phone accepts is never turned away later. Tidies first, so check and send tidyEmail(e).
 * Used by the welcome screen, Settings, the crew sign-in sheet and Suggest a topic.
 */
export function validEmail(e: string): boolean {
  const email = tidyEmail(e);
  if (email.length > 254) return false;
  const parts = email.split('@');
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  return local.length <= 64 && LOCAL.test(local) && DOMAIN.test(domain);
}
