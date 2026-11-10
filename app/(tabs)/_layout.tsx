import { Tabs } from 'expo-router';
import { SymbolView, SymbolViewProps } from 'expo-symbols';
import { ColorValue } from 'react-native';

import { fonts, useTheme } from '@/constants/theme';

type IconName = SymbolViewProps['name'];

function icon(name: IconName) {
  function TabIcon({ color }: { color: ColorValue }) {
    return <SymbolView name={name} tintColor={color} size={26} />;
  }
  return TabIcon;
}

/** Tabs, ordered by a supervisor's shift: Monday Minute first (the app opens here), then today's talk, inspect, report, calculate, learn. */
export default function TabLayout() {
  const t = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.text,
        tabBarInactiveTintColor: t.muted,
        tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.rule },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 12 },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Monday', tabBarIcon: icon({ ios: 'stopwatch', android: 'timer', web: 'timer' }) }} />
      <Tabs.Screen name="today" options={{ title: 'Today', tabBarIcon: icon({ ios: 'sun.max', android: 'today', web: 'today' }) }} />
      <Tabs.Screen name="inspect" options={{ title: 'Inspect', tabBarIcon: icon({ ios: 'checklist', android: 'checklist', web: 'checklist' }) }} />
      <Tabs.Screen name="report" options={{ title: 'Report', tabBarIcon: icon({ ios: 'exclamationmark.triangle', android: 'report', web: 'report' }) }} />
      <Tabs.Screen name="tools" options={{ title: 'Tools', tabBarIcon: icon({ ios: 'wrench.and.screwdriver', android: 'build', web: 'build' }) }} />
      <Tabs.Screen name="learn" options={{ title: 'Learn', tabBarIcon: icon({ ios: 'book', android: 'menu_book', web: 'menu_book' }) }} />
    </Tabs>
  );
}
