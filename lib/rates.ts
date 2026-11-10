/**
 * OSHA injury-rate math (TRIR / DART).
 *
 * OSHA normalises incident rates to a 200,000-hour base: 100 full-time
 * workers x 40 hours/week x 50 weeks/year. So
 *   rate = cases x 200,000 / total hours worked
 * e.g. 3 recordables over 410,000 hours -> 1.46.
 */

/** Number of hours in OSHA's rate base (100 full-time workers for a year). */
export const OSHA_HOURS_BASE = 200000;

/** Parse a user-typed count such as "410,000". Commas are stripped; the rest goes through Number(). */
export const parseCount = (s: string) => Number(s.replace(/,/g, ''));

/**
 * Format an OSHA incident rate to 2 decimals, or '–' when it cannot be computed
 * (hours blank, zero, negative or non-numeric; cases blank).
 */
export function injuryRate(cases: string, hours: string): string {
  const h = parseCount(hours);
  const ready = h > 0;
  return ready && cases !== '' ? ((parseCount(cases) * OSHA_HOURS_BASE) / h).toFixed(2) : '–';
}
