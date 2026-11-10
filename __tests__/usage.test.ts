import { api, isConfigured } from '@/lib/config';
import { getUsageOn, localDay, parsePlace, rememberPlace, reportOpen, setUsageOn } from '@/lib/usage';

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    setItem: (key: string, value: string) => Promise.resolve(void mockStore.set(key, value)),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
  },
}));
jest.mock('@/lib/config', () => ({ api: jest.fn(), isConfigured: jest.fn() }));

const send = api as jest.Mock;
const body = (call = 0) => JSON.parse(send.mock.calls[call][1].body);

beforeEach(() => {
  mockStore.clear();
  send.mockReset().mockResolvedValue({ ok: true });
  (isConfigured as jest.Mock).mockReturnValue(true);
  jest.useFakeTimers().setSystemTime(new Date(2026, 10, 10, 9, 0));
});
afterEach(() => jest.useRealTimers());

describe('localDay', () => {
  it('uses the phone\'s own date on both sides of midnight', () => {
    expect(localDay(new Date(2026, 10, 10, 23, 59, 59))).toBe('2026-11-10');
    expect(localDay(new Date(2026, 10, 11, 0, 0, 0))).toBe('2026-11-11');
    expect(localDay(new Date(2027, 0, 1, 0, 0, 1))).toBe('2027-01-01');
    expect(localDay(new Date(2026, 11, 31, 23, 59))).toBe('2026-12-31');
  });
});

describe('parsePlace', () => {
  it('splits "City, ST" and adds the country', () => {
    expect(parsePlace('Las Vegas, NV')).toEqual({ city: 'Las Vegas', region: 'NV', country: 'US' });
    expect(parsePlace(' Coeur d\'Alene,id ')).toEqual({ city: 'Coeur d\'Alene', region: 'ID', country: 'US' });
  });

  it('gives nothing for empty or odd input', () => {
    for (const odd of ['', null, undefined, 'NV', 'Las Vegas', ', NV', 'Las Vegas, Nevada', 'Paris, Ile, FR', `${'x'.repeat(81)}, NV`]) {
      expect(parsePlace(odd)).toBeNull();
    }
  });
});

describe('reportOpen', () => {
  it('sends the open once per local day', async () => {
    await reportOpen();
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0]).toBe('/v2/app/open');
    expect(send.mock.calls[0][1].method).toBe('POST');
    expect(send.mock.calls[0][2]).toBe(5000);
    expect(body().install_id).toMatch(/^zh-.{8,}/);
    expect(body().platform).toBe('ios');
    expect(body()).not.toHaveProperty('place');

    jest.setSystemTime(new Date(2026, 10, 10, 23, 59));
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(1);

    jest.setSystemTime(new Date(2026, 10, 11, 0, 1));
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('sends only once when launch and foreground call it together', async () => {
    await Promise.all([reportOpen(), reportOpen()]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('tries again after a failed send and never throws', async () => {
    send.mockRejectedValueOnce(new Error('no signal'));
    await expect(reportOpen()).resolves.toBeUndefined();
    await reportOpen();
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('sends nothing when the setting is off', async () => {
    expect(await getUsageOn()).toBe(true);
    await setUsageOn(false);
    expect(await getUsageOn()).toBe(false);
    await reportOpen();
    await rememberPlace('Las Vegas, NV');
    expect(send).not.toHaveBeenCalled();

    expect(mockStore.has('last_place')).toBe(false); // nothing is collected while it is off

    await setUsageOn(true);
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(1);
    expect(body(0)).not.toHaveProperty('place');
  });

  it('forgets the remembered city when the setting is turned off', async () => {
    await rememberPlace('Las Vegas, NV');
    expect(mockStore.has('last_place')).toBe(true);
    await setUsageOn(false);
    expect(mockStore.has('last_place')).toBe(false);
  });

  it('does not report yesterday\'s city: the open goes out plain and today\'s weather fills it in', async () => {
    await rememberPlace('Reno, NV');
    jest.setSystemTime(new Date(2026, 10, 11, 9, 0));
    await reportOpen();
    expect(body(1)).not.toHaveProperty('place');
    await rememberPlace('Sacramento, CA');
    expect(send).toHaveBeenCalledTimes(3);
    expect(body(2).place.city).toBe('Sacramento');
  });

  it('keeps counting when the saved marker is damaged', async () => {
    mockStore.set('usage_sent', '{"day":');
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(1);
    mockStore.set('usage_sent', 'null');
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('sends nothing when the server address is not set', async () => {
    (isConfigured as jest.Mock).mockReturnValue(false);
    await reportOpen();
    expect(send).not.toHaveBeenCalled();
  });

  it('includes the city when the weather already told the phone', async () => {
    await rememberPlace('Las Vegas, NV');
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(1);
    expect(body().place).toEqual({ city: 'Las Vegas', region: 'NV', country: 'US' });
  });

  it('sends once more that day when the city becomes known after the open went out', async () => {
    await reportOpen();
    await rememberPlace('Reno, NV');
    expect(send).toHaveBeenCalledTimes(2);
    expect(body(1).place).toEqual({ city: 'Reno', region: 'NV', country: 'US' });

    await rememberPlace('Sparks, NV');
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('still upgrades when the city arrives while the first send is in the air', async () => {
    let finish: (v: unknown) => void = () => {};
    send.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    const first = reportOpen();
    while (send.mock.calls.length === 0) await Promise.resolve();
    const second = rememberPlace('Reno, NV');
    for (let i = 0; i < 10; i++) await Promise.resolve();
    finish({ ok: true });
    await Promise.all([first, second]);
    expect(send).toHaveBeenCalledTimes(2);
    expect(body(0)).not.toHaveProperty('place');
    expect(body(1).place.city).toBe('Reno');
  });

  it('drops a remembered city from an earlier day', async () => {
    await rememberPlace('Las Vegas, NV');
    jest.setSystemTime(new Date(2026, 10, 20, 9, 0));
    await reportOpen();
    expect(send).toHaveBeenCalledTimes(2);
    expect(body(1)).not.toHaveProperty('place');
  });
});
