import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AppState, StyleSheet } from 'react-native';

import { CrashScreen } from '@/components/CrashScreen';
import { api, ApiError, isConfigured } from '@/lib/config';
import { setCrashReportsOn } from '@/lib/support/crash';
import { flushReports } from '@/lib/support/reports';

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
  return { api: jest.fn(), isConfigured: jest.fn(), ApiError };
});
jest.mock('expo-device', () => ({ __esModule: true, modelName: 'Pixel 8', osVersion: '15' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View };
});
// The screen is drawn above the navigator when the whole app has fallen over. If it ever loads the router (a Link,
// router.push), this throws and every test here fails.
jest.mock('expo-router', () => {
  throw new Error('the crash screen must not load the router');
});

const send = api as jest.Mock;
const crashes = () => JSON.parse(mockStore.get('crash_outbox') ?? '[]') as { name: string; message: string; fatal: boolean }[];
const reports = () => JSON.parse(mockStore.get('support_outbox') ?? '[]') as { body: Record<string, unknown> }[];
const noSignal = () => send.mockReset().mockRejectedValue(new Error('Network request failed'));
const reportCalls = () => send.mock.calls.filter((c) => c[0] === '/v2/support/report');
const sentBody = () => JSON.parse(send.mock.calls.find((c) => c[0] === '/v2/support/report')![1].body);

// The crash recorder drops an error it has seen in the last ten minutes, so each test breaks in its own way.
let nth = 0;
const words = ['alpha', 'bravo', 'charlie', 'delta', 'echo', 'foxtrot', 'golf', 'hotel', 'india', 'juliet', 'kilo', 'lima'];
const boom = () => new TypeError(`cannot read ${words[nth++]} of undefined`);

async function show(error: Error = boom()) {
  const retry = jest.fn(() => Promise.resolve());
  await render(<CrashScreen error={error} retry={retry} />);
  return { retry, error };
}

async function openForm(text: string, email = '') {
  await fireEvent.press(screen.getByRole('button', { name: 'Report this problem' }));
  await fireEvent.changeText(screen.getByLabelText('What were you doing when this happened?'), text);
  if (email) await fireEvent.changeText(screen.getByLabelText('Email, if you want a reply (optional)'), email);
}

beforeEach(async () => {
  await flushReports();
  mockStore.clear();
  setCrashReportsOn(true); // and forget the switch read a moment ago, when a test turned it off
  send.mockReset().mockResolvedValue({ number: 'ZH-31', status: 'new' });
  (isConfigured as jest.Mock).mockReturnValue(true);
});

describe('the crash screen', () => {
  it('saves a crash report for the error, marked as one the screen could not carry on from', async () => {
    noSignal();
    const { error } = await show();
    expect(crashes()).toHaveLength(1);
    expect(crashes()[0]).toMatchObject({ name: 'TypeError', message: error.message, fatal: true });
    expect(screen.getByRole('header', { name: 'Something went wrong' })).toBeTruthy();
    expect(
      screen.getByText(
        "The app hit an error. It saved a short report for Trainovate with what the error said and where in the app's code it happened, whether the app had to close, the screen you were on, the time, the app version, iPhone or Android, the system version, your phone model, and a random id for this app. It is built to leave out what you typed, your name and your email.",
      ),
    ).toBeTruthy();
  });

  it('sends the crash report from here, since the layout that normally sends it may be the thing that failed', async () => {
    const { error } = await show();
    await waitFor(() => expect(crashes()).toHaveLength(0));
    const call = send.mock.calls.find((c) => c[0] === '/v2/support/crash');
    expect(JSON.parse(call![1].body)).toMatchObject({ name: 'TypeError', message: error.message, fatal: true });
  });

  it('with no signal, sends what is waiting when the app comes back to the front', async () => {
    let onAppState: (state: string) => void = () => {};
    jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, handler) => {
      onAppState = handler as (state: string) => void;
      return { remove: jest.fn() } as unknown as ReturnType<typeof AppState.addEventListener>;
    });
    noSignal();
    await show();
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText('Saved on this phone. It will send when you have signal.')).toBeTruthy());
    expect(reports()).toHaveLength(1);
    expect(crashes()).toHaveLength(1);
    send.mockReset().mockResolvedValue({ number: 'ZH-32', status: 'new' });
    await act(async () => onAppState('active'));
    await waitFor(() => expect(reports()).toHaveLength(0));
    await waitFor(() => expect(crashes()).toHaveLength(0));
    expect(send.mock.calls.map((c) => c[0]).sort()).toEqual(['/v2/support/crash', '/v2/support/report']);
    jest.restoreAllMocks();
  });

  it('says so, and saves nothing, when crash reports are switched off', async () => {
    setCrashReportsOn(false);
    await show();
    expect(crashes()).toHaveLength(0);
    expect(screen.getByText('The app hit an error. Crash reports are off, so no report was saved.')).toBeTruthy();
    expect(screen.queryByText(/It saved a short report/)).toBeNull();
  });

  it('"Try again" calls retry', async () => {
    const { retry } = await show();
    await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('sends no problem report just by being shown: only the crash report', async () => {
    await show();
    await waitFor(() => expect(crashes()).toHaveLength(0));
    expect(send.mock.calls.map((c) => c[0])).toEqual(['/v2/support/crash']);
  });

  it('every control has a role and a label, and no text relies on a font that may not have loaded', async () => {
    await show();
    await fireEvent.press(screen.getByRole('button', { name: 'Report this problem' }));
    for (const name of ['Send report', 'Cancel']) expect(screen.getByRole('button', { name })).toBeTruthy();
    expect(screen.getByLabelText('What were you doing when this happened?')).toBeTruthy();
    expect(screen.getByLabelText('Email, if you want a reply (optional)')).toBeTruthy();
    const sized = screen.container.queryAll((node) => StyleSheet.flatten(node.props.style)?.fontSize !== undefined);
    expect(sized.length).toBeGreaterThan(5); // the search does see the text styles
    const named = screen.container.queryAll((node) => StyleSheet.flatten(node.props.style)?.fontFamily !== undefined);
    expect(named).toHaveLength(0);
  });
});

