import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import OtisScreen from '@/app/otis';
import { getAccount } from '@/lib/account';
import { api } from '@/lib/config';
import { loadKb, type KbItem } from '@/lib/otis/kb';
import served from './fixtures/otis-kb-served.json';
import { getManifest } from '@/lib/otis/manifest';
import { recordError } from '@/lib/support/crash';
import { fileReport, reportAnswer } from '@/lib/support/reports';

// ---- The phone around the screen ----------------------------------------------------------------------

const MODEL = { key: 'qwen3-test', label: 'OTIS', size_mb: 1100, builtin: 'QWEN3_1_7B', files: null };

const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    setItem: (key: string, value: string) => Promise.resolve(void mockStore.set(key, value)),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
  },
}));
// The model on the phone. `sendMessage` is the only way anything reaches it.
const mockLlm: { isReady: boolean; error: Error | null; downloadProgress: number; sendMessage: jest.Mock } = {
  isReady: true,
  error: null,
  downloadProgress: 1,
  sendMessage: jest.fn(),
};
jest.mock('react-native-executorch', () => ({ setTelemetryEnabled: jest.fn(), useLLMChatSession: () => mockLlm }));
jest.mock('expo-router', () => ({ router: { push: jest.fn() }, Stack: { Screen: () => null } }));
jest.mock('expo-web-browser', () => ({ openBrowserAsync: jest.fn() }));
jest.mock('react-native-safe-area-context', () => {
  const { View } = jest.requireActual('react-native');
  return { SafeAreaView: View };
});
jest.mock('@/lib/config', () => ({ api: jest.fn(), apiFetch: jest.fn(), isConfigured: () => true, config: {} }));
jest.mock('@/lib/live', () => ({ useContentRefresh: jest.fn(), noteStaleContent: jest.fn() }));
jest.mock('@/lib/otis/manifest', () => ({
  getManifest: jest.fn(),
  llmModel: (m: unknown) => m,
  sizeLabel: () => '1.1 GB',
  kbVersionKey: 'otis_kb_version',
}));
// The real search runs; only the download is replaced.
jest.mock('@/lib/otis/kb', () => ({ ...jest.requireActual('@/lib/otis/kb'), loadKb: jest.fn() }));
jest.mock('@/lib/otis/feedback', () => ({
  getFeedbackPrefs: () => Promise.resolve({ helpImprove: false, shareQuestion: false }),
  sendFeedback: jest.fn(),
}));
jest.mock('@/lib/account', () => ({ getAccount: jest.fn() }));
jest.mock('@/lib/profile', () => ({ ...jest.requireActual('@/lib/profile'), getProfile: () => Promise.resolve({ name: '', email: '', company: '' }) }));
jest.mock('@/lib/support/device', () => ({ deviceInfo: () => ({ app_version: '1.0.0', platform: 'ios', os_version: '18.1', device: 'iPhone 15' }) }));
jest.mock('@/lib/support/crash', () => ({ recordError: jest.fn() }));
// The two ways anything typed here can leave the phone. Both are replaced, so every call is counted.
jest.mock('@/lib/support/reports', () => ({ fileReport: jest.fn(), reportAnswer: jest.fn() }));

const router = (jest.requireMock('expo-router') as { router: { push: jest.Mock } }).router;
const file = fileReport as jest.Mock;
const flag = reportAnswer as jest.Mock;
const fetchSpy = jest.fn();


/**
 * The chat screen with the knowledge base the server really sends (__tests__/fixtures/otis-kb-served.json), walking
 * the cases the review of the first version found on a real screen.
 */
const KB = (served as { items: KbItem[] }).items;
const BANNER = 'If someone is hurt or in danger right now, call 911 first.';
const GOES_TO = 'This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.';
const ON_HOLD = 'Your report is on hold. Nothing was sent. If your message was about the app, open Settings and tap Report a problem.';
const ANSWER = 'Stop and get help [1].';

