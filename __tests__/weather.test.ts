/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
/** getWeather(): local heat/cold conditions, without ever prompting for location unasked. */
import type { Weather } from '@/lib/weather';

jest.mock('expo-location', () => ({
  getForegroundPermissionsAsync: jest.fn(),
  requestForegroundPermissionsAsync: jest.fn(),
  getLastKnownPositionAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
  Accuracy: { Low: 2 },
}));

// The merged lib/weather.ts hands the city to the anonymous usage count. That has its own tests; here we only
// check the hand-off, and keeping lib/usage out of the module graph keeps react-native (and its fetch) out too.
jest.mock('@/lib/usage', () => ({ rememberPlace: jest.fn() }));

const usage = jest.requireMock('@/lib/usage') as { rememberPlace: jest.Mock };

const Location = jest.requireMock('expo-location') as {
  getForegroundPermissionsAsync: jest.Mock;
  requestForegroundPermissionsAsync: jest.Mock;
  getLastKnownPositionAsync: jest.Mock;
  getCurrentPositionAsync: jest.Mock;
};

const fetchMock = jest.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

const WX: Weather = {
  place: 'Newark, NJ',
  temp_f: 96,
  summary: 'Sunny',
  heat_index_f: 104,
  wind: 'SW 5 mph',
  hazard: 'heat',
  alerts: [],
};

const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
const at = (latitude: number, longitude: number) => ({ coords: { latitude, longitude } });

function load(apiUrl = 'https://api.example.test') {
  process.env.EXPO_PUBLIC_API_URL = apiUrl;
  let mod!: typeof import('@/lib/weather');
  jest.isolateModules(() => {
    mod = require('@/lib/weather'); // fresh module = empty 10-minute cache
  });
  // A fresh module graph can put its own fetch back on the global, so re-hang ours.
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return mod;
}

const requestedUrl = () => fetchMock.mock.calls[0][0] as string;

beforeEach(() => {
  jest.useFakeTimers({ now: new Date('2026-07-15T12:00:00Z') });
  fetchMock.mockReset();
  usage.rememberPlace.mockReset();
  Location.getForegroundPermissionsAsync.mockReset().mockResolvedValue({ status: 'granted' });
  Location.requestForegroundPermissionsAsync.mockReset().mockResolvedValue({ status: 'granted' });
  Location.getLastKnownPositionAsync.mockReset().mockResolvedValue(at(40.73567, -74.17241));
  Location.getCurrentPositionAsync.mockReset().mockResolvedValue(at(1, 1));
});

afterEach(() => jest.useRealTimers());

