/**
 * Dates in the console are shown and entered in Pacific time, the same clock the app's schedule runs on.
 * Times are sent without an offset, and the backend reads them as America/Los_Angeles.
 */
const ZONE = 'America/Los_Angeles';

function parts(iso: string): Record<string, string> | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  return Object.fromEntries(fmt.formatToParts(d).map((p) => [p.type, p.value]));
}

/** ISO from the API -> value for <input type="datetime-local">, in Pacific time. */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const p = parts(iso);
  if (!p) return '';
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** Value from <input type="datetime-local"> -> naive ISO the backend reads as Pacific. */
export function fromLocalInput(value: string): string {
  return value ? `${value}:00` : '';
}

/** "Sun, Nov 16, 11:59 AM PT" */
export function formatPacific(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString('en-US', { timeZone: ZONE, weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} PT`;
}

export function isFuture(iso: string | null | undefined): boolean {
  return !!iso && new Date(iso).getTime() > Date.now();
}