const box = () => screen.getByLabelText(/^(Question for OTIS|What went wrong with the app\?|Your email|¿Qué falló en la app\?|Su correo)$/);
const tap = (name: string) => fireEvent.press(screen.getByRole('button', { name }));
async function say(text: string) {
  await fireEvent.changeText(box(), text);
  await tap('Send');
  await act(async () => {});
}
async function openChat() {
  await render(<OtisScreen />);
  await waitFor(() => expect(box()).toBeTruthy());
  await act(async () => {});
}
const sentToModel = () => mockLlm.sendMessage.mock.calls.map((c) => c[0] as string);
const supportTitles = new Set(KB.filter((d) => d.kind === 'support').map((d) => d.title));
/** No line on screen is a support entry or a report offer. */
function noSupportPath() {
  for (const title of supportTitles) expect(screen.queryByText(new RegExp(`^${title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s`))).toBeNull();
  expect(screen.queryByRole('button', { name: 'Report this problem' })).toBeNull();
  expect(screen.queryByText(/I don't have a fix for that yet/)).toBeNull();
}

beforeEach(() => {
  mockStore.clear();
  mockStore.set('otis_downloaded_model', JSON.stringify(MODEL));
  (getManifest as jest.Mock).mockResolvedValue({ enabled: true, update_required: false, message: '', model: MODEL, feedback_enabled: false });
  (loadKb as jest.Mock).mockResolvedValue(KB);
  (getAccount as jest.Mock).mockResolvedValue({ state: 'out', name: '', email: '' });
  (api as jest.Mock).mockReset();
  (recordError as jest.Mock).mockReset();
  router.push.mockReset();
  file.mockReset().mockResolvedValue({ ref: 'p-1', number: 'ZH-7', queued: false });
  flag.mockReset().mockResolvedValue({ ref: 'p-2', number: 'ZH-8', queued: false });
  mockLlm.isReady = true;
  mockLlm.error = null;
  mockLlm.downloadProgress = 1;
  mockLlm.sendMessage = jest.fn(async (_turn: string, onToken: (t: string) => void) => onToken(ANSWER));
  fetchSpy.mockReset();
  (globalThis as { fetch: unknown }).fetch = fetchSpy;
});
afterEach(() => jest.restoreAllMocks());

describe('an emergency that mentions a failing machine or screen: banner, then the safety answer from the model', () => {
  test.each([
    'the press glitched and came down on his hand',
    'the light curtain glitched and the press cycled on her arm',
    'the gas monitor screen went blank and Tom is not answering from inside the tank',
    'the crew got no notification and they started the line with Luis still working on it',
    'the buggy rolled on top of him',
    'a guy is stuck at the loading dock between the trailer and the wall',
    'his arm is stuck on the loading conveyor',
    'I need help with the app',
  ])('%p', async (q) => {
    await openChat();
    await say(q);
    expect(screen.getByText(BANNER)).toBeTruthy();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(sentToModel()[0]).toContain(q);
    noSupportPath();
    expect(file).not.toHaveBeenCalled();
  });
});

describe('"report an issue" followed by a hazard is never filed as an app report', () => {
  it('shows how to report an app problem, says who a report goes to, and holds a hazard typed as the description', async () => {
    await openChat();
    await say('I want to report an issue');
    expect(screen.getByText(/^How to report a problem and see the reply\s/)).toBeTruthy();
    expect(sentToModel()).toHaveLength(0);
    await tap('Report a problem with the app'); // the small link under the entry
    expect(screen.getByText(GOES_TO)).toBeTruthy();
    await tap('OK');
    await say('forklift 3 has no brakes and they are still using it');
    expect(screen.getByText(ON_HOLD)).toBeTruthy();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(sentToModel()[0]).toContain('forklift 3 has no brakes');
    await tap('Cancel');
    expect(file).not.toHaveBeenCalled();
  });

  it('typed in one message, the hazard goes straight to the safety answer', async () => {
    await openChat();
    await say('I want to report an issue. There is a spill in aisle 4');
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    noSupportPath();
  });
});

describe('a report waiting for its description or an email', () => {
  it('an emergency the rail catches is never the description: banner, on hold, safety answer, nothing filed', async () => {
    await openChat();
    await say('the app keeps crashing');
    await tap('Report this problem');
    await tap('OK');
    await say('a rack came down on top of Mike');
    expect(screen.getAllByText(BANNER)).toHaveLength(1);
    expect(screen.getByText(ON_HOLD)).toBeTruthy();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    await say('his lips are blue');
    expect(screen.getAllByText(BANNER)).toHaveLength(2);
    await waitFor(() => expect(sentToModel()).toHaveLength(2));
    expect(file).not.toHaveBeenCalled();
  });

  it('a question typed where the email goes is answered, not taken as a bad email', async () => {
    await openChat();
    await say('the app keeps crashing');
    await tap('Report this problem');
    await tap('OK');
    await say('the app keeps crashing when I open a talk');
    await say('how do I lock out the mixer');
    expect(screen.queryByText('Check the email address, or tap Skip.')).toBeNull();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(file).not.toHaveBeenCalled();
  });

  it('says when it put a saved email in the box', async () => {
    (getAccount as jest.Mock).mockResolvedValue({ state: 'in', name: 'Sam', email: 'sam@example.com' });
    await openChat();
    await say('the app keeps crashing');
    await tap('Report this problem');
    await tap('OK');
    await say('it closes when I open a talk');
    expect(box().props.value).toBe('sam@example.com');
    expect(screen.getByText('Want a reply? I put your email in the box. Send to include it, or tap Skip to send without one.')).toBeTruthy();
  });

  it('a report left alone for more than five minutes is dropped, so a later "yes" is not taken as an answer to it', async () => {
    const now = jest.spyOn(Date, 'now');
    now.mockReturnValue(1_000_000);
    await openChat();
    await say('the app keeps crashing');
    now.mockReturnValue(1_000_000 + 6 * 60 * 1000);
    await say('yes');
    expect(screen.queryByText(GOES_TO)).toBeNull();
    expect(file).not.toHaveBeenCalled();
  });
});

describe('after an entry, the offer reads the way people answer it', () => {
  it('"no it still crashes" goes on to the report, "yes" too', async () => {
    await openChat();
    await say('the app keeps crashing');
    await say('no it still crashes');
    expect(screen.getByText(GOES_TO)).toBeTruthy();
  });
});

describe('app questions reach their entry, safety questions about screens and sheets do not', () => {
  test.each([
    ['how do I find past talks', 'Finding past talks'],
    ['the talk is locked', 'A talk is locked or not there yet'],
    ['delete my data', 'Deleting your data'],
    ['turn off crash reports', 'What a crash report sends and how to turn it off'],
    ['no hay espanol', 'Spanish is not offered'],
  ])('%p shows %p word for word, with no model', async (q, title) => {
    await openChat();
    await say(q);
    expect(screen.getByText(new RegExp(`^${title}\\s`))).toBeTruthy();
    expect(sentToModel()).toHaveLength(0);
  });

  test.each(['the gas monitor screen is blank, can I still enter the tank?', 'the inspection sheet is blank, do I still need to sign it', 'we did not get notification of the lockout before they started work'])(
    '%p gets the safety answer',
    async (q) => {
      await openChat();
      await say(q);
      await waitFor(() => expect(sentToModel()).toHaveLength(1));
      noSupportPath();
    },
  );
});

describe('the 911 line on a support reply, with the served entries, in English and Spanish', () => {
  const EN = 'If anyone is hurt or in danger, call 911 now.';
  const ES = 'Si alguien está herido o en peligro, llame al 911 ahora.';
  test.each([
    // [message, the line it must carry, the entry shown under it]
    ['the app keeps crashing', EN, 'The app closed, crashed or froze'],
    ['how do I find past talks', EN, 'Finding past talks'],
    ['la app se cierra sola', ES, 'The app closed, crashed or froze'],
    ['como cambio el idioma', ES, 'Spanish is not offered'],
  ])('%p: the line, then the entry', async (q, line, title) => {
    await openChat();
    await say(q);
    expect(screen.getAllByText(line)).toHaveLength(1);
    expect(screen.queryByText(line === EN ? ES : EN)).toBeNull();
    expect(screen.getByText(new RegExp(`^${title}\\s`))).toBeTruthy();
    expect(screen.queryByText(BANNER)).toBeNull();
    expect(sentToModel()).toHaveLength(0);
  });

  it('a Spanish "sigue igual" at the offer carries it too, before the line about who the report goes to', async () => {
    await openChat();
    await say('la app se cierra sola');
    await say('sigue igual');
    expect(screen.getAllByText(ES)).toHaveLength(2);
    expect(screen.getByText(/^Esto va a Trainovate/)).toBeTruthy();
  });

  it('"otis se traba", short Spanish the language check reads as English: the line in both languages, then the entry', async () => {
    await openChat();
    await say('otis se traba');
    expect(screen.getAllByText(`${EN}\n${ES}`)).toHaveLength(1);
    expect(screen.getByText(/^The app closed, crashed or froze\s/)).toBeTruthy();
    expect(screen.queryByText(BANNER)).toBeNull();
  });

  test.each(['otis 2 down', 'otis 1 esta pegado', 'the app is stuck and so is 1 of mine', 'otis i dont know where i am', 'otis what do i do now', 'otis entro y ya no contesta'])(
    'round 4, %p: the banner and the safety answer, no support entry and no 911 line',
    async (q) => {
      await openChat();
      await say(q);
      expect(screen.getByText(BANNER)).toBeTruthy();
      expect(screen.queryByText(EN)).toBeNull();
      noSupportPath();
    },
  );

  test.each(['otis can i run it now', 'otis its 108 today', 'otis puedo entrar', 'otis do i have to give my name'])(
    'round 4, %p: the safety answer, no support entry',
    async (q) => {
      await openChat();
      await say(q);
      await waitFor(() => expect(sentToModel()).toHaveLength(1));
      noSupportPath();
      expect(screen.queryByText(EN)).toBeNull();
    },
  );

  test.each(['app froze get me out', 'la app se cerro y el no sale', 'the app froze and it shut on me'])(
    '%p: the banner and the safety answer, never the line on a support reply',
    async (q) => {
      await openChat();
      await say(q);
      expect(screen.getByText(BANNER)).toBeTruthy();
      expect(screen.queryByText(EN)).toBeNull();
      expect(screen.queryByText(ES)).toBeNull();
      noSupportPath();
    },
  );
});

describe('the privacy line on the set-up screen matches what can leave the phone', () => {
  it('names the two ways a question can leave, and no longer says it never does', async () => {
    mockStore.delete('otis_downloaded_model');
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText('Meet OTIS')).toBeTruthy());
    expect(
      screen.getByText(
        'OTIS runs on this phone and works with no signal once it is set up. What you ask stays on this phone unless you choose to report a problem or an answer, or turn on Include my question in Settings.',
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/never leave/)).toBeNull();
  });
});

