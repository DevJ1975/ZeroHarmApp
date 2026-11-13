import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import MyReportsScreen from '@/app/my-reports';
import ReportScreen from '@/app/report';
import { getAccount } from '@/lib/account';
import { api, isConfigured } from '@/lib/config';
import { flushReports } from '@/lib/support/reports';

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
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
jest.mock('@/lib/account', () => ({ getAccount: jest.fn() }));
jest.mock('expo-device', () => ({ __esModule: true, modelName: 'iPhone 15', osVersion: '18.1' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View };
});
jest.mock('expo-router', () => {
  const { useEffect } = jest.requireActual('react');
  return { router: { push: jest.fn(), replace: jest.fn() }, useFocusEffect: (run: () => void) => useEffect(run, [run]) };
});

const { ApiError } = jest.requireMock('@/lib/config') as { ApiError: new (status: number) => Error };
const mockRouter = (jest.requireMock('expo-router') as { router: { push: jest.Mock; replace: jest.Mock } }).router;
const send = api as jest.Mock;
const outbox = () => JSON.parse(mockStore.get('support_outbox') ?? '[]') as { key: string; body: Record<string, unknown> }[];
const reportCalls = () => send.mock.calls.filter((c) => c[0] === '/v2/support/report').map((c) => JSON.parse(c[1].body));
const noSignal = () => send.mockReset().mockRejectedValue(new Error('Network request failed'));
/** The server: a report gets ticket ZH-123; "mine" lists what the test put in `tickets`. */
let tickets: unknown[] = [];
const online = () => send.mockReset().mockImplementation(async (path: string) => (path === '/v2/support/mine' ? { tickets } : { number: 'ZH-123', status: 'new' }));
const signedOut = () => (getAccount as jest.Mock).mockResolvedValue({ state: 'out', name: '', email: '' });
const signedIn = () => (getAccount as jest.Mock).mockResolvedValue({ state: 'in', name: 'Maria Lopez', email: 'maria@example.com' });

const WHAT = 'What happened?';
const typed = 'The app closes when I open a talk';

async function form() {
  await render(<ReportScreen />);
  await act(async () => {}); // let the saved email load
}
const press = (name: string) => fireEvent.press(screen.getByRole('button', { name }));

beforeEach(async () => {
  await flushReports();
  mockStore.clear();
  mockRouter.push.mockClear();
  mockRouter.replace.mockClear();
  tickets = [];
  online();
  signedOut();
  (isConfigured as jest.Mock).mockReturnValue(true);
});

