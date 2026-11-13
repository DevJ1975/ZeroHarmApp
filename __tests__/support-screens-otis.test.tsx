import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import OtisScreen from '@/app/otis';
import { getAccount } from '@/lib/account';
import { api } from '@/lib/config';
import { loadKb, type KbItem } from '@/lib/otis/kb';
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

const entry = (id: string, title: string, text: string, tags: string, kind?: 'support'): KbItem => ({
  id,
  title,
  text,
  tags,
  lang: 'en',
  issue: null,
  source: kind ? 'Zero Harm app help' : 'Zero Harm knowledge base',
  ...(kind ? { kind } : {}),
});
const CRASH_FIX = entry('k90', 'The app closes or crashes', '1. Close Zero Harm all the way.\n2. Open it again.\n3. If it still closes, update the app.', 'crash crashed crashing closes closing', 'support');
const WHAT_IS_OTIS = entry('k91', 'What is OTIS', 'OTIS is the safety assistant in Zero Harm. It runs on this phone.', 'otis assistant', 'support');
const PAST_TALKS = entry('k92', 'Find past talks', '1. Open the Today tab.\n2. Tap Archive.', 'archive past old talks find', 'support');
const LOCKOUT = entry('k1', 'Lockout: who takes off a lock', 'Only the worker who put a lock on may take that lock off.', 'lockout lock tagout');
const BLEEDING = entry('k2', 'First aid for bleeding', 'Press firmly on the wound with a clean cloth. Call 911 for heavy bleeding.', 'bleeding blood wound');
const KB = [LOCKOUT, BLEEDING, CRASH_FIX, WHAT_IS_OTIS, PAST_TALKS];

const BANNER = 'If someone is hurt or in danger right now, call 911 first.';
const CONFIRM =
  'A report sends Trainovate what you write, your email if you give one, your phone model (iPhone 15, iOS 18.1), the app version (1.0.0) and a random id for this app, so you can see your reports later. Nothing else. Your chat with OTIS is not sent. OK?';
const ON_HOLD = 'Your report is on hold. Nothing was sent. If your message was about the app, open Settings and tap Report a problem.';
const GOES_TO = 'This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.';
const OFFER = 'If that did not fix it, want me to send a report to Trainovate, who make the app?';
const LONG_CHAT = 'Long chats slow OTIS down on a phone. Tap New chat to start fresh.';
const ANSWER = 'Only the person who put the lock on can take it off [1].';
const CRASHING = 'the app keeps crashing';

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
  await act(async () => {}); // the knowledge base and the saved email load
}
/** What reached the model: the text of every turn sent to it. */
const sentToModel = () => mockLlm.sendMessage.mock.calls.map((c) => c[0] as string);
/** Asserts that nothing typed in this chat has left the phone by any road. */
function nothingLeftThePhone() {
  expect(file).not.toHaveBeenCalled();
  expect(flag).not.toHaveBeenCalled();
  expect(api).not.toHaveBeenCalled();
  expect(fetchSpy).not.toHaveBeenCalled();
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

// ---- Safety answers: unchanged ------------------------------------------------------------------------

describe('a safety question still goes to the model on the phone, with safety sources only', () => {
  it('answers from the safety entries and never hands the model a support entry', async () => {
    await openChat();
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText(ANSWER)).toBeTruthy());
    expect(sentToModel()).toHaveLength(1);
    expect(sentToModel()[0]).toContain('Only the worker who put a lock on may take that lock off.');
    for (const support of [CRASH_FIX, WHAT_IS_OTIS, PAST_TALKS]) expect(sentToModel()[0]).not.toContain(support.text);
    nothingLeftThePhone();
  });

  it('a question nothing covers gets the usual line, and the model is not asked', async () => {
    await openChat();
    await say('What is the capital of France?');
    expect(screen.getByText("I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead.")).toBeTruthy();
    expect(sentToModel()).toHaveLength(0);
    nothingLeftThePhone();
  });
});

// ---- The 911 rail -------------------------------------------------------------------------------------

