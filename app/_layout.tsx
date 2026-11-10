import { Barlow_400Regular, Barlow_500Medium, Barlow_600SemiBold } from '@expo-google-fonts/barlow';
import { BarlowCondensed_600SemiBold, BarlowCondensed_700Bold } from '@expo-google-fonts/barlow-condensed';
import { useFonts } from 'expo-font';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useCallback, useEffect, useState } from 'react';
import { AppState, useColorScheme, View } from 'react-native';
import 'react-native-reanimated';

import { HolidaySplash } from '@/components/Holiday';
import { fonts } from '@/constants/theme';
import { flushVotes } from '@/lib/monday';
import { startPush } from '@/lib/push';
import { isHoliday, refreshSeason } from '@/lib/season';
import { flushSheets } from '@/lib/sheets';
import { reportOpen } from '@/lib/usage';

export { ErrorBoundary } from 'expo-router';

export const unstable_settings = { anchor: '(tabs)' };

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const scheme = useColorScheme();
  // The holiday opening screen plays once per cold start, decided by the date when the app opens.
  const [opening, setOpening] = useState(isHoliday);
  const closeOpening = useCallback(() => setOpening(false), []);
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

  useEffect(() => {
    startPush();
    // Sheets and votes saved with no signal go out now, and again each time the app comes back to the front:
    // people walk from a dead spot on the floor to the break room with the phone in their pocket.
    const flush = () => {
      flushSheets();
      flushVotes();
      refreshSeason();
      reportOpen();
    };
    flush();
    const sub = AppState.addEventListener('change', (state) => state === 'active' && flush());
    return () => sub.remove();
  }, []);

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <View style={{ flex: 1 }}>
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
        <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
      </Stack>
    </ThemeProvider>
    {opening && <HolidaySplash onDone={closeOpening} />}
    </View>
  );
}