describe('"Report this problem" on the crash screen', () => {
  it('says exactly what a report sends, under the form', async () => {
    await show();
    await fireEvent.press(screen.getByRole('button', { name: 'Report this problem' }));
    expect(
      screen.getByText(
        'A report sends Trainovate what you write, your email if you give one, your phone model (Pixel 8, iOS 15), the app version (1.0.0) and a random id for this app, so you can see your reports later. Nothing else.',
      ),
    ).toBeTruthy();
  });

  it('asks for a few words before it sends anything', async () => {
    await show();
    await openForm('hm');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    expect(screen.getByText('Tell us what happened in a few words.')).toBeTruthy();
    expect(reports()).toHaveLength(0);
    expect(reportCalls()).toHaveLength(0);
  });

  it('counts an emoji as one character, as the server does, so a too-short report is caught here', async () => {
    await show();
    await openForm('😀😀a');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    expect(screen.getByText('Tell us what happened in a few words.')).toBeTruthy();
    expect(reportCalls()).toHaveLength(0);
  });

  it('says where a report goes, and where a hazard or an injury goes, before anything is sent', async () => {
    await show();
    await openForm('');
    expect(
      screen.getByText('This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.'),
    ).toBeTruthy();
  });

  it('when the server says the words do not pass its check, asks for more instead of "try again later"', async () => {
    send.mockImplementation((path: string) => (path === '/v2/support/report' ? Promise.reject(new ApiError(422)) : Promise.resolve({})));
    await show();
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText('Tell us a little more about what happened, then send it again.')).toBeTruthy());
    expect(screen.queryByText(/Try again later/)).toBeNull();
  });

  it('will not send an email address that is not one', async () => {
    await show();
    await openForm('It broke when I opened a talk', 'maria@');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    expect(screen.getByText('Check the email address, or leave it blank.')).toBeTruthy();
    expect(reportCalls()).toHaveLength(0);
  });

  it('with a signal: sends the words and shows the reference', async () => {
    await show();
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText('Reported. Your reference is ZH-31.')).toBeTruthy());
    expect(sentBody()).toMatchObject({ text: 'It broke when I opened a talk', source: 'form', device: 'Pixel 8', app_version: '1.0.0' });
    expect(sentBody()).not.toHaveProperty('email');
    expect(reports()).toHaveLength(0); // nothing left waiting
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  it('a typed email goes with the report, as the address to reply to', async () => {
    await show();
    await openForm('It broke when I opened a talk', ' Maria@Example.com ');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText('Reported. Your reference is ZH-31.')).toBeTruthy());
    expect(sentBody()).toMatchObject({ email: 'maria@example.com', may_contact: true });
  });

  it('with no signal: the report is saved on the phone and the screen says so', async () => {
    noSignal();
    await show();
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText('Saved on this phone. It will send when you have signal.')).toBeTruthy());
    expect(reports()).toHaveLength(1);
    expect(reports()[0].body).toMatchObject({ text: 'It broke when I opened a talk', source: 'form' });
  });

  it('a failed send of the report is not itself saved as a crash', async () => {
    noSignal();
    await show();
    const before = crashes().length;
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Send report' }));
    await waitFor(() => expect(screen.getByText(/Saved on this phone/)).toBeTruthy());
    expect(crashes()).toHaveLength(before);
  });

  it('"Cancel" goes back to the two buttons and sends nothing', async () => {
    await show();
    await openForm('It broke when I opened a talk');
    await fireEvent.press(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('button', { name: 'Report this problem' })).toBeTruthy();
    expect(reportCalls()).toHaveLength(0);
    expect(reports()).toHaveLength(0);
    await act(async () => {});
  });
});
