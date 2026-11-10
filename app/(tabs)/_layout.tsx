import { Tabs } from 'expo-router';
import { SymbolView, SymbolViewProps } from 'expo-symbols';
import { ColorValue } from 'react-native';

import { useHolidayAccent } from '@/components/Holiday';
import { fonts, useTheme } from '@/constants/theme';
import { useHoliday } from '@/lib/season';

type IconName = SymbolViewProps['name'];

function icon(name: IconName) {
  function TabIcon({ color }: { color: ColorValue }) {
    return <SymbolView name={name} tintColor={color} size={26} />;
  }
  return TabIcon;
}

/** Tabs, ordered by a supervisor's shift: Monday Minute first (the app opens here), then Zero Harm Weekly, tools, learn. */
export default function TabLayout() {
  const t = useTheme();
  const festive = useHoliday();
  const evergreen = useHolidayAccent();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: festive ? evergreen : t.text,
        tabBarInactiveTintColor: t.muted,
        tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.rule },
        tabBarLabelStyle: { fontFamily: fonts.bodyMedium, fontSize: 12 },
      }}>
      <Tabs.Screen name="index" options={{ title: 'Monday', tabBarIcon: icon({ ios: 'stopwatch', android: 'timer', web: 'timer' }) }} />
      <Tabs.Screen name="today" options={{ title: 'Today', tabBarIcon: icon({ ios: 'sun.max', android: 'today', web: 'today' }) }} />
      <Tabs.Screen name="tools" options={{ title: 'Tools', tabBarIcon: icon({ ios: 'wrench.and.screwdriver', android: 'build', web: 'build' }) }} />
      <Tabs.Screen name="learn" options={{ title: 'Learn', tabBarIcon: icon({ ios: 'book', android: 'menu_book', web: 'menu_book' }) }} />
    </Tabs>
  );
}