describe('Report a problem', () => {
  it('says exactly what is sent, and that it is for the app, not for an emergency', async () => {
    await form();
    expect(
      screen.getByText(
        'A report sends Trainovate what you write, your email if you give one, your phone model (iPhone 15, iOS 18.1), the app version (1.0.0) and a random id for this app, so you can see your reports later. Nothing else.',
      ),
    ).toBeTruthy();
    expect(
      screen.getByText('This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.'),
    ).toBeTruthy();
  });

  it('counts an emoji as one character, as the server does, so a too-short report is caught on the phone', async () => {
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), '😀😀a');
    await press('Send report');
    expect(screen.getByText('Tell us what happened in a few words.')).toBeTruthy();
    expect(send).not.toHaveBeenCalled();
  });

  it('when the server says the words do not pass its check (422), asks for more instead of "try again later"', async () => {
    send.mockReset().mockRejectedValue(new ApiError(422));
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText('Tell us a little more about what happened, then send it again.')).toBeTruthy());
    expect(screen.queryByText(/Try again later/)).toBeNull();
    expect(screen.getByLabelText(WHAT).props.value).toBe(typed);
  });

  it('asks for a few words and sends nothing until it has them', async () => {
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), ' bad ');
    await press('Send report');
    expect(screen.getByText('Tell us what happened in a few words.')).toBeTruthy();
    expect(outbox()).toHaveLength(0);
    expect(send).not.toHaveBeenCalled();
  });

  it('with a signal: sends the words, the phone and the app version, and shows the reference', async () => {
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText('Reported. Your reference is ZH-123.')).toBeTruthy());
    expect(reportCalls()).toHaveLength(1);
    const body = reportCalls()[0];
    expect(body).toMatchObject({ text: typed, source: 'form', lang: 'en', device: 'iPhone 15', os_version: '18.1', app_version: '1.0.0', platform: 'ios' });
    // Only what the line under the button names: no email, no name, no screen.
    expect(Object.keys(body).sort()).toEqual(['app_version', 'client_key', 'device', 'install_id', 'lang', 'os_version', 'platform', 'source', 'text']);
    expect(outbox()).toHaveLength(0);
  });

  it('with no signal: saves the report on the phone and says it will send later', async () => {
    noSignal();
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText('Saved on this phone. It will send when you have signal.')).toBeTruthy());
    expect(outbox()).toHaveLength(1);
    expect(outbox()[0].body).toMatchObject({ text: typed, source: 'form' });

    // Back in signal, the next flush sends that same report once, under the key made on the phone.
    online();
    await flushReports();
    expect(reportCalls()).toHaveLength(1);
    expect(reportCalls()[0]).toMatchObject({ text: typed, client_key: expect.stringMatching(/^p-/) });
    expect(outbox()).toHaveLength(0);
  });

  it('works with no server address at all (OTIS off, nothing set up): the report is kept', async () => {
    (isConfigured as jest.Mock).mockReturnValue(false);
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText('Saved on this phone. It will send when you have signal.')).toBeTruthy());
    expect(outbox()).toHaveLength(1);
    expect(send).not.toHaveBeenCalled();
  });

  it('when the server turns the report down for good, it says so and keeps what was typed on screen', async () => {
    send.mockReset().mockRejectedValue(new ApiError(400));
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText('That report could not be sent. Try again later.')).toBeTruthy());
    expect(screen.getByLabelText(WHAT).props.value).toBe(typed);
    expect(screen.queryByText('Thank you')).toBeNull();
  });

  it('a Spanish report is marked as Spanish', async () => {
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), 'La aplicación se cierra y no puedo ver la charla');
    await press('Send report');
    await waitFor(() => expect(screen.getByText(/Reported\./)).toBeTruthy());
    expect(reportCalls()[0]).toMatchObject({ lang: 'es' });
  });

  describe('the email', () => {
    it('one already on the phone is filled in but NOT sent unless "OK to reply to me" is turned on', async () => {
      signedIn();
      await form();
      expect(screen.getByLabelText('Email (optional)').props.value).toBe('maria@example.com');
      expect(screen.getByLabelText('OK to reply to me').props.value).toBe(false);
      expect(screen.getByText('Off: your email is not sent.')).toBeTruthy();
      await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
      await press('Send report');
      await waitFor(() => expect(screen.getByText(/Reported\./)).toBeTruthy());
      expect(reportCalls()[0]).not.toHaveProperty('email');
      expect(reportCalls()[0]).not.toHaveProperty('may_contact');
    });

    it('is sent, with leave to reply, once the switch is on', async () => {
      signedIn();
      await form();
      await fireEvent(screen.getByLabelText('OK to reply to me'), 'valueChange', true);
      expect(screen.getByText('On: your email is sent with the report.')).toBeTruthy();
      await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
      await press('Send report');
      await waitFor(() => expect(screen.getByText(/Reported\./)).toBeTruthy());
      expect(reportCalls()[0]).toMatchObject({ email: 'maria@example.com', may_contact: true });
    });

    it('typing an address turns the switch on, and it can be turned off again', async () => {
      await form();
      const toggle = () => screen.getByLabelText('OK to reply to me');
      expect(toggle().props.disabled).toBe(true); // nothing to reply to yet
      await fireEvent.changeText(screen.getByLabelText('Email (optional)'), 'Sam@Example.com ');
      expect(toggle().props.value).toBe(true);
      await fireEvent(toggle(), 'valueChange', false);
      await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
      await press('Send report');
      await waitFor(() => expect(screen.getByText(/Reported\./)).toBeTruthy());
      expect(reportCalls()[0]).not.toHaveProperty('email');
    });

    it('a mistyped address is caught before anything is sent', async () => {
      await form();
      await fireEvent.changeText(screen.getByLabelText('Email (optional)'), 'sam@');
      await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
      await press('Send report');
      expect(screen.getByText('Check the email address, or turn off OK to reply to me.')).toBeTruthy();
      expect(send).not.toHaveBeenCalled();
      expect(outbox()).toHaveLength(0);
    });
  });

  it('after sending, "My reports" opens the list and "Report another problem" clears the form', async () => {
    await form();
    await fireEvent.changeText(screen.getByLabelText(WHAT), typed);
    await press('Send report');
    await waitFor(() => expect(screen.getByText(/Reported\./)).toBeTruthy());
    await press('My reports');
    expect(mockRouter.replace).toHaveBeenCalledWith('/my-reports');
    await press('Report another problem');
    expect(screen.getByLabelText(WHAT).props.value).toBe('');
  });
});

