import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert, Linking } from 'react-native';

import SettingsScreen from '@/app/settings';
import { flushAccount, getAccount, removeMyInfo, signIn } from '@/lib/account';
import { crashReportsOn } from '@/lib/support/crash';

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    setItem: (key: string, value: string) => Promise.resolve(void mockStore.set(key, value)),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
    getItemSync: (key: string) => mockStore.get(key) ?? null,
    setItemSync: (key: string, value: string) => void mockStore.set(key, value),
    removeItemSync: (key: string) => mockStore.delete(key),
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
  return { api: jest.fn(), isConfigured: () => true, ApiError, config: { privacyUrl: '', termsUrl: '', supportEmail: 'help@example.com' } };
});
// The wording and the checks are the real ones; only what talks to storage and the server is replaced.
jest.mock('@/lib/account', () => ({
  ...jest.requireActual('@/lib/account'),
  getAccount: jest.fn(),
  signIn: jest.fn(),
  removeMyInfo: jest.fn(),
  flushAccount: jest.fn(),
}));
jest.mock('@/lib/profile', () => ({ ...jest.requireActual('@/lib/profile'), getProfile: () => Promise.resolve({ name: '', email: '', company: '' }) }));
jest.mock('@/lib/push', () => ({
  getPrefs: () => Promise.resolve({ mondayMinute: false, weeklyTalk: false, alerts: false, zeroHour: false, offers: false }),
  setPrefs: jest.fn(),
}));
jest.mock('@/lib/usage', () => ({ getUsageOn: () => Promise.resolve(true), setUsageOn: jest.fn() }));
jest.mock('@/lib/otis/feedback', () => ({
  getFeedbackPrefs: () => Promise.resolve({ helpImprove: false, shareQuestion: false }),
  saveFeedbackPrefs: jest.fn(),
}));
jest.mock('expo-device', () => ({ __esModule: true, modelName: 'Pixel 8', osVersion: '15' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));
jest.mock('expo-web-browser', () => ({ openBrowserAsync: jest.fn() }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() } }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View };
});

const router = (jest.requireMock('expo-router') as { router: { push: jest.Mock } }).router;
const account = getAccount as jest.Mock;
const remove = removeMyInfo as jest.Mock;
const maria = { state: 'in', name: 'Maria Lopez', email: 'maria@example.com' };
const out = { state: 'out', name: '', email: '' };

const NOT_CHANGED =
  'This email is already signed up from another phone or an earlier install of the app, so your name, company and offers choice were not changed. Contact support and we will change them.';

async function open() {
  await render(<SettingsScreen />);
  await act(async () => {});
}
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
/** Taps "Remove my info", then the red "Remove" in the question that comes up. Hands back the question's text. */
async function confirmRemove() {
  await press('Remove my info');
  const [title, text, buttons] = (Alert.alert as jest.Mock).mock.calls.at(-1) as [string, string, { text: string; onPress?: () => Promise<void> }[]];
  await act(async () => {
    await buttons.find((b) => b.text === 'Remove')?.onPress?.();
  });
  return { title, text };
}

