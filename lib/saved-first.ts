/**
 * Built for plants and docks where Wi-Fi and cellular are weak: show what's saved on the phone right away, then
 * refresh quietly in the background. A screen never waits on a slow network when it already has something to show.
 */
const lastFresh = new Map<string, number>();
const inFlight = new Map<string, Promise<unknown>>();

/** Don't re-download the same thing more often than this. Saves data and battery on a weak signal. */
export const FRESH_FOR_MS = 60_000;

export type SavedFirst<T> = {
  /** Called when the background refresh brings back newer data. */
  onFresh?: (value: T) => void;
  /** Called when the refresh fails, so the screen can say it's showing the saved copy. */
  onOffline?: () => void;
};

export async function savedFirst<T>(
  key: string,
  readSaved: () => Promise<T | null>,
  fetchFresh: () => Promise<T>,
  { onFresh, onOffline }: SavedFirst<T> = {},
): Promise<{ value: T | null; fromSaved: boolean }> {
  const refresh = () => {
    let run = inFlight.get(key) as Promise<T> | undefined;
    if (!run) {
      run = fetchFresh().finally(() => inFlight.delete(key));
      inFlight.set(key, run);
    }
    return run.then((value) => {
      lastFresh.set(key, Date.now());
      return value;
    });
  };

  const saved = await readSaved().catch(() => null);
  if (saved !== null) {
    if (Date.now() - (lastFresh.get(key) ?? 0) > FRESH_FOR_MS) {
      refresh().then(onFresh, () => onOffline?.());
    }
    return { value: saved, fromSaved: true };
  }
  try {
    return { value: await refresh(), fromSaved: false };
  } catch {
    onOffline?.();
    return { value: null, fromSaved: false };
  }
}

/** Forget freshness, e.g. after the person posts something and the list should reload. */
export function markStale(key: string) {
  lastFresh.delete(key);
}

/** For tests. */
export function resetSavedFirst() {
  lastFresh.clear();
  inFlight.clear();
}
