import { fireEvent, render, screen } from '@testing-library/react-native';
import { createElement } from 'react';

import ToolsScreen from '@/app/(tabs)/tools';
import { injuryRate, OSHA_HOURS_BASE, parseCount } from '@/lib/rates';

// Native boundary: the screen wraps itself in a SafeAreaView.
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View };
});

// Decision for non-numeric input: the calculator must never put "NaN" (or
// "Infinity") in front of a user. Anything that is not a usable count shows
// the placeholder '–' instead.

describe('parseCount', () => {
  test('plain integers', () => {
    expect(parseCount('3')).toBe(3);
    expect(parseCount('410000')).toBe(410000);
  });

  test('strips thousands separators', () => {
    expect(parseCount('410,000')).toBe(410000);
    expect(parseCount('1,234,567')).toBe(1234567);
  });

  test('blank parses to 0 (Number semantics)', () => {
    expect(parseCount('')).toBe(0);
  });

  test('non-numeric parses to NaN', () => {
    expect(parseCount('abc')).toBeNaN();
    expect(parseCount('12a')).toBeNaN();
  });
});

describe('injuryRate', () => {
  test('uses the OSHA 200,000-hour base', () => {
    expect(OSHA_HOURS_BASE).toBe(200000);
    // 200,000 hours worked and 1 case is exactly a rate of 1.
    expect(injuryRate('1', '200000')).toBe('1.00');
  });

  test('OSHA worked example: 3 recordables over 410,000 hours -> 1.46', () => {
    expect(injuryRate('3', '410000')).toBe('1.46');
  });

  test('accepts comma-formatted hours and cases', () => {
    expect(injuryRate('3', '410,000')).toBe('1.46');
    expect(injuryRate('1,000', '2,000,000')).toBe('100.00');
  });

  test('zero cases with valid hours is a real 0.00 rate', () => {
    expect(injuryRate('0', '410,000')).toBe('0.00');
  });

  test('rounds to 2 decimals', () => {
    // 2 * 200000 / 300000 = 1.3333...
    expect(injuryRate('2', '300000')).toBe('1.33');
    // 5 * 200000 / 600000 = 1.6666...
    expect(injuryRate('5', '600000')).toBe('1.67');
    // 7 * 200000 / 1,000,000 = 1.4 -> padded
    expect(injuryRate('7', '1,000,000')).toBe('1.40');
    // 1 * 200000 / 1,600,000 = 0.125 exactly -> rounds half up, not down
    expect(injuryRate('1', '1,600,000')).toBe('0.13');
  });

  test('large sites stay exact (no overflow or exponent formatting)', () => {
    // 1,250 cases over 50,000,000 hours = 5.00
    expect(injuryRate('1,250', '50,000,000')).toBe('5.00');
  });

  test.each([
    ['blank', ''],
    ['zero', '0'],
    ['negative', '-410000'],
    ['non-numeric', 'abc'],
    ['garbled', '41o,000'],
  ])('hours %s -> placeholder', (_label, hours) => {
    expect(injuryRate('3', hours)).toBe('–');
  });

  test('blank cases -> placeholder even with valid hours', () => {
    expect(injuryRate('', '410,000')).toBe('–');
  });

  // Fixed: cases must parse to a finite number, so junk or overflow shows '–'
  // instead of "NaN"/"Infinity".
  test.each([
    ['abc', 'abc'],
    ['stray "."', '.'],
    ['lone "-"', '-'],
    ['trailing letter', '3a'],
    ['overflow', '1e400'],
  ])('cases %s -> placeholder', (_label, cases) => {
    expect(injuryRate(cases, '410,000')).toBe('–');
  });

  // Fixed: hours must be finite, so overflowing hours no longer show a fake 0.00 rate.
  test('overflowing hours -> placeholder', () => {
    expect(injuryRate('3', '1e400')).toBe('–');
  });

  // Fixed: negative case counts are rejected, so no negative rate is shown.
  test('negative cases -> placeholder', () => {
    expect(injuryRate('-3', '410,000')).toBe('–');
  });

  // Fixed: spaces-only cases count as blank instead of a fake 0.00 rate.
  test.each([
    ['space', ' '],
    ['tab', '\t'],
  ])('cases %s only -> placeholder', (_label, cases) => {
    expect(injuryRate(cases, '410,000')).toBe('–');
  });

  // Fixed: finite inputs whose rate overflows show '–', not "Infinity".
  test.each([
    ['huge cases', '1e308', '1'],
    ['tiny hours', '1', '1e-320'],
  ])('rate overflow (%s) -> placeholder', (_label, cases, hours) => {
    expect(injuryRate(cases, hours)).toBe('–');
  });

  test('surrounding spaces on a real count still compute', () => {
    expect(injuryRate(' 3 ', '410,000')).toBe('1.46');
  });
});

describe('Tools screen injury-rate card', () => {
  const renderScreen = () => render(createElement(ToolsScreen));
  // The card's three inputs, in on-screen order: hours, recordables, DART.
  const inputs = () => screen.container.queryAll((n) => n.type === 'TextInput');
  const enter = async (field: 'hours' | 'recordables' | 'dart', text: string) => {
    const idx = { hours: 0, recordables: 1, dart: 2 }[field];
    await fireEvent.changeText(inputs()[idx], text);
  };
  /** The big number shown above a result caption ("TRIR" / "DART rate"). */
  const value = (caption: string) => {
    const result = screen.getByText(caption).parent!;
    return result.children[0] as Parameters<typeof expect>[0];
  };

  test('renders exactly the three calculator inputs', async () => {
    await renderScreen();
    expect(inputs()).toHaveLength(3);
    expect(inputs()[0].props.placeholder).toBe('e.g. 410,000');
  });

  test('shows placeholders until hours are entered, then TRIR and DART', async () => {
    await renderScreen();
    expect(value('TRIR')).toHaveTextContent('–');
    expect(value('DART rate')).toHaveTextContent('–');

    await enter('recordables', '3');
    await enter('dart', '1');
    // Still no hours: nothing to divide by.
    expect(value('TRIR')).toHaveTextContent('–');
    expect(value('DART rate')).toHaveTextContent('–');

    await enter('hours', '410,000');
    // 3 * 200000 / 410000 = 1.46 ; 1 * 200000 / 410000 = 0.49
    expect(value('TRIR')).toHaveTextContent('1.46');
    expect(value('DART rate')).toHaveTextContent('0.49');
  });

  test('TRIR card reads recordables and DART card reads DART cases', async () => {
    await renderScreen();
    await enter('hours', '200,000');
    await enter('recordables', '4');
    await enter('dart', '2');
    expect(value('TRIR')).toHaveTextContent('4.00');
    expect(value('DART rate')).toHaveTextContent('2.00');
  });

  test('clearing hours returns both cards to the placeholder', async () => {
    await renderScreen();
    await enter('hours', '410,000');
    await enter('recordables', '3');
    await enter('dart', '1');
    expect(value('TRIR')).toHaveTextContent('1.46');
    await enter('hours', '');
    expect(value('TRIR')).toHaveTextContent('–');
    expect(value('DART rate')).toHaveTextContent('–');
  });
});
