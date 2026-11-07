import * as Location from 'expo-location';

import { api, isConfigured } from './config';

export type Weather = {
  place: string;
  temp_f: number;
  summary: string;
  heat_index_f: number | null;
  wind: string;
  hazard: 'heat' | 'cold' | null;
  alerts: { event: string; severity: string; headline: string }[];
};

let cached: { at: number; data: Weather } | null = null;

/** Whether the person has already answered the location question (so we never pop it up unasked). */
export async function locationStatus() {
  return (await Location.getForegroundPermissionsAsync()).status;
}

/**
 * Local conditions from the National Weather Service, through the Zero Harm server.
 * Location is rounded to about 1 km on the phone before it is sent, and nothing is stored.
 */
export async function getWeather(ask = false): Promise<Weather | null> {
  if (cached && Date.now() - cached.at < 10 * 60 * 1000) return cached.data;
  if (!isConfigured()) return null;
  const perm = ask ? await Location.requestForegroundPermissionsAsync() : await Location.getForegroundPermissionsAsync();
  if (perm.status !== 'granted') return null;
  const pos =
    (await Location.getLastKnownPositionAsync({ maxAge: 30 * 60 * 1000 })) ??
    (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }));
  const lat = pos.coords.latitude.toFixed(2);
  const lon = pos.coords.longitude.toFixed(2);
  try {
    const data = await api<Weather>(`/weather/?lat=${lat}&lon=${lon}`);
    cached = { at: Date.now(), data };
    return data;
  } catch {
    return null;
  }
}
