const mockStore = new Map<string, string>();
const mockFail = { read: false };
// A storage that answers a little later, as the phone's does, so two first callers really do overlap.
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) =>
      new Promise((resolve, reject) => setTimeout(() => (mockFail.read ? reject(new Error('storage is closed')) : resolve(mockStore.get(key) ?? null)), 1)),
    setItem: (key: string, value: string) => new Promise((resolve) => setTimeout(() => resolve(void mockStore.set(key, value)), 1)),
  },
}));

type InstallModule = typeof import('@/lib/install');
let install: InstallModule;

beforeEach(() => {
  mockStore.clear();
  mockFail.read = false;
  jest.resetModules();
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- a fresh module each test: it remembers the id
  install = require('@/lib/install');
});

describe('installId', () => {
  it('two first calls at the same moment get the same id, and it is the one kept on the phone', async () => {
    const [a, b] = await Promise.all([install.installId(), install.installId()]);
    expect(a).toBe(b);
    expect(mockStore.get('install_id')).toBe(a);
    expect(await install.installId()).toBe(a);
    expect(a).toMatch(/^zh-[0-9a-z]+-[0-9a-f]{24}$/);
  });

  it('reads an id already on the phone', async () => {
    mockStore.set('install_id', 'zh-old-123');
    expect(await install.installId()).toBe('zh-old-123');
  });

  it('a storage hiccup is not remembered: the next call tries again', async () => {
    mockFail.read = true;
    await expect(install.installId()).rejects.toThrow('storage is closed');
    mockFail.read = false;
    mockStore.set('install_id', 'zh-old-123');
    expect(await install.installId()).toBe('zh-old-123');
  });
});
