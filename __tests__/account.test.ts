import {
  checkSignIn,
  cleanName,
  CONSENT_LINE,
  firstRun,
  flushAccount,
  getAccount,
  markHowToDone,
  removeMyInfo,
  signedIn,
  signIn,
  skip,
  whatToShow,
} from '@/lib/account';
import { api, isConfigured } from '@/lib/config';
import { getProfile, saveProfile, tidyEmail, validEmail } from '@/lib/profile';

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    getItemSync: (key: string) => mockStore.get(key) ?? null,
    setItem: (key: string, value: string) => Promise.resolve(void mockStore.set(key, value)),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
  },
}));
jest.mock('@/lib/config', () => {
  class ApiError extends Error {
    status: number;
    constructor(code: number) {
      super(`API ${code}`);
      this.status = code;
    }
  }
  return { api: jest.fn(), isConfigured: jest.fn(), ApiError };
});

const { ApiError } = jest.requireMock('@/lib/config') as { ApiError: new (status: number) => Error };
const send = api as jest.Mock;
const path = (call: number) => send.mock.calls[call][0] as string;
const body = (call: number) => JSON.parse(send.mock.calls[call][1].body);
const maria = { name: 'Maria Lopez', email: 'maria@example.com' };

beforeEach(async () => {
  await flushAccount(); // let anything a previous test left in the air finish
  mockStore.clear();
  send.mockReset().mockResolvedValue({ ok: true });
  (isConfigured as jest.Mock).mockReturnValue(true);
});

describe('checkSignIn', () => {
  it('cleans up the name and email', () => {
    expect(checkSignIn({ name: '  Maria   Lopez ', email: ' Maria@Example.COM ' })).toEqual({ name: 'Maria Lopez', email: 'maria@example.com', errors: {}, ok: true });
    expect(cleanName('x'.repeat(200))).toHaveLength(120);
  });

  it('asks for a name', () => {
    const checked = checkSignIn({ name: '   ', email: 'maria@example.com' });
    expect(checked.ok).toBe(false);
    expect(checked.errors).toEqual({ name: 'Enter your name.' });
  });

  it('asks for an email, and says so when it does not look like one', () => {
    expect(checkSignIn({ name: 'Maria', email: '' }).errors).toEqual({ email: 'Enter your email.' });
    for (const bad of ['maria', 'maria@', 'maria@example', '@example.com', 'maria lopez@example.com']) {
      const checked = checkSignIn({ name: 'Maria', email: bad });
      expect(checked.ok).toBe(false);
      expect(checked.errors.email).toMatch(/^Check the email address/);
    }
  });

  it('tidies a stray full stop, comma or space off the end', () => {
    for (const typed of ['maria@example.com.', 'maria@example.com,', ' Maria@Example.com. ', 'maria@example.com;']) {
      expect(checkSignIn({ name: 'Maria', email: typed })).toMatchObject({ email: 'maria@example.com', ok: true });
    }
  });

  it('turns down what the server would turn down', () => {
    for (const bad of ['maria@gmail..com', 'bob@site.c', 'a@b@c.com', 'maría@example.com', 'maria@exämple.com', '.maria@example.com', 'maria.@example.com', 'maria@.example.com', 'maria@example-.com', 'maria@-example.com', 'maria@example.123', 'ma ria@example.com', 'maria@example.com,bob@example.com']) {
      expect(checkSignIn({ name: 'Maria', email: bad }).ok).toBe(false);
    }
  });

  it('reports both fields at once', () => {
    expect(Object.keys(checkSignIn({ name: '', email: 'nope' }).errors)).toEqual(['name', 'email']);
  });
});

describe('what to show first', () => {
  it('goes welcome, then how-to, then the app', () => {
    expect(whatToShow({ opening: false, welcomeDone: false, howToDone: false })).toBe('welcome');
    expect(whatToShow({ opening: false, welcomeDone: true, howToDone: false })).toBe('howto');
    expect(whatToShow({ opening: false, welcomeDone: true, howToDone: true })).toBe('app');
  });

  it('lets the holiday opening screen play alone, whatever comes next', () => {
    for (const welcomeDone of [false, true]) {
      for (const howToDone of [false, true]) expect(whatToShow({ opening: true, welcomeDone, howToDone })).toBe('opening');
    }
  });

  it('never shows the how-to ahead of the welcome screen', () => {
    expect(whatToShow({ opening: false, welcomeDone: false, howToDone: true })).toBe('welcome');
  });

  it('reads the first-run state from the phone', async () => {
    expect(firstRun()).toEqual({ welcomeDone: false, howToDone: false });
    await skip();
    expect(firstRun()).toEqual({ welcomeDone: true, howToDone: false });
    await markHowToDone();
    expect(firstRun()).toEqual({ welcomeDone: true, howToDone: true });
  });
});

