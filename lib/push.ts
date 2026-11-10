import { router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { LogLevel, NotificationClickEvent, OneSignal } from 'react-native-onesignal';

import { config } from './config';

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

  // Tapping the Sunday push opens that week's talk.
  OneSignal.Notifications.addEventListener('click', (event: NotificationClickEvent) => {
    const data = event.notification.additionalData as { issue?: number | string; feed_id?: number | string; kind?: string; episode?: number | string; monday_minute?: number | string } | undefined;
    if (data?.monday_minute) router.push(`/monday/${data.monday_minute}`);
    else if (data?.episode) router.push(`/zero-hour/${data.episode}`);
    else if (data?.issue) router.push(`/talk/${data.issue}`);
    else if (data?.feed_id && data.kind === 'alert') router.push(`/alert/${data.feed_id}`);
    else if (data?.feed_id) router.push('/learn');
  });
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
  if (config.oneSignalAppId && (next.mondayMinute || next.weeklyTalk || next.alerts || next.zeroHour || next.offers)) {
    const granted = await OneSignal.Notifications.requestPermission(true);
    await markAsked();
    if (!granted) {
      permissionDenied = true;
      next = OFF;
    }
  }
  if (config.oneSignalAppId) {
    const on = (v: boolean) => (v ? 'on' : 'off');
    OneSignal.User.addTags({ monday_minute: on(next.mondayMinute), weekly_talk: on(next.weeklyTalk), alerts: on(next.alerts), zero_hour: on(next.zeroHour), offers: on(next.offers) });
  }
  await Storage.setItem(PREFS_KEY, JSON.stringify(next));
  return { prefs: next, permissionDenied };
}
