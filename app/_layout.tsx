import { Barlow_400Regular, Barlow_500Medium, Barlow_600SemiBold } from '@expo-google-fonts/barlow';
import { BarlowCondensed_600SemiBold, BarlowCondensed_700Bold } from '@expo-google-fonts/barlow-condensed';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, type ErrorBoundaryProps, Stack, ThemeProvider, usePathname } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useCallback, useEffect, useState } from 'react';
import { AppState, useColorScheme, View } from 'react-native';
import 'react-native-reanimated';

import { CrashScreen } from '@/components/CrashScreen';
import { HolidaySplash } from '@/components/Holiday';
import { HowTo } from '@/components/HowTo';
import { IntroSplash } from '@/components/IntroSplash';
import { Welcome } from '@/components/Welcome';
import { fonts, themes } from '@/constants/theme';
import { firstRun, flushAccount, markHowToDone, whatToShow } from '@/lib/account';
import { startLive } from '@/lib/live';
import { flushVotes } from '@/lib/monday';
import { startPush } from '@/lib/push';
import { isHoliday, refreshSeason } from '@/lib/season';
import { flushSheets } from '@/lib/sheets';
import { flushCrashes, installCrashReporter, noteScreen } from '@/lib/support/crash';
import { flushReports } from '@/lib/support/reports';
import { reportOpen } from '@/lib/usage';

// Before anything else runs, so an error while the app is still starting is caught too.
installCrashReporter();

/**
 * Shown in place of the whole app when the layout itself throws (a font that will not load, say). It is drawn above
 * the navigator, so it stands on its own: see CrashScreen.
 */
export function ErrorBoundary(props: ErrorBoundaryProps) {
  return <CrashScreen {...props} />;
}

// screenErrorBoundary: when one screen throws, only that screen shows the error. The header, the back button and the
// tabs stay, so the person can leave it and the rest of the app keeps working.
export const unstable_settings = { anchor: '(tabs)', screenErrorBoundary: ErrorBoundary };

SplashScreen.preventAutoHideAsync();

// "Try again" on the error screen draws the layout afresh. The opening screen has had its turn by then.
let openingPlayed = false;

export default function RootLayout() {
  const scheme = useColorScheme();
  // One opening screen per cold start, decided by the date when the app opens: the holiday screen in December,
  // the footage intro the rest of the year. null once it has played.
  const [opening, setOpening] = useState<'holiday' | 'intro' | null>(() => (openingPlayed ? null : isHoliday() ? 'holiday' : 'intro'));
  const closeOpening = useCallback(() => {
    openingPlayed = true;
    setOpening(null);
  }, []);
  // The welcome sign-in and the how-to show once, on the first open. Read before the first frame so the tabs never flash.
  const [first, setFirst] = useState(firstRun);
  const closeWelcome = useCallback(() => setFirst((f) => ({ ...f, welcomeDone: true })), []);
  const closeHowTo = useCallback(() => {
    setFirst({ welcomeDone: true, howToDone: true });
    markHowToDone().catch(() => {});
  }, []);
  const [loaded, error] = useFonts({
    Barlow_400Regular,
    Barlow_500Medium,
    Barlow_600SemiBold,
    BarlowCondensed_600SemiBold,
    BarlowCondensed_700Bold,
  });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  // A crash report says which screen the person was on. The route only, never what is after a "?".
  const pathname = usePathname();
  useEffect(() => {
    noteScreen(pathname);
  }, [pathname]);

  // The root view sits behind every screen (transitions, keyboard): match it to the theme, not app.json's splash yellow.
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(themes[scheme === 'dark' ? 'dark' : 'light'].background);
  }, [scheme]);

  useEffect(() => {
    startPush();
    startLive(); // reload lists when new talks, alerts or episodes are published
    // Sheets, votes, a sign-up, problem reports and crash reports saved with no signal go out now, and again each time
    // the app comes back to the front: people walk from a dead spot on the floor to the break room with the phone in
    // their pocket.
    const flush = () => {
      flushSheets();
      flushVotes();
      flushAccount();
      flushReports();
      flushCrashes();
      refreshSeason();
      reportOpen();
    };
    flush();
    const sub = AppState.addEventListener('change', (state) => state === 'active' && flush());
    return () => sub.remove();
  }, []);

  // The footage intro hides the native launch screen itself, once its first frame is drawn (see IntroSplash).
  // Every other opening hands over as soon as the fonts are in.
  useEffect(() => {
    if (loaded && opening !== 'intro') SplashScreen.hideAsync();
  }, [loaded, opening]);

  // Stable, so a re-render during the intro (e.g. a dark-mode switch) hands IntroSplash the same function.
  const hideSplash = useCallback(() => {
    SplashScreen.hideAsync();
  }, []);

  if (!loaded) return null;

  // The opening screen plays alone. What comes next waits under it, out of reach of taps and screen readers,
  // so the opening fades straight into it. A returning person has nothing waiting and lands on the Monday tab.
  const next = whatToShow({ ...first, opening: false });
  const covered = whatToShow({ ...first, opening: opening !== null }) === 'opening';
  const firstRunUp = next !== 'app';

  return (
    <View style={{ flex: 1 }}>
    <View style={{ flex: 1 }} accessibilityElementsHidden={firstRunUp} importantForAccessibility={firstRunUp ? 'no-hide-descendants' : 'auto'}>
    <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack screenOptions={{ headerTitleStyle: { fontFamily: fonts.displayMedium }, headerBackButtonDisplayMode: 'minimal' }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="talk/[issue]" options={{ title: 'Toolbox talk' }} />
        <Stack.Screen name="monday/index" options={{ title: 'Monday Minute' }} />
        <Stack.Screen name="monday/[id]" options={{ title: 'Monday Minute' }} />
        <Stack.Screen name="sheets" options={{ title: 'My sign-in sheets' }} />
        <Stack.Screen name="signin/[session]" options={{ title: 'Crew sign-in' }} />
        <Stack.Screen name="archive" options={{ title: 'Archive' }} />
        <Stack.Screen name="suggest" options={{ title: 'Suggest a talk' }} />
        <Stack.Screen name="otis" options={{ title: 'OTIS' }} />
        <Stack.Screen name="zero-hour/index" options={{ title: 'Zero Hour' }} />
        <Stack.Screen name="zero-hour/[n]" options={{ title: 'Zero Hour' }} />
        <Stack.Screen name="alerts" options={{ title: 'Regulatory alerts' }} />
        <Stack.Screen name="alert/[id]" options={{ title: 'Regulatory alert' }} />
        <Stack.Screen name="how-to" options={{ title: 'How to use Zero Harm' }} />
        <Stack.Screen name="report" options={{ title: 'Report a problem' }} />
        <Stack.Screen name="my-reports" options={{ title: 'My reports' }} />
        <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
      </Stack>
    </ThemeProvider>
    </View>
    {next === 'welcome' && <Welcome onDone={closeWelcome} covered={covered} />}
    {next === 'howto' && <HowTo cover onDone={closeHowTo} covered={covered} />}
    {opening === 'holiday' && <HolidaySplash onDone={closeOpening} />}
    {opening === 'intro' && <IntroSplash onReady={hideSplash} onDone={closeOpening} />}
    </View>
  );
}
