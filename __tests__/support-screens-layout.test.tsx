import { act, render, screen } from '@testing-library/react-native';
import { AppState, type AppStateStatus } from 'react-native';

import RootLayout, { ErrorBoundary, unstable_settings } from '@/app/_layout';
import { flushCrashes, installCrashReporter, noteScreen } from '@/lib/support/crash';
import { flushReports } from '@/lib/support/reports';

// Everything the layout draws or starts is replaced by a stand-in: this file checks the wiring, not the screens.
jest.mock('@expo-google-fonts/barlow', () => ({}));
jest.mock('@expo-google-fonts/barlow-condensed', () => ({}));
jest.mock('expo-font', () => ({ useFonts: () => [true, null] }));
jest.mock('expo-splash-screen', () => ({ preventAutoHideAsync: jest.fn(), hideAsync: jest.fn() }));
jest.mock('expo-system-ui', () => ({ setBackgroundColorAsync: jest.fn() }));
jest.mock('react-native-reanimated', () => ({}));
const mockRoute = { path: '/' };
jest.mock('expo-router', () => {
  const { Text } = jest.requireActual('react-native');
  const Stack = ({ children }: { children: unknown }) => children;
  Stack.Screen = ({ name, options }: { name: string; options?: { title?: string } }) => <Text>{`${name} = ${options?.title ?? ''}`}</Text>;
  return { DarkTheme: {}, DefaultTheme: {}, ThemeProvider: ({ children }: { children: unknown }) => children, Stack, usePathname: () => mockRoute.path };
});
jest.mock('@/components/CrashScreen', () => {
  const { Text } = jest.requireActual('react-native');
  return { CrashScreen: ({ error }: { error: Error }) => <Text>{`crash screen: ${error.message}`}</Text> };
});
jest.mock('@/components/Holiday', () => ({ HolidaySplash: () => null }));
jest.mock('@/components/HowTo', () => ({ HowTo: () => null }));
jest.mock('@/components/IntroSplash', () => ({ IntroSplash: () => null }));
jest.mock('@/components/Welcome', () => ({ Welcome: () => null }));
jest.mock('@/lib/account', () => ({
  firstRun: () => ({ welcomeDone: true, howToDone: true }),
  flushAccount: jest.fn(),
  markHowToDone: jest.fn(),
  whatToShow: ({ opening }: { opening: boolean }) => (opening ? 'opening' : 'app'),
}));
jest.mock('@/lib/live', () => ({ startLive: jest.fn() }));
jest.mock('@/lib/monday', () => ({ flushVotes: jest.fn() }));
jest.mock('@/lib/push', () => ({ startPush: jest.fn() }));
jest.mock('@/lib/season', () => ({ isHoliday: () => false, refreshSeason: jest.fn() }));
jest.mock('@/lib/sheets', () => ({ flushSheets: jest.fn() }));
jest.mock('@/lib/usage', () => ({ reportOpen: jest.fn() }));
jest.mock('@/lib/support/crash', () => ({ installCrashReporter: jest.fn(), flushCrashes: jest.fn(), noteScreen: jest.fn() }));
jest.mock('@/lib/support/reports', () => ({ flushReports: jest.fn() }));

// Counted here, before any test draws anything: the crash reporter has to be in place before the first screen.
const installedOnLoad = (installCrashReporter as jest.Mock).mock.calls.length;

let onAppState: (state: AppStateStatus) => void = () => {};
beforeEach(() => {
  mockRoute.path = '/';
  for (const fn of [flushCrashes, flushReports, noteScreen]) (fn as jest.Mock).mockClear();
  jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, handler) => {
    onAppState = handler as (state: AppStateStatus) => void;
    return { remove: jest.fn() } as unknown as ReturnType<typeof AppState.addEventListener>;
  });
});
afterEach(() => jest.restoreAllMocks());

describe('the root layout', () => {
  it('starts the crash reporter once, when the app loads, before anything is drawn', () => {
    expect(installedOnLoad).toBe(1);
  });

  it('sends waiting problem reports and crash reports at launch and each time the app comes back to the front', async () => {
    await render(<RootLayout />);
    expect(flushReports).toHaveBeenCalledTimes(1);
    expect(flushCrashes).toHaveBeenCalledTimes(1);
    await act(async () => onAppState('background'));
    expect(flushReports).toHaveBeenCalledTimes(1);
    await act(async () => onAppState('active'));
    expect(flushReports).toHaveBeenCalledTimes(2);
    expect(flushCrashes).toHaveBeenCalledTimes(2);
  });

  it('tells the crash reporter which screen is showing, and again when it changes', async () => {
    const drawn = await render(<RootLayout />);
    expect(noteScreen).toHaveBeenLastCalledWith('/');
    mockRoute.path = '/talk/12';
    await drawn.rerender(<RootLayout />);
    expect(noteScreen).toHaveBeenLastCalledWith('/talk/12');
  });

  it('registers the two new screens with their titles', async () => {
    await render(<RootLayout />);
    expect(screen.getByText('report = Report a problem')).toBeTruthy();
    expect(screen.getByText('my-reports = My reports')).toBeTruthy();
  });

  it('its error screen is the app’s own crash screen, for the whole app and for a single screen', async () => {
    expect(unstable_settings.screenErrorBoundary).toBe(ErrorBoundary);
    await render(<ErrorBoundary error={new Error('fonts did not load')} retry={() => Promise.resolve()} />);
    expect(screen.getByText('crash screen: fonts did not load')).toBeTruthy();
  });
});