describe('the 911 banner comes first, as before', () => {
  it('shows on an emergency message and the safety answer still follows', async () => {
    await openChat();
    await say('He is bleeding badly, what do I do');
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Call 911' })).toBeTruthy();
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(sentToModel()[0]).toContain('Press firmly on the wound');
  });

  it('shows even when the message is also about the app', async () => {
    await openChat();
    await say("the app crashed and he's not breathing");
    expect(screen.getByText(BANNER)).toBeTruthy();
    nothingLeftThePhone();
  });

  it('an emergency message typed in the middle of a report puts the report on hold: banner, nothing filed, not taken as the description', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    expect(box().props.value).toBe(CRASHING); // the describe step, with their words in the box
    await say('He is bleeding badly, what do I do');

    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.getByText(ON_HOLD)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Go on with the report' })).toBeTruthy();
    // It was not taken as the description: the flow did not move on to the email step.
    expect(screen.queryByText('Want a reply? Type your email. Or tap Skip to send without one.')).toBeNull();
    expect(file).not.toHaveBeenCalled();
    // And it still gets its safety answer, exactly as it would outside a report.
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(sentToModel()[0]).toContain('Press firmly on the wound');
    nothingLeftThePhone();
  });

  it('while a report is on hold, what is typed is a question for OTIS, never part of the report', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say('He is bleeding badly, what do I do');
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    await say('Who can take off a lock?');
    await waitFor(() => expect(sentToModel()).toHaveLength(2));
    expect(sentToModel()[1]).toContain('Only the worker who put a lock on');
    expect(screen.queryByText(/Want a reply\?/)).toBeNull();
    nothingLeftThePhone();
  });

  it('"Go on with the report" picks it up where it stopped, and it can then be sent', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say('He is bleeding badly, what do I do');
    await tap('Go on with the report');
    expect(box().props.value).toBe(CRASHING);
    await say(`${CRASHING} when I open a talk`);
    await tap('Skip');
    await waitFor(() => expect(screen.getByText('Reported. Your reference is ZH-7.')).toBeTruthy());
    expect(file).toHaveBeenCalledTimes(1);
    expect(file).toHaveBeenCalledWith({ text: `${CRASHING} when I open a talk`, source: 'otis', lang: 'en' });
  });
});

// ---- Tech support answers -----------------------------------------------------------------------------

