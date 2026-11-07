import Storage from 'expo-sqlite/kv-store';

/** The person running talks on this phone. Used to send finished sign-in sheets to their records. Stored on the phone only. */
export type Profile = { name: string; email: string; company: string };
const KEY = 'supervisor_profile';

export async function getProfile(): Promise<Profile> {
  const raw = await Storage.getItem(KEY);
  return raw ? (JSON.parse(raw) as Profile) : { name: '', email: '', company: '' };
}

export async function saveProfile(p: Profile) {
  await Storage.setItem(KEY, JSON.stringify({ name: p.name.trim(), email: p.email.trim().toLowerCase(), company: p.company.trim() }));
}

export const validEmail = (e: string) => /^\S+@\S+\.\S+$/.test(e.trim());
