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
 * (hours blank, zero, negative, non-numeric or overflowing; cases blank or
 * spaces only, negative, non-numeric or overflowing; or a rate too big to show).
 */
export function injuryRate(cases: string, hours: string): string {
  const h = parseCount(hours);
  const c = parseCount(cases);
  // Hours must be a real number above zero; cases a real number of zero or more.
  // Number.isFinite rejects NaN ("abc", ".") and Infinity ("1e400").
  // Spaces-only cases count as blank (Number(' ') would quietly give 0).
  const hoursOk = Number.isFinite(h) && h > 0;
  const casesOk = cases.trim() !== '' && Number.isFinite(c) && c >= 0;
  if (!hoursOk || !casesOk) return '–';
  // The division itself can still overflow (huge cases, or tiny hours).
  const rate = (c * OSHA_HOURS_BASE) / h;
  return Number.isFinite(rate) ? rate.toFixed(2) : '–';
}