describe('a problem with the app is answered from the support entries, word for word', () => {
  it('shows the entry exactly as written and never asks the model', async () => {
    await openChat();
    await say(CRASHING);
    expect(screen.getByText(`${CRASH_FIX.title}\n\n${CRASH_FIX.text}`)).toBeTruthy();
    expect(screen.getByText(OFFER)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Report this problem' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'That fixed it' })).toBeTruthy();
    expect(sentToModel()).toHaveLength(0);
    nothingLeftThePhone();
  });

  it('"That fixed it" ends it there and sends nothing', async () => {
    await openChat();
    await say(CRASHING);
    await tap('That fixed it');
    expect(screen.getByText('Good. Glad that helped.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Report this problem' })).toBeNull(); // old buttons are gone
    nothingLeftThePhone();
  });

  it('with no matching entry it offers to report straight away', async () => {
    await openChat();
    await say('the app is broken');
    expect(screen.getByText("I don't have a fix for that yet. If this is a problem with the Zero Harm app, I can send a report to Trainovate, who make the app.")).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Report this problem' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'No thanks' })).toBeTruthy();
    expect(sentToModel()).toHaveLength(0);
    nothingLeftThePhone();
  });

  it('a plain question about the app shows its entry word for word, with no report buttons and no model', async () => {
    await openChat();
    await say('What is OTIS?');
    expect(screen.getByText(`${WHAT_IS_OTIS.title}\n\n${WHAT_IS_OTIS.text}`)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Report this problem' })).toBeNull();
    expect(sentToModel()).toHaveLength(0);
  });

  it('when the safety search finds nothing, a support entry that fits is shown before giving up', async () => {
    await openChat();
    await say('how do I find past talks');
    expect(screen.getByText(`${PAST_TALKS.title}\n\n${PAST_TALKS.text}`)).toBeTruthy();
    expect(screen.queryByText(/I don't have that in my Zero Harm knowledge base/)).toBeNull();
    expect(sentToModel()).toHaveLength(0);
  });

  it('a safety question that only sounds like a report stays with the safety answers', async () => {
    await openChat();
    await say('The lock on the machine is broken, who can take it off?');
    await waitFor(() => expect(sentToModel()).toHaveLength(1));
    expect(screen.queryByRole('button', { name: 'Report this problem' })).toBeNull();
  });
});

// ---- The 911 line on support replies -------------------------------------------------------------------

const CALL_LINE = 'If anyone is hurt or in danger, call 911 now.';
const LINE_ES = 'Si alguien está herido o en peligro, llame al 911 ahora.';

describe('every support reply shown in place of the safety answer starts with the one 911 line', () => {
  it('on the problem path: the line, then the entry word for word, then the offer', async () => {
    await openChat();
    await say(CRASHING);
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(1);
    // The entry is still shown exactly as written, in its own text, under the line.
    expect(screen.getByText(`${CRASH_FIX.title}\n\n${CRASH_FIX.text}`)).toBeTruthy();
    expect(screen.getByText(OFFER)).toBeTruthy();
    // Calm: it is not the red banner and brings no Call 911 button.
    expect(screen.queryByText(BANNER)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Call 911' })).toBeNull();
  });

  it('on the offer to report when no entry matches', async () => {
    await openChat();
    await say('the app is broken');
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(1);
    expect(screen.getByText(/^I don't have a fix for that yet/)).toBeTruthy();
  });

  it('on a help entry', async () => {
    await openChat();
    await say('What is OTIS?');
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(1);
    expect(screen.getByText(`${WHAT_IS_OTIS.title}\n\n${WHAT_IS_OTIS.text}`)).toBeTruthy();
  });

  it('on the report taken up from a typed "still broken", with the line about who it goes to still before sending', async () => {
    await openChat();
    await say(CRASHING);
    await say('no it still crashes');
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(2);
    expect(screen.getByText(GOES_TO)).toBeTruthy();
    expect(screen.getByText(CONFIRM)).toBeTruthy();
  });

  it('not on the confirm step reached by tapping Report this problem: nothing typed was taken there', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(1); // the one on the entry
    expect(screen.getByText(GOES_TO)).toBeTruthy();
  });

  it('not on a safety answer, and not under the 911 banner, which already says it', async () => {
    await openChat();
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText(ANSWER)).toBeTruthy());
    await say("the app crashed and he's not breathing");
    expect(screen.getByText(BANNER)).toBeTruthy();
    expect(screen.queryByText(CALL_LINE)).toBeNull();
  });

  it('is not part of what "Report this answer" sends: the entry goes word for word', async () => {
    jest.spyOn(Alert, 'alert').mockImplementation((_t, _b, buttons) => buttons?.[1]?.onPress?.());
    await openChat();
    await say('What is OTIS?');
    await tap('Report this answer');
    await waitFor(() => expect(flag).toHaveBeenCalledTimes(1));
    expect(flag.mock.calls[0][0]).toMatchObject({ answer: `${WHAT_IS_OTIS.title}\n\n${WHAT_IS_OTIS.text}` });
  });

  it('in Spanish, for a Spanish message', async () => {
    await openChat();
    await say('la app se cierra sola');
    expect(screen.getAllByText(LINE_ES)).toHaveLength(1);
    expect(screen.queryByText(CALL_LINE)).toBeNull();
  });

  it('in both languages for a short Spanish message the language check reads as English', async () => {
    await openChat();
    await say('otis se traba');
    expect(screen.getAllByText(`${CALL_LINE}\n${LINE_ES}`)).toHaveLength(1);
    expect(screen.queryByText(BANNER)).toBeNull();
  });

  it('on the email step, when a description was typed at the describe step (it was taken in place of a question)', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say('it closes every time i open a talk');
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(2);
    expect(screen.getByText('Want a reply? Type your email. Or tap Skip to send without one.')).toBeTruthy();
    nothingLeftThePhone();
  });

  it('not on the email step when the first message, put in the box, is sent as it is', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say(CRASHING);
    expect(screen.getAllByText(CALL_LINE)).toHaveLength(1); // the one on the entry
    expect(screen.getByText('Want a reply? Type your email. Or tap Skip to send without one.')).toBeTruthy();
  });

  it('a description that names nothing of the app and says nothing only software does is held, not taken', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say('i left it running');
    expect(screen.getByText('Your report is on hold. Nothing was sent. If your message was about the app, open Settings and tap Report a problem.')).toBeTruthy();
    expect(screen.queryByText('Want a reply? Type your email. Or tap Skip to send without one.')).toBeNull();
    nothingLeftThePhone();
  });
});