describe('signIn', () => {
  it('saves the profile, marks welcome done and sends the sign-up', async () => {
    await signIn(maria);
    await flushAccount();
    expect(await getProfile()).toEqual({ name: 'Maria Lopez', email: 'maria@example.com', company: '' });
    expect(await signedIn()).toBe(true);
    expect(firstRun().welcomeDone).toBe(true);
    expect(send).toHaveBeenCalledTimes(1);
    expect(path(0)).toBe('/signups/');
    expect(send.mock.calls[0][1].method).toBe('POST');
    expect(body(0)).toEqual({
      name: 'Maria Lopez',
      email: 'maria@example.com',
      install_id: expect.stringMatching(/^zh-.{8,}/),
      source: 'welcome',
      consent: "You'll get Zero Harm Weekly by email each week. Unsubscribe anytime.",
    });
    expect(body(0)).not.toHaveProperty('wants_offers'); // the welcome screen must not switch off an earlier opt-in
    expect(body(0).consent).toBe(CONSENT_LINE);
  });

  it('lets the person in even when the network fails, then sends the sign-up later exactly once', async () => {
    send.mockRejectedValue(new Error('no signal'));
    await expect(signIn(maria)).resolves.toBeUndefined();
    await flushAccount();
    expect((await getProfile()).name).toBe('Maria Lopez');
    expect(await signedIn()).toBe(true);
    expect(firstRun().welcomeDone).toBe(true);
    expect(send).toHaveBeenCalledTimes(1);

    await flushAccount(); // still no signal
    expect(send).toHaveBeenCalledTimes(2);

    send.mockResolvedValue({ ok: true });
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(3);
    expect(body(2).email).toBe('maria@example.com');

    await flushAccount();
    await Promise.all([flushAccount(), flushAccount()]);
    expect(send).toHaveBeenCalledTimes(3);
  });

  it('does not wait for the network', async () => {
    let finish: (v: unknown) => void = () => {};
    send.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    await signIn(maria); // comes back while the request is still in the air
    expect(await signedIn()).toBe(true);
    finish({ ok: true });
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('sends once when launch and foreground flush together', async () => {
    (isConfigured as jest.Mock).mockReturnValue(false);
    await signIn(maria);
    expect(send).not.toHaveBeenCalled(); // no server address yet: it waits
    (isConfigured as jest.Mock).mockReturnValue(true);
    await Promise.all([flushAccount(), flushAccount()]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('keeps the sign-up when the server says slow down, drops it when the server refuses it for good', async () => {
    send.mockRejectedValueOnce(new ApiError(429));
    await signIn(maria);
    await flushAccount();
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(2);

    send.mockReset().mockRejectedValueOnce(new ApiError(400));
    await signIn({ name: 'Sam', email: 'sam@example.com' });
    await flushAccount();
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('from Settings sends the source, company and offers choice, and keeps a company already on the phone', async () => {
    await signIn({ ...maria, company: ' Acme Steel ', source: 'settings', wantsOffers: true });
    await flushAccount();
    expect(body(0)).toMatchObject({ source: 'settings', company: 'Acme Steel', wants_offers: true });

    await signIn(maria);
    await flushAccount();
    expect((await getProfile()).company).toBe('Acme Steel');
  });
});

describe('skip', () => {
  it('marks welcome done without signing in or sending anything', async () => {
    await skip();
    await flushAccount();
    expect(firstRun().welcomeDone).toBe(true);
    expect(await signedIn()).toBe(false);
    expect(await getProfile()).toEqual({ name: '', email: '', company: '' });
    expect(send).not.toHaveBeenCalled();
  });
});

describe('removeMyInfo', () => {
  it('asks the server to remove the sign-up and clears the phone', async () => {
    await signIn(maria);
    await flushAccount();
    await removeMyInfo();
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(2);
    expect(path(1)).toBe('/signups/remove/');
    expect(body(1)).toEqual({ install_id: body(0).install_id });
    expect(await signedIn()).toBe(false);
    expect(await getProfile()).toEqual({ name: '', email: '', company: '' });
    expect(firstRun().welcomeDone).toBe(true); // the welcome screen does not come back

    await flushAccount();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('cancels a sign-up that never left the phone, and queues the removal', async () => {
    send.mockRejectedValue(new Error('no signal'));
    await signIn(maria);
    await flushAccount();
    await removeMyInfo();
    await flushAccount();
    send.mockReset().mockResolvedValue({ ok: true });

    await flushAccount();
    await flushAccount();
    expect(send).toHaveBeenCalledTimes(1);
    expect(path(0)).toBe('/signups/remove/');
  });

  it('sends a waiting removal before a new sign-up, so the new one is not wiped', async () => {
    await saveProfile({ name: 'Old', email: 'old@example.com', company: '' });
    send.mockRejectedValue(new Error('no signal'));
    await removeMyInfo();
    await flushAccount();
    await signIn(maria);
    await flushAccount();
    send.mockReset().mockResolvedValue({ ok: true });

    await flushAccount();
    expect(send.mock.calls.map((c) => c[0])).toEqual(['/signups/remove/', '/signups/']);
    expect(body(1).email).toBe('maria@example.com');
    expect(await signedIn()).toBe(true);
  });

  it('removing while the sign-up is in the air still ends with the removal', async () => {
    let finish: (v: unknown) => void = () => {};
    send.mockReturnValueOnce(new Promise((resolve) => (finish = resolve)));
    await signIn(maria);
    while (send.mock.calls.length === 0) await Promise.resolve();
    const removing = removeMyInfo();
    for (let i = 0; i < 20; i++) await Promise.resolve();
    finish({ ok: true });
    await removing;
    await flushAccount();
    await flushAccount();
    expect(send.mock.calls.map((c) => c[0])).toEqual(['/signups/', '/signups/remove/']);
    expect(await signedIn()).toBe(false);
  });
});

describe('validEmail', () => {
  it('takes ordinary addresses', () => {
    for (const ok of ['maria@example.com', 'maria.lopez+safety@mail.example.co.uk', 'o\'brien@acme-steel.com', 'a1@b2.io']) expect(validEmail(ok)).toBe(true);
  });

  it('tidies before checking, and tidyEmail gives what is sent', () => {
    expect(validEmail('maria@example.com.')).toBe(true);
    expect(tidyEmail(' Maria@Example.COM., ')).toBe('maria@example.com');
  });

  it('turns down the addresses Django turns down', () => {
    for (const bad of ['', 'maria', '@example.com', 'maria@', 'maria@example', 'maria@gmail..com', 'bob@site.c', 'a@b@c.com', 'maría@example.com', 'x'.repeat(65) + '@example.com', `maria@${'a'.repeat(250)}.com`]) {
      expect(validEmail(bad)).toBe(false);
    }
  });
});

describe('a sign-up the server turns down', () => {
  it('signs the phone out and asks for the email again', async () => {
    send.mockRejectedValueOnce(new ApiError(400));
    await signIn({ name: 'Maria Lopez', email: 'maria@example.com' });
    expect(await getAccount()).toEqual({ state: 'in', name: 'Maria Lopez', email: 'maria@example.com' });
    await flushAccount();
    expect(await signedIn()).toBe(false);
    expect(await getAccount()).toEqual({ state: 'fix', name: 'Maria Lopez', email: 'maria@example.com' });

    await flushAccount();
    expect(send).toHaveBeenCalledTimes(1); // dropped, not sent again

    await signIn({ name: 'Maria Lopez', email: 'maria@example.org' });
    await flushAccount();
    expect(await getAccount()).toEqual({ state: 'in', name: 'Maria Lopez', email: 'maria@example.org' });
  });

  it('does not sign out a newer sign-up made while the bad one was in the air', async () => {
    let fail: (e: unknown) => void = () => {};
    send.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)));
    await signIn({ name: 'Maria', email: 'maria@example.com' });
    while (send.mock.calls.length === 0) await Promise.resolve();
    await signIn({ name: 'Maria', email: 'maria@example.org' });
    fail(new ApiError(400));
    await flushAccount();
    await flushAccount();
    expect(await getAccount()).toMatchObject({ state: 'in', email: 'maria@example.org' });
    expect(body(send.mock.calls.length - 1).email).toBe('maria@example.org');
  });

  it('a refusal that is not about the input (403) just drops it and stays signed in', async () => {
    send.mockRejectedValueOnce(new ApiError(403));
    await signIn(maria);
    await flushAccount();
    expect((await getAccount()).state).toBe('in');
  });
});

describe('the account name and email', () => {
  it('are kept apart from the sign-in sheet profile', async () => {
    await signIn(maria);
    await flushAccount();
    await saveProfile({ name: 'Crew Lead Sam', email: 'sam@example.com', company: '' }); // the crew sign-in screen
    expect(await getAccount()).toEqual({ state: 'in', name: 'Maria Lopez', email: 'maria@example.com' });
  });

  it('are cleared by Remove my info', async () => {
    send.mockRejectedValueOnce(new ApiError(400));
    await signIn(maria);
    await flushAccount();
    await removeMyInfo();
    expect(await getAccount()).toEqual({ state: 'out', name: '', email: '' });
  });
});
