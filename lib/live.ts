import Storage from 'expo-sqlite/kv-store';
import { useEffect, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';

import { api, isConfigured } from './config';

/**
 * Live content: the backend publishes a short "content version" that changes whenever a talk,
 * alert, episode or OTIS entry is released, edited or pulled. The app checks it when it comes
 * back to the foreground (at most once a minute) and whenever a push says "refresh", and tells
 * the open screens to reload their lists when it changed. No sockets, no new native code.
 */
type Listener = () => unknown; // may return a promise: the version is kept only after it settles

const KEY = 'content_version';
const THROTTLE_MS = 60_000;

const listeners = new Set<Listener>();
let fallbacks = 0; // reloads that had to use the copy on the phone (no signal)
let lastCheck = 0;
let inFlight: Promise<boolean> | null = null;
let again = false; // another check was asked for while one was running
let started = false;

/** Calls `listener` every time the content changes. Returns a function that stops listening. */
export function subscribeContent(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Called by a list loader when it couldn't reach the API and showed the copy on the phone instead.
 * A content change seen during that reload is then not marked as seen, so the next check tries again.
 */
export function noteStaleContent() {
  fallbacks += 1;
}

/** Asks the backend for the content version now. Resolves true when it changed (and listeners were told). */
export function refreshContent(): Promise<boolean> {
  if (!isConfigured()) return Promise.resolve(false);
  if (inFlight) {
    // A push can land while an older check is still waiting; check once more after it so the change isn't missed.
    again = true;
    return inFlight;
  }
  inFlight = run().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

async function run(): Promise<boolean> {
  let changed = await check();
  while (again) {
    again = false;
    changed = (await check()) || changed;
  }
  return changed;
}

async function check(): Promise<boolean> {
  lastCheck = Date.now();
  let version: string;
  try {
    ({ version } = await api<{ version: string }>('/content-version/', undefined, 8000));
    if (!version || version === (await Storage.getItem(KEY))) return false;
  } catch {
    return false; // no signal or storage trouble: try again next time
  }
  // Remember the version only once every open screen really reloaded it. If a reload fell back to the
  // copy on the phone (signal dropped between the two requests), leave it unseen so the next check retries.
  const before = fallbacks;
  await notify();
  if (fallbacks === before) {
    try {
      await Storage.setItem(KEY, version);
    } catch {
      // storage trouble: the next check notifies again, which only costs a reload
    }
  }
  return true;
}

async function notify() {
  const runs = [...listeners].map(async (listener) => {
    try {
      await listener();
    } catch {
      noteStaleContent(); // one broken screen should not stop the others, but it didn't get the new content
    }
  });
  await Promise.all(runs);
}

function onAppState(state: AppStateStatus) {
  if (state !== 'active') return;
  if (Date.now() - lastCheck < THROTTLE_MS) return;
  refreshContent();
}

/** Starts watching for the app coming back to the foreground. Safe to call more than once. */
export function startLive() {
  if (started) return;
  started = true;
  AppState.addEventListener('change', onAppState);
  refreshContent(); // learn the current version at launch
}

/** Runs `reload` whenever content changes while the screen is mounted. Return its promise so a failed reload is retried. */
export function useContentRefresh(reload: () => unknown) {
  const latest = useRef(reload);
  useEffect(() => {
    latest.current = reload;
  });
  useEffect(() => subscribeContent(() => latest.current()), []);
}