// ---- The report flow ----------------------------------------------------------------------------------

describe('reporting a problem from the chat', () => {
  it('the confirm step says exactly what is sent, and nothing is sent before the person finishes', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    expect(screen.getByText(GOES_TO)).toBeTruthy(); // who it goes to, before anything is sent
    expect(screen.getByText(CONFIRM)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'OK' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy();
    nothingLeftThePhone();

    await tap('OK');
    expect(screen.getByText('What went wrong with the app? I put what you typed in the box. Change it or add to it, then send. Leave out names.')).toBeTruthy();
    expect(box().props.value).toBe(CRASHING);
    nothingLeftThePhone();

    await say(`${CRASHING} on the Today tab`);
    expect(screen.getByText('Want a reply? Type your email. Or tap Skip to send without one.')).toBeTruthy();
    expect(box().props.keyboardType).toBe('email-address');
    nothingLeftThePhone();

    await tap('Skip');
    await waitFor(() => expect(screen.getByText('Reported. Your reference is ZH-7.')).toBeTruthy());
    // Exactly the description the person sent. No chat, no email, no earlier messages.
    expect(file).toHaveBeenCalledTimes(1);
    expect(file).toHaveBeenCalledWith({ text: `${CRASHING} on the Today tab`, source: 'otis', lang: 'en' });
    expect(sentToModel()).toHaveLength(0);
    expect(box().props.keyboardType).toBe('default');
  });

  it('"Cancel" at the confirm step sends nothing', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('Cancel');
    expect(screen.getByText('OK. Nothing was sent.')).toBeTruthy();
    nothingLeftThePhone();
  });

  it('a typed email goes with the report as the address to reply to', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say(CRASHING);
    await say('Maria@Example.com');
    await waitFor(() => expect(file).toHaveBeenCalledTimes(1));
    expect(file).toHaveBeenCalledWith({ text: CRASHING, source: 'otis', lang: 'en', email: 'maria@example.com', may_contact: true });
  });

  it('an email already on the phone is offered in the box, and is only sent if the person sends it', async () => {
    (getAccount as jest.Mock).mockResolvedValue({ state: 'in', name: 'Maria Lopez', email: 'maria@example.com' });
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say(CRASHING);
    expect(box().props.value).toBe('maria@example.com');
    await tap('Skip');
    await waitFor(() => expect(file).toHaveBeenCalledTimes(1));
    expect(file).toHaveBeenCalledWith({ text: CRASHING, source: 'otis', lang: 'en' });
  });

  it('with no signal it says the report is saved on the phone', async () => {
    file.mockResolvedValue({ ref: 'p-1', queued: true });
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    await tap('OK');
    await say(CRASHING);
    await tap('Skip');
    await waitFor(() => expect(screen.getByText('Saved on this phone. It will send when you have signal.')).toBeTruthy());
  });

  it('a safety question typed at the offer drops the report and is answered as a safety question', async () => {
    await openChat();
    await say(CRASHING);
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText(ANSWER)).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Report this problem' })).toBeNull();
    nothingLeftThePhone();
  });

  it('a report started in Spanish stays in Spanish', async () => {
    await openChat();
    await say('la aplicación no funciona');
    await tap('Reportar este problema');
    expect(screen.getByText(/Su conversación con OTIS no se envía\. ¿De acuerdo\?$/)).toBeTruthy();
    await tap('De acuerdo');
    await say('ok se cierra sola');
    await tap('Omitir');
    await waitFor(() => expect(screen.getByText('Reportado. Su referencia es ZH-7.')).toBeTruthy());
    expect(file).toHaveBeenCalledWith({ text: 'ok se cierra sola', source: 'otis', lang: 'es' });
  });

  it('the empty chat has a "Report a problem" control that starts at the confirm step', async () => {
    await openChat();
    await tap('Report a problem with the app');
    expect(screen.getByText(CONFIRM)).toBeTruthy();
    await tap('OK');
    expect(screen.getByText('What went wrong with the app? Tell me in a sentence or two. Leave out names.')).toBeTruthy();
    expect(box().props.value).toBe('');
    nothingLeftThePhone();
  });
});

