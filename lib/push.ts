import { Href, router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { LogLevel, NotificationClickEvent, NotificationWillDisplayEvent, OneSignal } from 'react-native-onesignal';

import { config } from './config';
import { refreshContent } from './live';

/**
 * Three separate opt-ins, matching Apple's rule that promotional pushes need their own consent:
 *   weekly_talk  - the Sunday toolbox talk (a feature of the app)
 *   alerts       - regulatory alerts published from GoHighLevel (a feature of the app)
 *   zero_hour    - a new Zero Hour episode, Thursdays (a feature of the app)
 *   offers       - news, free courses and offers (promotional, off by default)
 * The backend's cron sends each push to devices with the matching OneSignal tag set to "on".
 */
export type PushPrefs = { weeklyTalk: boolean; alerts: boolean; zeroHour: boolean; offers: boolean };
const OFF: PushPrefs = { weeklyTalk: false, alerts: false, zeroHour: false, offers: false };
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
    if (route) router.push(route);
    else if (data?.episode) router.push(`/zero-hour/${data.episode}`);
    else if (data?.issue) router.push(`/talk/${data.issue}`);
    else if (data?.feed_id && data.kind === 'alert') router.push(`/alert/${data.feed_id}`);
    else if (data?.feed_id) router.push('/learn');
  });
}

type PushData = {
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
const ID_ROUTE = /^\/(talk|alert|zero-hour)\/[A-Za-z0-9_-]{1,40}$/;

function safeRoute(route: unknown): Href | null {
  if (typeof route !== 'string') return null;
  if (FIXED_ROUTES.includes(route) || ID_ROUTE.test(route)) return route as Href;
  return null;
}

export async function getPrefs(): Promise<PushPrefs> {
  const raw = await Storage.getItem(PREFS_KEY);
  return raw ? { ...OFF, ...(JSON.parse(raw) as Partial<PushPrefs>) } : OFF;
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
  if (config.oneSignalAppId && (next.weeklyTalk || next.alerts || next.zeroHour || next.offers)) {
    const granted = await OneSignal.Notifications.requestPermission(true);
    await markAsked();
    if (!granted) {
      permissionDenied = true;
      next = OFF;
    }
  }
  if (config.oneSignalAppId) {
    const on = (v: boolean) => (v ? 'on' : 'off');
    OneSignal.User.addTags({ weekly_talk: on(next.weeklyTalk), alerts: on(next.alerts), zero_hour: on(next.zeroHour), offers: on(next.offers) });
  }
  await Storage.setItem(PREFS_KEY, JSON.stringify(next));
  return { prefs: next, permissionDenied };
}
