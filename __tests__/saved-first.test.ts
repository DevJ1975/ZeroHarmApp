import { FRESH_FOR_MS, resetSavedFirst, savedFirst } from '@/lib/saved-first';

const tick = () => new Promise<void>((r) => setImmediate(() => r()));

describe('saved copy first (weak signal)', () => {
  beforeEach(() => {
    resetSavedFirst();
    jest.restoreAllMocks();
  });

  it('returns the saved copy at once and refreshes in the background', async () => {
    let release!: (v: string[]) => void;
    const slowNetwork = new Promise<string[]>((r) => (release = r));
    const onFresh = jest.fn();
    const result = await savedFirst('talks', async () => ['saved'], () => slowNetwork, { onFresh });
    expect(result).toEqual({ value: ['saved'], fromSaved: true }); // did not wait for the network
    expect(onFresh).not.toHaveBeenCalled();
    release(['fresh']);
    await tick();
    expect(onFresh).toHaveBeenCalledWith(['fresh']);
  });

  it('waits for the network only when nothing is saved', async () => {
    const result = await savedFirst('talks', async () => null, async () => ['fresh']);
    expect(result).toEqual({ value: ['fresh'], fromSaved: false });
  });

  it('with no signal, keeps the saved copy and says so', async () => {
    const onOffline = jest.fn();
    const result = await savedFirst('talks', async () => ['saved'], () => Promise.reject(new Error('timeout')), { onOffline });
    await tick();
    expect(result.value).toEqual(['saved']);
    expect(onOffline).toHaveBeenCalled();
    const nothing = await savedFirst('empty', async () => null, () => Promise.reject(new Error('timeout')), { onOffline });
    expect(nothing).toEqual({ value: null, fromSaved: false });
  });

  it('does not download again within a minute, and shares one request between callers', async () => {
    const fetch = jest.fn(async () => ['fresh']);
    await savedFirst('talks', async () => ['saved'], fetch);
    await tick();
    await savedFirst('talks', async () => ['saved'], fetch);
    await tick();
    expect(fetch).toHaveBeenCalledTimes(1);
    jest.spyOn(Date, 'now').mockReturnValue(Date.now() + FRESH_FOR_MS + 1);
    await Promise.all([savedFirst('talks', async () => ['saved'], fetch), savedFirst('talks', async () => ['saved'], fetch)]);
    await tick();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
