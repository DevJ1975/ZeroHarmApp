import { router } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { LogLevel, NotificationClickEvent, OneSignal } from 'react-native-onesignal';

import { config } from './config';

/**
 * Two separate opt-ins, matching Apple's rule that promotional pushes need their own consent:
 *   weekly_talk  - the Sunday toolbox talk (a feature of the app)
 *   offers       - news and offers (promotional, off by default)
 * GoHighLevel's Sunday workflow calls the send-talk-push edge function, which targets weekly_talk = on.
 */
export type PushPrefs = { weeklyTalk: boolean; offers: boolean };
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
    const data = event.notification.additionalData as { issue?: number | string } | undefined;
    if (data?.issue) router.push(`/talk/${data.issue}`);
  });
}

export async function getPrefs(): Promise<PushPrefs> {
  const raw = await Storage.getItem(PREFS_KEY);
  return raw ? (JSON.parse(raw) as PushPrefs) : { weeklyTalk: false, offers: false };
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
  if (config.oneSignalAppId && (next.weeklyTalk || next.offers)) {
    const granted = await OneSignal.Notifications.requestPermission(true);
    await markAsked();
    if (!granted) {
      permissionDenied = true;
      next = { weeklyTalk: false, offers: false };
    }
  }
  if (config.oneSignalAppId) {
    OneSignal.User.addTags({ weekly_talk: next.weeklyTalk ? 'on' : 'off', offers: next.offers ? 'on' : 'off' });
  }
  await Storage.setItem(PREFS_KEY, JSON.stringify(next));
  return { prefs: next, permissionDenied };
}
