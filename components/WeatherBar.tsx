import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, space, useTheme } from '@/constants/theme';
import { getWeather, locationStatus, Weather } from '@/lib/weather';

/** Header weather: place, temperature and conditions, plus a heat or cold note and any National Weather Service alert. */
export function WeatherBar() {
  const t = useTheme();
  const [wx, setWx] = useState<Weather | null>(null);
  const [status, setStatus] = useState<string>('loading');

  useEffect(() => {
    locationStatus().then(async (s) => {
      setStatus(s);
      if (s === 'granted') setWx(await getWeather());
    });
  }, []);

  if (status === 'loading' || status === 'denied') return null;
  if (status !== 'granted')
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityHint="Asks to use your location for local weather"
        onPress={async () => {
          const w = await getWeather(true);
          setStatus(w ? 'granted' : 'denied');
          setWx(w);
        }}
        style={[styles.pill, { borderColor: t.rule }]}>
        <Text style={[styles.text, { color: t.muted }]}>Show local weather and heat alerts</Text>
      </Pressable>
    );
  if (!wx) return null;

  const feels = wx.heat_index_f && wx.heat_index_f > wx.temp_f ? ` · feels like ${wx.heat_index_f}°` : '';
  return (
    <View style={{ gap: space.xs }}>
      <Text style={[styles.text, { color: t.muted }]} accessibilityLabel={`${wx.place}: ${wx.temp_f} degrees, ${wx.summary}`}>
        {wx.place ? `${wx.place} · ` : ''}
        <Text style={[styles.temp, { color: t.text }]}>{wx.temp_f}°F</Text> {wx.summary}
        {feels}
      </Text>
      {wx.alerts.slice(0, 1).map((a) => (
        <View key={a.event} style={[styles.chip, { backgroundColor: t.danger }]}>
          <Text style={styles.chipText}>{a.event}</Text>
        </View>
      ))}
      {wx.hazard && (
        <Pressable
          accessibilityRole="link"
          onPress={() => router.push({ pathname: '/archive', params: { theme: wx.hazard === 'heat' ? 'Heat' : 'Winter Safety' } })}
          style={[styles.chip, { backgroundColor: t.accent }]}>
          <Text style={[styles.chipText, { color: t.onAccent }]}>
            {wx.hazard === 'heat' ? 'Heat risk today: water, rest, shade. See the heat talks →' : 'Cold today: watch for cold stress. See the winter talks →'}
          </Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  text: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  temp: { fontFamily: fonts.bodyBold, fontSize: 15 },
  pill: { alignSelf: 'flex-start', borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, minHeight: 36, justifyContent: 'center' },
  chip: { alignSelf: 'flex-start', borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6 },
  chipText: { fontFamily: fonts.bodyBold, fontSize: 14, color: '#FFFFFF' },
});