describe('the pure-app gate on the screen: a message that is not only about the app gets the safety answer', () => {
  it('"the app froze and the floor is slippery": the safety answer from the model, with the Report a problem link, no offer', async () => {
    await openChat();
    await say('the app froze and the floor is slippery');
    expect(screen.queryByText(BANNER)).toBeNull();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    noSupportPath();
    expect(screen.getByLabelText('Report a problem with the app')).toBeTruthy();
    expect(file).not.toHaveBeenCalled();
  });

  test.each(['app froze and mike is not moving', 'la app se cerró y me torcí el tobillo, no puedo caminar', 'app crashd and hes bleding bad'])(
    '%p: banner, then the safety answer, no support path',
    async (q) => {
      await openChat();
      await say(q);
      expect(screen.getByText(BANNER)).toBeTruthy();
      await waitFor(() => expect(sentToModel()).toHaveLength(1));
      noSupportPath();
      expect(file).not.toHaveBeenCalled();
    },
  );

  it('at the offer, "still crashing and mike is not moving" is not "the fix did not help"', async () => {
    await openChat();
    await say('the app keeps crashing');
    await say('still crashing and mike is not moving');
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.queryByText(GOES_TO)).toBeNull();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(file).not.toHaveBeenCalled();
  });

  it('"wet floor" typed where the email goes is answered, not met with "Check the email address"', async () => {
    await openChat();
    await say('the app keeps crashing');
    await tap('Report this problem');
    await tap('OK');
    await say('the app keeps crashing when I open a talk');
    await say('wet floor');
    expect(screen.queryByText('Check the email address, or tap Skip.')).toBeNull();
    expect(screen.getByText(ON_HOLD)).toBeTruthy();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(file).not.toHaveBeenCalled();
  });
});
