import { router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { LogLevel, NotificationClickEvent, OneSignal } from 'react-native-onesignal';

import { config } from './config';

/**
 * Three separate opt-ins, matching Apple's rule that promotional pushes need their own consent:
 *   weekly_talk  - the Sunday toolbox talk (a feature of the app)
 *   alerts       - regulatory alerts published from GoHighLevel (a feature of the app)
 *   offers       - news, free courses and offers (promotional, off by default)
 * The backend's cron sends each push to devices with the matching OneSignal tag set to "on".
 */
export type PushPrefs = { weeklyTalk: boolean; alerts: boolean; offers: boolean };
const OFF: PushPrefs = { weeklyTalk: false, alerts: false, offers: false };
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
    const data = event.notification.additionalData as { issue?: number | string; feed_id?: number | string; kind?: string } | undefined;
    if (data?.issue) router.push(`/talk/${data.issue}`);
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
  if (config.oneSignalAppId && (next.weeklyTalk || next.alerts || next.offers)) {
    const granted = await OneSignal.Notifications.requestPermission(true);
    await markAsked();
    if (!granted) {
      permissionDenied = true;
      next = OFF;
    }
  }
  if (config.oneSignalAppId) {
    const on = (v: boolean) => (v ? 'on' : 'off');
    OneSignal.User.addTags({ weekly_talk: on(next.weeklyTalk), alerts: on(next.alerts), offers: on(next.offers) });
  }
  await Storage.setItem(PREFS_KEY, JSON.stringify(next));
  return { prefs: next, permissionDenied };
}
