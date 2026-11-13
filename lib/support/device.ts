/**
 * The few facts about this phone that go with a problem report or a crash report: the app version, iPhone or
 * Android, the system version and the model name ("iPhone 15", "Pixel 8"). Nothing here names a person or a
 * phone: no serial number, no advertising id, no phone name. It never throws, because the crash recorder calls it.
 */
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

export type DeviceInfo = {
  app_version: string;
  /** Left out on the web preview: the server only knows phones. */
  platform?: 'ios' | 'android';
  os_version: string;
  device: string;
};

const short = (value: unknown, max: number) => (typeof value === 'string' ? value : value == null ? '' : String(value)).trim().slice(0, max);

/** What this phone is, in the words the server's ticket uses. Every value is capped; a missing one is an empty string. */
export function deviceInfo(): DeviceInfo {
  const info: DeviceInfo = { app_version: '', os_version: '', device: '' };
  try {
    if (Platform.OS === 'ios' || Platform.OS === 'android') info.platform = Platform.OS;
    info.app_version = short(Constants.expoConfig?.version, 20);
    info.os_version = short(Device.osVersion, 20);
    info.device = short(Device.modelName, 60);
  } catch {
    // A phone that can't say what it is still gets to send its report.
  }
  return info;
}