describe('My reports', () => {
  const list = async () => {
    await render(<MyReportsScreen />);
    await act(async () => {});
  };

  it('says there are none yet, and offers the form', async () => {
    await list();
    await waitFor(() => expect(screen.getByText('No reports yet. If something in the app goes wrong, tell us.')).toBeTruthy());
    await press('Report a problem');
    expect(mockRouter.push).toHaveBeenCalledWith('/report');
  });

  it('shows the status in words and the reply from Trainovate', async () => {
    tickets = [
      { number: 'ZH-9', status: 'fixed', title: 'Talk will not open', created_at: '2026-11-02T18:00:00Z', updated_at: '2026-11-03T18:00:00Z', reply: 'Fixed in the next update. Thanks for telling us.' },
      { number: 'ZH-4', status: 'in_progress', title: 'No Monday notification', created_at: '2026-10-20T18:00:00Z', updated_at: '2026-10-21T18:00:00Z', reply: '' },
    ];
    await list();
    await waitFor(() => expect(screen.getByText('Talk will not open')).toBeTruthy());
    expect(screen.getByText(/^ZH-9 · /)).toBeTruthy();
    expect(screen.getByText('Status: Fixed')).toBeTruthy();
    expect(screen.getByText('Reply from Trainovate')).toBeTruthy();
    expect(screen.getByText('Fixed in the next update. Thanks for telling us.')).toBeTruthy();
    expect(screen.getByText('No Monday notification')).toBeTruthy();
    expect(screen.getByText('Status: Being looked at')).toBeTruthy();
    // POST, so the install id is never part of a web address.
    const mine = send.mock.calls.find((c) => c[0] === '/v2/support/mine')!;
    expect(mine[1].method).toBe('POST');
  });

  it('with no signal: draws what is saved on the phone, and marks a report that has not been sent', async () => {
    mockStore.set('support_reports', JSON.stringify([{ ref: 'p-old', number: 'ZH-2', status: 'new', title: 'Sheet did not print', created_at: '2026-10-01T18:00:00Z' }]));
    mockStore.set(
      'support_outbox',
      JSON.stringify([{ key: 'p-new', at: '2026-11-10T18:00:00Z', mine: true, body: { text: 'OTIS will not download\nIt stops at 40%', source: 'form' } }]),
    );
    noSignal();
    await list();
    await waitFor(() => expect(screen.getByText('OTIS will not download')).toBeTruthy());
    expect(screen.getByText(/^Not sent yet · /)).toBeTruthy();
    expect(screen.getByText('Status: Waiting to send')).toBeTruthy();
    expect(screen.getByText('A report is saved on this phone. It will send when you have signal.')).toBeTruthy();
    expect(screen.getByText('Sheet did not print')).toBeTruthy();
    expect(screen.getByText('Status: Received')).toBeTruthy();
    expect(outbox()).toHaveLength(1); // still waiting, not lost
  });

  it('a report waiting on the phone is sent when the list is opened in signal, and then shows its number', async () => {
    mockStore.set('support_outbox', JSON.stringify([{ key: 'p-new', at: new Date().toISOString(), mine: true, body: { text: 'OTIS will not download', source: 'form' } }]));
    await list();
    await waitFor(() => expect(screen.getByText(/^ZH-123 · /)).toBeTruthy());
    expect(screen.queryByText('Status: Waiting to send')).toBeNull();
    expect(outbox()).toHaveLength(0);
  });

  it('a report that waited and was then turned down says so, instead of vanishing', async () => {
    mockStore.set('support_outbox', JSON.stringify([{ key: 'p-new', at: new Date().toISOString(), mine: true, body: { text: 'OTIS will not download', source: 'form' } }]));
    send.mockReset().mockImplementation(async (path: string) => {
      if (path === '/v2/support/mine') return { tickets: [] };
      throw new ApiError(422);
    });
    await list();
    await waitFor(() => expect(screen.getByText('Status: Could not be sent')).toBeTruthy());
    expect(screen.getByText('OTIS will not download')).toBeTruthy();
    expect(screen.getByText(/^Not sent · /)).toBeTruthy();
    expect(screen.getByText('Trainovate did not get this report. If the problem is still there, report it again.')).toBeTruthy();
  });

  it('never shows a flagged OTIS answer in the list', async () => {
    mockStore.set('support_outbox', JSON.stringify([{ key: 'p-ans', at: '2026-11-10T18:00:00Z', mine: false, body: { text: 'Flagged OTIS answer', source: 'otis_answer' } }]));
    noSignal();
    await list();
    await waitFor(() => expect(screen.getByText(/No reports yet/)).toBeTruthy());
    expect(screen.queryByText('Flagged OTIS answer')).toBeNull();
  });
});