describe('permission', () => {
  test('not yet answered: returns null and never pops the permission prompt', async () => {
    const { getWeather } = load();
    Location.getForegroundPermissionsAsync.mockResolvedValue({ status: 'undetermined' });

    expect(await getWeather()).toBeNull();
    expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('denied: null, no location read, no request', async () => {
    const { getWeather } = load();
    Location.getForegroundPermissionsAsync.mockResolvedValue({ status: 'denied' });

    expect(await getWeather()).toBeNull();
    expect(Location.getLastKnownPositionAsync).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('ask=true prompts, and a yes gets the weather', async () => {
    const { getWeather } = load();
    Location.getForegroundPermissionsAsync.mockResolvedValue({ status: 'undetermined' });
    fetchMock.mockReturnValueOnce(ok(WX));

    expect(await getWeather(true)).toEqual(WX);
    expect(Location.requestForegroundPermissionsAsync).toHaveBeenCalledTimes(1);
  });

  test('ask=true and the person says no: null', async () => {
    const { getWeather } = load();
    Location.requestForegroundPermissionsAsync.mockResolvedValue({ status: 'denied' });
    expect(await getWeather(true)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('locationStatus reports the current answer without prompting', async () => {
    const { locationStatus } = load();
    Location.getForegroundPermissionsAsync.mockResolvedValue({ status: 'denied' });
    expect(await locationStatus()).toBe('denied');
    expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  });

  test('API not configured: null without touching location', async () => {
    const { getWeather } = load('');
    expect(await getWeather(true)).toBeNull();
    expect(Location.requestForegroundPermissionsAsync).not.toHaveBeenCalled();
  });
});

describe('position', () => {
  test('uses a recent last-known position (no fresh GPS fix) and rounds to 2 decimals', async () => {
    const { getWeather } = load();
    fetchMock.mockReturnValueOnce(ok(WX));

    expect(await getWeather()).toEqual(WX);
    expect(Location.getLastKnownPositionAsync).toHaveBeenCalledWith({ maxAge: 30 * 60 * 1000 });
    expect(Location.getCurrentPositionAsync).not.toHaveBeenCalled();
    expect(requestedUrl()).toBe('https://api.example.test/api/weather/?lat=40.74&lon=-74.17');
  });

  test('no last-known position: takes a fresh low-accuracy fix', async () => {
    const { getWeather } = load();
    Location.getLastKnownPositionAsync.mockResolvedValue(null);
    Location.getCurrentPositionAsync.mockResolvedValue(at(29.7604, -95.3698));
    fetchMock.mockReturnValueOnce(ok(WX));

    expect(await getWeather()).toEqual(WX);
    expect(Location.getCurrentPositionAsync).toHaveBeenCalledWith({ accuracy: 2 });
    expect(requestedUrl()).toBe('https://api.example.test/api/weather/?lat=29.76&lon=-95.37');
  });

  test('the full coordinates never leave the phone', async () => {
    const { getWeather } = load();
    Location.getLastKnownPositionAsync.mockResolvedValue(at(40.712776, -74.005974));
    fetchMock.mockReturnValueOnce(ok(WX));

    await getWeather();
    expect(requestedUrl()).not.toMatch(/40\.712|74\.005/);
    expect(requestedUrl()).toMatch(/lat=40\.71&lon=-74\.01$/);
  });

  test('a failed fresh fix (inside a building, airplane mode) returns null instead of throwing', async () => {
    const { getWeather } = load();
    Location.getLastKnownPositionAsync.mockResolvedValue(null);
    Location.getCurrentPositionAsync.mockRejectedValue(new Error('Current location is unavailable'));

    await expect(getWeather()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('a throwing last-known lookup also returns null instead of crashing', async () => {
    const { getWeather } = load();
    Location.getLastKnownPositionAsync.mockRejectedValue(new Error('Location provider is unavailable'));
    await expect(getWeather()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('server and cache', () => {
  test('a server failure returns null', async () => {
    const { getWeather } = load();
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: false, status: 502, json: async () => ({}) }));
    await expect(getWeather()).resolves.toBeNull();
  });

  test('a second call within 10 minutes reuses the result without location or network', async () => {
    const { getWeather } = load();
    fetchMock.mockReturnValueOnce(ok(WX));
    await getWeather();

    jest.advanceTimersByTime(9 * 60 * 1000 + 59 * 1000);
    Location.getForegroundPermissionsAsync.mockClear();
    expect(await getWeather()).toEqual(WX);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(Location.getForegroundPermissionsAsync).not.toHaveBeenCalled();
  });

  test('after 10 minutes it fetches fresh conditions', async () => {
    const { getWeather } = load();
    fetchMock.mockReturnValueOnce(ok(WX));
    await getWeather();

    jest.advanceTimersByTime(10 * 60 * 1000);
    const cooler = { ...WX, temp_f: 88, hazard: null };
    fetchMock.mockReturnValueOnce(ok(cooler));
    expect(await getWeather()).toEqual(cooler);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test('no fix is not cached either: the next call tries the location again', async () => {
    const { getWeather } = load();
    Location.getLastKnownPositionAsync.mockResolvedValueOnce(null);
    Location.getCurrentPositionAsync.mockRejectedValueOnce(new Error('Current location is unavailable'));
    expect(await getWeather()).toBeNull();

    fetchMock.mockReturnValueOnce(ok(WX));
    expect(await getWeather()).toEqual(WX);
  });

  test('the city from the answer goes to the anonymous usage count; a failure sends nothing', async () => {
    const { getWeather } = load();
    fetchMock.mockReturnValueOnce(ok(WX));
    await getWeather();
    expect(usage.rememberPlace).toHaveBeenCalledWith('Newark, NJ');

    const { getWeather: again } = load();
    usage.rememberPlace.mockClear();
    fetchMock.mockImplementationOnce(() => Promise.reject(new TypeError('Network request failed')));
    expect(await again()).toBeNull();
    expect(usage.rememberPlace).not.toHaveBeenCalled();
  });

  test('a failure is not cached: the next call tries again', async () => {
    const { getWeather } = load();
    fetchMock.mockImplementationOnce(() => Promise.reject(new TypeError('Network request failed')));
    expect(await getWeather()).toBeNull();

    fetchMock.mockReturnValueOnce(ok(WX));
    expect(await getWeather()).toEqual(WX);
  });
});
