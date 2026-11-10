/**
 * The holiday look. It turns itself on and off by the phone's own date, so it needs no app update and works with no
 * signal. The server can also force it on or off (APP_THEME on the backend) without a new build.
 */
import Storage from 'expo-sqlite/kv-store';
import { useSyncExternalStore } from 'react';

import { api, isConfigured } from './config';

export type ThemeMode = 'auto' | 'default' | 'holiday';

const KEY = 'app-theme-mode';
const MODES: ThemeMode[] = ['auto', 'default', 'holiday'];

/** Every year: December 1 through December 31. The first season starts early, on November 10, 2026. */
export function inHolidayWindow(now: Date): boolean {
  const month = now.getMonth(); // 0 = January
  if (month === 11) return true;
  return now.getFullYear() === 2026 && month === 10 && now.getDate() >= 10;
}

/** The server's word wins; "auto" follows the calendar. On January 1 the app is back to its normal look. */
export function holidayOn(now: Date, mode: ThemeMode): boolean {
  if (mode === 'holiday') return true;
  if (mode === 'default') return false;
  return inHolidayWindow(now);
}

const asMode = (value: unknown): ThemeMode => (MODES.includes(value as ThemeMode) ? (value as ThemeMode) : 'auto');

function savedMode(): ThemeMode {
  try {
    return asMode(Storage.getItemSync(KEY));
  } catch {
    return 'auto';
  }
}

let mode: ThemeMode = savedMode();
const listeners = new Set<() => void>();
const tell = () => listeners.forEach((l) => l());

export const isHoliday = () => holidayOn(new Date(), mode);

/** Ask the server whether the look is forced on or off. No signal or no answer: keep what the phone already has. */
export async function refreshSeason(): Promise<void> {
  if (isConfigured()) {
    try {
      const next = asMode((await api<{ theme: string }>('/v2/app/config', undefined, 5000)).theme);
      if (next !== mode) {
        mode = next;
        Storage.setItem(KEY, next).catch(() => {});
      }
    } catch {
      // Weak signal is normal on a plant floor. The calendar still decides.
    }
  }
  tell(); // also picks up a date change while the app sat in the background
}

/** True while the holiday look is showing. Screens re-draw when it changes. */
export function useHoliday(): boolean {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    isHoliday,
    isHoliday,
  );
}

/** For tests. */
export function setThemeModeForTest(next: ThemeMode) {
  mode = next;
  tell();
}