// ---- The long-chat notice -----------------------------------------------------------------------------

describe('the long-chat notice counts questions for the model only', () => {
  it('support answers and report steps never bring it up', async () => {
    await openChat();
    for (let i = 0; i < 3; i++) {
      await say(CRASHING);
      await tap('Report this problem');
      await tap('OK');
      await say(`${CRASHING} again`);
      await tap('Skip');
      await waitFor(() => expect(file).toHaveBeenCalledTimes(i + 1));
    }
    await say('What is OTIS?');
    await say('how do I find past talks');
    expect(screen.queryByText(LONG_CHAT)).toBeNull(); // 11 typed messages, none of them for the model
    expect(sentToModel()).toHaveLength(0);
  });

  it('six safety questions still do', async () => {
    await openChat();
    for (let i = 0; i < 5; i++) await say('Who can take off a lock?');
    expect(screen.queryByText(LONG_CHAT)).toBeNull();
    await say('Who can take off a lock?');
    expect(screen.getByText(LONG_CHAT)).toBeTruthy();
  });
});

// ---- Report this answer -------------------------------------------------------------------------------

describe('"Report this answer"', () => {
  const confirm = async (button: 'Send' | 'Cancel' | 'Enviar') => {
    const [title, body, buttons] = (Alert.alert as jest.Mock).mock.calls.at(-1) as [string, string, { text: string; onPress?: () => Promise<void> }[]];
    await act(async () => {
      await buttons.find((b) => b.text === button)?.onPress?.();
    });
    return { title, body };
  };
  beforeEach(() => {
    jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  });

  it('is under a finished answer, asks first, and sends that one question and answer only on "Send"', async () => {
    await openChat();
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText(ANSWER)).toBeTruthy());
    await tap('Report this answer');
    expect(flag).not.toHaveBeenCalled(); // not before the person says yes
    const asked = await confirm('Send');
    expect(asked).toEqual({ title: 'Report this answer?', body: expect.stringContaining('your phone model, the system version, the app version and a random id') });
    expect(flag).toHaveBeenCalledTimes(1);
    expect(flag).toHaveBeenCalledWith({ question: 'Who can take off a lock?', answer: ANSWER, modelKey: 'qwen3-test', lang: 'en' });
    expect(screen.getByText('Sent. A person will review it.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Report this answer' })).toBeNull(); // once per answer
  });

  it('"Cancel" sends nothing', async () => {
    await openChat();
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText(ANSWER)).toBeTruthy());
    await tap('Report this answer');
    await confirm('Cancel');
    nothingLeftThePhone();
    expect(screen.getByRole('button', { name: 'Report this answer' })).toBeTruthy();
  });

  it('is there with "Help improve OTIS" off, and is not shown while the answer is still being written', async () => {
    let finish: () => void = () => {};
    mockLlm.sendMessage = jest.fn((_turn: string, onToken: (t: string) => void) => {
      onToken('Only the person');
      return new Promise<void>((done) => (finish = done));
    });
    await openChat();
    await fireEvent.changeText(box(), 'Who can take off a lock?');
    const asking = tap('Send'); // not waited on: the answer is still coming
    await waitFor(() => expect(screen.getByText('Only the person')).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Report this answer' })).toBeNull();
    await act(async () => finish());
    await asking;
    await waitFor(() => expect(screen.getByRole('button', { name: 'Report this answer' })).toBeTruthy());
    expect(screen.queryByText('Was this helpful?')).toBeNull();
  });

  it('is under a "not covered" reply too, and says no model wrote it', async () => {
    await openChat();
    await say('What is the capital of France?');
    await tap('Report this answer');
    await confirm('Send');
    expect(flag).toHaveBeenCalledWith({
      question: 'What is the capital of France?',
      answer: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead.",
      modelKey: 'no-model',
      lang: 'en',
    });
  });

  it('asks in Spanish under a Spanish answer, and says when it is saved for later', async () => {
    flag.mockResolvedValue({ ref: 'p-2', queued: true });
    await openChat();
    await say('¿Cuál es la capital de Francia?');
    await tap('Reportar esta respuesta');
    const asked = await confirm('Enviar');
    expect(asked.title).toBe('¿Reportar esta respuesta?');
    expect(flag).toHaveBeenCalledWith(expect.objectContaining({ lang: 'es', question: '¿Cuál es la capital de Francia?' }));
    expect(screen.getByText('Guardado en este teléfono. Se enviará cuando tenga señal.')).toBeTruthy();
  });

  it('is not put on the lines of a report in progress', async () => {
    await openChat();
    await say(CRASHING);
    await tap('Report this problem');
    expect(screen.queryByRole('button', { name: 'Report this answer' })).toBeNull();
  });
});