beforeEach(() => {
  mockStore.clear();
  account.mockReset().mockResolvedValue(out);
  remove.mockReset().mockResolvedValue('removed');
  (signIn as jest.Mock).mockReset().mockResolvedValue(undefined);
  (flushAccount as jest.Mock).mockReset().mockResolvedValue(undefined);
  router.push.mockReset();
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

describe('Settings: crash reports', () => {
  const toggle = () => screen.getByLabelText('Crash reports');

  it('is on unless the person turned it off, and says what is and is not sent', async () => {
    await open();
    expect(toggle().props.value).toBe(true);
    expect(
      screen.getByText(
        "When the app hits an error, it sends what the error said and where in the app's code it happened, whether the app had to close, the screen you were on, the time, the app version, iPhone or Android, the system version, your phone model, and a random id for this app. It is built to leave out what you typed, your name and your email. Turning it off also deletes any reports waiting on this phone.",
      ),
    ).toBeTruthy();
  });

  it('turning it off stops them and deletes what was waiting on the phone', async () => {
    mockStore.set('crash_outbox', JSON.stringify([{ client_key: 'c-1', name: 'TypeError', message: 'x', stack: '', fatal: true, screen: '/otis', at: '2026-11-10T18:00:00Z' }]));
    await open();
    await fireEvent(toggle(), 'valueChange', false);
    expect(toggle().props.value).toBe(false);
    expect(crashReportsOn()).toBe(false);
    expect(mockStore.has('crash_outbox')).toBe(false);
  });

  it('shows the saved choice when Settings is opened again, and turns back on', async () => {
    mockStore.set('crash_reports', 'off');
    await open();
    expect(toggle().props.value).toBe(false);
    await fireEvent(toggle(), 'valueChange', true);
    expect(toggle().props.value).toBe(true);
    expect(crashReportsOn()).toBe(true);
  });
});

describe('Settings: reporting a problem', () => {
  it('has "Report a problem" and "My reports"', async () => {
    await open();
    await press('Report a problem');
    expect(router.push).toHaveBeenLastCalledWith('/report');
    await press('My reports');
    expect(router.push).toHaveBeenLastCalledWith('/my-reports');
  });

  it('keeps the credit line at the very bottom', async () => {
    await open();
    const texts = screen.container.queryAll((node) => node.type === 'Text').map((node) => node.props.children);
    expect(texts.at(-1)).toBe('Made with love ❤️ from Las Vegas, Trainovate');
  });
});

describe('Settings: what the server said about the sign-up', () => {
  it('"Signed in as" shows the name and email this phone signed up with', async () => {
    account.mockResolvedValue(maria);
    await open();
    expect(screen.getByText('Signed in as Maria Lopez, maria@example.com')).toBeTruthy();
    expect(screen.queryByText(NOT_CHANGED)).toBeNull();
  });

  it('a sign-up another phone made: says the details were not changed, and never shows the typed name as saved', async () => {
    account.mockResolvedValue({ state: 'in', name: '', email: 'maria@example.com', notice: 'not_changed' });
    await open();
    expect(screen.getByText('Signed in as maria@example.com')).toBeTruthy();
    expect(screen.getByText(NOT_CHANGED)).toBeTruthy();
  });

  it('signing in: when the server answers "not changed", the name just typed stops being shown as saved', async () => {
    await open();
    await fireEvent.changeText(screen.getByLabelText('Your name'), 'Maria L');
    await fireEvent.changeText(screen.getByLabelText('Email'), 'maria@example.com');
    account.mockResolvedValue({ state: 'in', name: '', email: 'maria@example.com', notice: 'not_changed' });
    await press('Sign in');
    await waitFor(() => expect(screen.getByText(NOT_CHANGED)).toBeTruthy());
    expect(flushAccount).toHaveBeenCalled();
    expect(screen.getByText('Signed in as maria@example.com')).toBeTruthy();
    expect(screen.queryByText(/Maria L/)).toBeNull();
  });

  it('the "Remove my info?" question describes the real rule for both kinds of phone', async () => {
    account.mockResolvedValue(maria);
    await open();
    const asked = await confirmRemove();
    expect(asked.title).toBe('Remove my info?');
    expect(asked.text).toContain('If this phone made your sign-up, the sign-up is deleted');
    expect(asked.text).toContain('If another phone made it, nothing is deleted yet: we ask a person at Trainovate to remove it.');
  });

  it('removed: says removed', async () => {
    account.mockResolvedValue(maria);
    await open();
    await confirmRemove();
    expect(screen.getByText('Removed. Your name and email are cleared from this phone. If this phone made your sign-up, the sign-up is deleted too.')).toBeTruthy();
    expect(screen.queryByText(/Signed in as/)).toBeNull();
  });

  it('pending: says a person will remove it, and never says "Removed"', async () => {
    account.mockResolvedValue(maria);
    remove.mockResolvedValue('pending');
    await open();
    await confirmRemove();
    expect(screen.getByText('We got your request. A person will remove your info.')).toBeTruthy();
    expect(screen.queryByText(/^Removed/)).toBeNull();
  });

  it('no signal: says the request will send later', async () => {
    account.mockResolvedValue(maria);
    remove.mockResolvedValue('waiting');
    await open();
    await confirmRemove();
    expect(screen.getByText('Cleared from this phone. Your request will send when you have signal.')).toBeTruthy();
    expect(screen.queryByText(/^Removed/)).toBeNull();
  });

  it('a removal still with a person is said again when Settings is opened later', async () => {
    account.mockResolvedValue({ ...out, notice: 'removal_pending' });
    await open();
    expect(screen.getByText('We got your request. A person will remove your info.')).toBeTruthy();
  });

  it('the button shows it is working while the server is asked, and nothing is said until it answers', async () => {
    account.mockResolvedValue(maria);
    let answer: (o: string) => void = () => {};
    remove.mockReturnValue(new Promise<string>((done) => (answer = done)));
    await open();
    await press('Remove my info');
    const buttons = (Alert.alert as jest.Mock).mock.calls.at(-1)[2] as { text: string; onPress?: () => Promise<void> }[];
    let going: Promise<void> | undefined;
    await act(async () => {
      going = buttons.find((b) => b.text === 'Remove')?.onPress?.();
    });
    expect(screen.queryByText(/^Removed|We got your request/)).toBeNull();
    expect(screen.queryByText('Remove my info')).toBeNull(); // the button shows a spinner in place of its label
    expect(screen.getByText('Signed in as Maria Lopez, maria@example.com')).toBeTruthy();
    await act(async () => {
      answer('pending');
      await going;
    });
    expect(screen.getByText('We got your request. A person will remove your info.')).toBeTruthy();
  });

  it('if the phone could not do it, it says so and stays signed in', async () => {
    account.mockResolvedValue(maria);
    remove.mockRejectedValue(new Error('disk full'));
    await open();
    await confirmRemove();
    expect(screen.getByText('That did not work on this phone. Tap Remove my info again.')).toBeTruthy();
    expect(screen.getByText('Signed in as Maria Lopez, maria@example.com')).toBeTruthy();
  });
});

describe('Settings: what leaves the phone', () => {
  it('the OTIS line says a question can also leave the phone when the person reports a problem or an answer', async () => {
    await open();
    expect(screen.getByText('OTIS runs on this phone. What you ask stays on it unless you turn this on, or you choose to report a problem or an answer.')).toBeTruthy();
    expect(screen.queryByText(/Nothing you ask leaves it/)).toBeNull();
  });

  it('a sign-up the server did not change offers a way to contact support right under the notice', async () => {
    const openURL = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
    account.mockResolvedValue({ state: 'in', name: '', email: 'maria@example.com', notice: 'not_changed' });
    await open();
    await press('Contact support about my sign-up');
    expect(openURL).toHaveBeenCalledWith('mailto:help@example.com?subject=Change%20my%20Zero%20Harm%20sign-up');
  });
});

describe('Settings: the "not changed" line in a build with no support address', () => {
  const config = (jest.requireMock('@/lib/config') as { config: { supportEmail: string } }).config;
  afterEach(() => {
    config.supportEmail = 'help@example.com';
  });

  it('does not tell the person to contact support when there is no way to', async () => {
    config.supportEmail = '';
    account.mockResolvedValue({ state: 'in', name: '', email: 'maria@example.com', notice: 'not_changed' });
    await open();
    expect(screen.getByText('This email is already signed up from another phone or an earlier install of the app, so your name, company and offers choice were not changed.')).toBeTruthy();
    expect(screen.queryByText(/Contact support/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Contact support about my sign-up' })).toBeNull();
  });
});
