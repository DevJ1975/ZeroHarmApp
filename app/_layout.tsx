import { Barlow_400Regular, Barlow_500Medium, Barlow_600SemiBold } from '@expo-google-fonts/barlow';
import { BarlowCondensed_600SemiBold, BarlowCondensed_700Bold } from '@expo-google-fonts/barlow-condensed';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import * as SystemUI from 'expo-system-ui';
import { useCallback, useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import 'react-native-reanimated';

import { IntroSplash } from '@/components/IntroSplash';
import { fonts, themes } from '@/constants/theme';
import { startLive } from '@/lib/live';
import { startPush } from '@/lib/push';
import { flushSheets } from '@/lib/sheets';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme();
  const [introDone, setIntroDone] = useState(false); // the footage intro plays once per cold start
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

  // The root view sits behind every screen (transitions, keyboard): match it to the theme, not app.json's splash yellow.
  useEffect(() => {
    SystemUI.setBackgroundColorAsync(themes[scheme === 'dark' ? 'dark' : 'light'].background);
  }, [scheme]);

  useEffect(() => {
    startPush();
    startLive(); // reload lists when new talks, alerts or episodes are published
    flushSheets(); // sheets saved with no signal go out now
  }, []);

  // The intro hides the native launch screen once its first frame is drawn (see IntroSplash); after the intro, nothing to do.
  const hideSplash = useCallback(() => {
    SplashScreen.hideAsync();
  }, []);

  // Stable, so a re-render during the intro (e.g. a dark-mode switch) hands IntroSplash the same function.
  const endIntro = useCallback(() => setIntroDone(true), []);

  if (!loaded) return null;

  return (
    <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack screenOptions={{ headerTitleStyle: { fontFamily: fonts.displayMedium }, headerBackButtonDisplayMode: 'minimal' }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="talk/[issue]" options={{ title: 'Toolbox talk' }} />
        <Stack.Screen name="signin/[session]" options={{ title: 'Crew sign-in' }} />
        <Stack.Screen name="archive" options={{ title: 'Archive' }} />
        <Stack.Screen name="suggest" options={{ title: 'Suggest a talk' }} />
        <Stack.Screen name="otis" options={{ title: 'OTIS' }} />
        <Stack.Screen name="zero-hour/index" options={{ title: 'Zero Hour' }} />
        <Stack.Screen name="zero-hour/[n]" options={{ title: 'Zero Hour' }} />
        <Stack.Screen name="alerts" options={{ title: 'Regulatory alerts' }} />
        <Stack.Screen name="alert/[id]" options={{ title: 'Regulatory alert' }} />
        <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
      </Stack>
      {!introDone && <IntroSplash onReady={hideSplash} onDone={endIntro} />}
    </ThemeProvider>
  );
}
