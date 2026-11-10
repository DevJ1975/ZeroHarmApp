/**
 * The anonymous usage count. Once a day the app tells the server it was opened, so Trainovate can see how many phones
 * use it and roughly where (city, state, country). It sends a random install id (the server keeps only a salted hash),
 * the platform, the app version and, when the weather feature already knows it, the city. No name, email or coordinates.
 * The switch in Settings turns it off.
 */
import Constants from 'expo-constants';
import Storage from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';

import { api, isConfigured } from './config';
import { installId } from './install';

export type Place = { city: string; region: string; country: string };

const ON_KEY = 'usage_count';
const SENT_KEY = 'usage_sent';
const PLACE_KEY = 'last_place';

/** The phone's own calendar day, 'YYYY-MM-DD'. Local time, so "once a day" matches the day the person sees. */
export function localDay(date: Date): string {
  const two = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;
}

/** "Las Vegas, NV" from the weather answer becomes city, state and country. The weather service only covers the US. */
export function parsePlace(text: string | null | undefined): Place | null {
  const match = /^([^,]{1,80}),\s*([A-Za-z]{2})$/.exec((text ?? '').trim());
  if (!match) return null;
  const city = match[1].trim();
  return city ? { city, region: match[2].toUpperCase(), country: 'US' } : null;
}

/** On unless the person turned it off in Settings. */
export async function getUsageOn(): Promise<boolean> {
  return (await Storage.getItem(ON_KEY)) !== 'off';
}

export async function setUsageOn(on: boolean): Promise<void> {
  await Storage.setItem(ON_KEY, on ? 'on' : 'off');
  // Off means nothing is collected either: forget the remembered city.
  if (!on) await Storage.removeItem(PLACE_KEY);
}

async function knownPlace(now: Date): Promise<Place | null> {
  const raw = await Storage.getItem(PLACE_KEY);
  if (!raw) return null;
  const saved = JSON.parse(raw) as { place?: string; at?: number };
  // Only a city learned today counts. Yesterday's may be the wrong town for a driver or a travelling crew; without one
  // the open goes out plain and is filled in when today's weather answers.
  if (typeof saved.at !== 'number' || localDay(new Date(saved.at)) !== localDay(now)) return null;
  return parsePlace(saved.place);
}

async function send(): Promise<void> {
  try {
    if (!(await getUsageOn())) return;
    const now = new Date();
    const day = localDay(now);
    const place = await knownPlace(now).catch(() => null);
    const raw = await Storage.getItem(SENT_KEY);
    let sent: { day?: string; place?: boolean } = {};
    try {
      sent = (raw && JSON.parse(raw)) || {};
    } catch {
      // A damaged value must not silence the count for good. Treat it as not sent; the save below rewrites it.
    }
    // Already counted today. The one exception: the city became known after today's open went out without one.
    if (sent.day === day && (sent.place || !place)) return;
    await api(
      '/v2/app/open',
      {
        method: 'POST',
        body: JSON.stringify({
          install_id: await installId(),
          platform: Platform.OS,
          app_version: (Constants.expoConfig?.version ?? '').slice(0, 20),
          ...(place ? { place } : {}),
        }),
      },
      5000,
    );
    // Marked only after the server said OK, so a dead spot tries again the next time the app comes to the front.
    await Storage.setItem(SENT_KEY, JSON.stringify({ day, place: Boolean(place) }));
  } catch {
    // No signal or a server hiccup. Nothing is lost; the next foreground tries again.
  }
}

let running: Promise<void> | null = null;
let again = false;

/** Tell the server the app was opened, at most once per local day. Safe to call often; it never throws. */
export function reportOpen(): Promise<void> {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return Promise.resolve();
  if (!isConfigured()) return Promise.resolve();
  if (running) {
    // Launch and foreground can both call this. One send at a time; a call that lands mid-send gets one more look after.
    again = true;
    return running;
  }
  running = (async () => {
    do {
      again = false;
      await send();
    } while (again);
  })().finally(() => {
    running = null;
  });
  return running;
}

/**
 * The weather feature calls this with its "City, ST". The city is kept on the phone for the daily count. If today's open
 * already went out without a city, it goes once more so the server can fill it in (the server keeps one row per day).
 */
export async function rememberPlace(place: string): Promise<void> {
  try {
    if (!parsePlace(place) || !(await getUsageOn())) return;
    await Storage.setItem(PLACE_KEY, JSON.stringify({ place, at: Date.now() }));
    await reportOpen();
  } catch {
    // Never let the usage count get in the way of the weather.
  }
}