// ---- When OTIS cannot chat ----------------------------------------------------------------------------

describe('the way to Report a problem when OTIS cannot chat', () => {
  const link = () => screen.getByRole('link', { name: 'Report a problem with the app' });

  it('OTIS switched off', async () => {
    (getManifest as jest.Mock).mockResolvedValue({ enabled: false, update_required: false, message: '', model: MODEL, feedback_enabled: false });
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText('OTIS is taking a short break. Check back soon.')).toBeTruthy());
    await fireEvent.press(link());
    expect(router.push).toHaveBeenCalledWith('/report');
  });

  it('the app needs an update', async () => {
    (getManifest as jest.Mock).mockResolvedValue({ enabled: true, update_required: true, message: '', model: MODEL, feedback_enabled: false });
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText(/Update Zero Harm from the App Store or Google Play/)).toBeTruthy());
    await fireEvent.press(link());
    expect(router.push).toHaveBeenCalledWith('/report');
  });

  it('OTIS not set up yet', async () => {
    mockStore.delete('otis_downloaded_model');
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText('Meet OTIS')).toBeTruthy());
    await fireEvent.press(link());
    expect(router.push).toHaveBeenCalledWith('/report');
  });

  it('OTIS still downloading', async () => {
    mockLlm.isReady = false;
    mockLlm.downloadProgress = 0.4;
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText('Setting up OTIS… 40%')).toBeTruthy());
    await fireEvent.press(link());
    expect(router.push).toHaveBeenCalledWith('/report');
    expect(recordError).not.toHaveBeenCalled();
  });

  it('OTIS broken: the link is there and the failure is saved as a crash report', async () => {
    mockLlm.isReady = false;
    mockLlm.error = new Error('model file is damaged');
    await render(<OtisScreen />);
    await waitFor(() => expect(screen.getByText(/OTIS could not finish setting up/)).toBeTruthy());
    await fireEvent.press(link());
    expect(router.push).toHaveBeenCalledWith('/report');
    expect(recordError).toHaveBeenCalledWith(mockLlm.error, { fatal: false, screen: '/otis' });
  });

  it('when the model fails on an answer, the crash report holds the kind of error and never the question', async () => {
    mockLlm.sendMessage = jest.fn(async () => {
      throw new RangeError('could not answer: Who can take off a lock?');
    });
    await openChat();
    await say('Who can take off a lock?');
    await waitFor(() => expect(screen.getByText('Sorry, OTIS could not answer just now. Try again, or start a new chat.')).toBeTruthy());
    expect(recordError).toHaveBeenCalledTimes(1);
    expect(recordError).toHaveBeenCalledWith({ name: 'OtisAnswerError', message: 'RangeError' }, { fatal: false, screen: '/otis' });
    expect(JSON.stringify((recordError as jest.Mock).mock.calls)).not.toContain('lock');
  });
});
