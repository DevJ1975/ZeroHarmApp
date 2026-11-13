import { Href, router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { LogLevel, NotificationClickEvent, NotificationWillDisplayEvent, OneSignal } from 'react-native-onesignal';

import { config } from './config';
import { refreshContent } from './live';

/**
 * Three separate opt-ins, matching Apple's rule that promotional pushes need their own consent:
 *   monday_minute - the Monday Minute, Monday mornings (a feature of the app)
 *   weekly_talk  - the Sunday toolbox talk (a feature of the app)
 *   alerts       - regulatory alerts published from GoHighLevel (a feature of the app)
 *   zero_hour    - a new Zero Hour episode, Thursdays (a feature of the app)
 *   offers       - news, free courses and offers (promotional, off by default)
 * The backend's cron sends each push to devices with the matching OneSignal tag set to "on".
 */
export type PushPrefs = { mondayMinute: boolean; weeklyTalk: boolean; alerts: boolean; zeroHour: boolean; offers: boolean };
const OFF: PushPrefs = { mondayMinute: false, weeklyTalk: false, alerts: false, zeroHour: false, offers: false };
const PREFS_KEY = 'push_prefs';
const ASKED_KEY = 'push_asked';

let started = false;

export function startPush() {
  if (started || !config.oneSignalAppId) return;
  started = true;
  if (__DEV__) OneSignal.Debug.setLogLevel(LogLevel.Warn);
  OneSignal.initialize(config.oneSignalAppId); // does NOT prompt; we ask at a good moment instead

  // A push arriving while the app is open still shows; if it says "refresh", reload the content now.
  OneSignal.Notifications.addEventListener('foregroundWillDisplay', (event: NotificationWillDisplayEvent) => {
    if (readData(event.getNotification().additionalData)?.refresh) refreshContent();
  });

  // Tapping a push opens what it is about.
  OneSignal.Notifications.addEventListener('click', (event: NotificationClickEvent) => {
    const data = readData(event.notification.additionalData);
    if (data?.refresh) refreshContent();
    const route = safeRoute(data?.route);
    const mondayMinute = safeId(data?.monday_minute);
    const episode = safeId(data?.episode);
    const issue = safeId(data?.issue);
    const feedId = safeId(data?.feed_id);
    if (route) router.push(route);
    else if (mondayMinute) router.push(`/monday/${mondayMinute}`);
    else if (episode) router.push(`/zero-hour/${episode}`);
    else if (issue) router.push(`/talk/${issue}`);
    else if (feedId && data?.kind === 'alert') router.push(`/alert/${feedId}`);
    else if (feedId) router.push('/learn');
  });
}

type PushData = {
  monday_minute?: number | string;
  issue?: number | string;
  feed_id?: number | string;
  kind?: string;
  episode?: number | string;
  route?: unknown;
  refresh?: boolean | string;
};

function readData(raw: object | undefined): (PushData & { refresh: boolean }) | undefined {
  if (!raw) return undefined;
  const data = raw as PushData;
  return { ...data, refresh: data.refresh === true || data.refresh === 'true' };
}

// Only these screens can be opened from a push, so a bad payload can't send people somewhere odd.
const FIXED_ROUTES = ['/learn', '/otis', '/archive'];
const ID_ROUTE = /^\/(talk|alert|zero-hour|monday)\/[A-Za-z0-9_-]{1,40}$/;

// The backend sends issue, episode and feed_id as whole numbers, so anything else is ignored.
function safeId(id: unknown): string | null {
  if (typeof id !== 'number' && typeof id !== 'string') return null;
  const text = String(id);
  return /^\d{1,12}$/.test(text) ? text : null;
}

function safeRoute(route: unknown): Href | null {
  if (typeof route !== 'string') return null;
  if (FIXED_ROUTES.includes(route) || ID_ROUTE.test(route)) return route as Href;
  return null;
}

// Always hands back a fresh object, so a caller editing it can't change the defaults.
// Only a saved `true` counts as on, so a garbled row (say offers: "false") can never opt someone in.
export async function getPrefs(): Promise<PushPrefs> {
  const saved = readSaved(await Storage.getItem(PREFS_KEY));
  const on = (key: keyof PushPrefs) => saved?.[key] === true;
  return { mondayMinute: on('mondayMinute'), weeklyTalk: on('weeklyTalk'), alerts: on('alerts'), zeroHour: on('zeroHour'), offers: on('offers') };
}

// A missing or corrupted row reads as nothing saved, rather than breaking the settings screen.
function readSaved(raw: string | null): Partial<Record<keyof PushPrefs, unknown>> | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function hasBeenAsked() {
  return (await Storage.getItem(ASKED_KEY)) === 'yes';
}

export async function markAsked() {
  await Storage.setItem(ASKED_KEY, 'yes');
}

/** Saves the choice on the device and mirrors it to OneSignal tags. Asks iOS/Android permission the first time a switch turns on. */
export async function setPrefs(next: PushPrefs): Promise<{ prefs: PushPrefs; permissionDenied: boolean }> {
  let permissionDenied = false;
  if (config.oneSignalAppId && (next.mondayMinute || next.weeklyTalk || next.alerts || next.zeroHour || next.offers)) {
    const granted = await OneSignal.Notifications.requestPermission(true);
    await markAsked();
    if (!granted) {
      permissionDenied = true;
      next = { ...OFF }; // a fresh copy, so editing the result can't change the defaults
    }
  }
  if (config.oneSignalAppId) {
    const on = (v: boolean) => (v ? 'on' : 'off');
    OneSignal.User.addTags({ monday_minute: on(next.mondayMinute), weekly_talk: on(next.weeklyTalk), alerts: on(next.alerts), zero_hour: on(next.zeroHour), offers: on(next.offers) });
  }
  await Storage.setItem(PREFS_KEY, JSON.stringify(next));
  return { prefs: next, permissionDenied };
}
