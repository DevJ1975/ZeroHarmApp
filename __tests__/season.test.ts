import { holidayOn, inHolidayWindow } from '@/lib/season';

jest.mock('expo-sqlite/kv-store', () => ({ getItemSync: () => null, setItem: () => Promise.resolve() }));

const day = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h);

describe('holiday window', () => {
  it('starts early the first year, on November 10, 2026', () => {
    expect(inHolidayWindow(day(2026, 11, 9, 23))).toBe(false);
    expect(inHolidayWindow(day(2026, 11, 10, 0))).toBe(true);
    expect(inHolidayWindow(day(2026, 11, 30))).toBe(true);
  });

  it('runs through the last minute of December 31 and is off on January 1', () => {
    expect(inHolidayWindow(new Date(2026, 11, 31, 23, 59, 59))).toBe(true);
    expect(inHolidayWindow(new Date(2027, 0, 1, 0, 0, 0))).toBe(false);
    expect(inHolidayWindow(day(2027, 6, 4))).toBe(false);
  });

  it('comes back each December, without the early start', () => {
    expect(inHolidayWindow(day(2027, 11, 20))).toBe(false);
    expect(inHolidayWindow(day(2027, 12, 1))).toBe(true);
    expect(inHolidayWindow(day(2028, 12, 25))).toBe(true);
  });

  it('lets the server force it on or off', () => {
    expect(holidayOn(day(2027, 7, 4), 'holiday')).toBe(true);
    expect(holidayOn(day(2026, 12, 25), 'default')).toBe(false);
    expect(holidayOn(day(2026, 12, 25), 'auto')).toBe(true);
    expect(holidayOn(day(2027, 1, 1), 'auto')).toBe(false);
  });
});
