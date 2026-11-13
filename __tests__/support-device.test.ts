import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

import { deviceInfo } from '@/lib/support/device';

jest.mock('expo-device', () => ({ __esModule: true, modelName: 'iPhone 15', osVersion: '18.1' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));

const device = Device as { modelName: string | null; osVersion: string | null };
const constants = Constants as unknown as { expoConfig: { version?: unknown } | null };
const realOS = Platform.OS;

afterEach(() => {
  Platform.OS = realOS;
  device.modelName = 'iPhone 15';
  device.osVersion = '18.1';
  constants.expoConfig = { version: '1.0.0' };
});

describe('deviceInfo', () => {
  it('gives the app version, platform, system version and model, and nothing else', () => {
    expect(deviceInfo()).toEqual({ app_version: '1.0.0', platform: 'ios', os_version: '18.1', device: 'iPhone 15' });
  });

  it('says android on an Android phone', () => {
    Platform.OS = 'android';
    device.modelName = 'Pixel 8';
    device.osVersion = '15';
    expect(deviceInfo()).toEqual({ app_version: '1.0.0', platform: 'android', os_version: '15', device: 'Pixel 8' });
  });

  it('leaves the platform out on the web, where the server has no name for it', () => {
    Platform.OS = 'web';
    expect(deviceInfo()).not.toHaveProperty('platform');
    expect(JSON.parse(JSON.stringify(deviceInfo()))).toEqual({ app_version: '1.0.0', os_version: '18.1', device: 'iPhone 15' });
  });

  it('caps every value at what the server takes', () => {
    device.modelName = 'x'.repeat(200);
    device.osVersion = '9'.repeat(200);
    constants.expoConfig = { version: '1'.repeat(200) };
    const info = deviceInfo();
    expect(info.device).toHaveLength(60);
    expect(info.os_version).toHaveLength(20);
    expect(info.app_version).toHaveLength(20);
  });

  it('gives empty strings, never null, when the phone will not say', () => {
    device.modelName = null;
    device.osVersion = null;
    constants.expoConfig = null;
    expect(deviceInfo()).toEqual({ app_version: '', platform: 'ios', os_version: '', device: '' });
  });

  it('never throws, because the crash recorder calls it', () => {
    Object.defineProperty(constants, 'expoConfig', { configurable: true, get: () => { throw new Error('native side is gone'); } });
    expect(() => deviceInfo()).not.toThrow();
    expect(deviceInfo().device).toBe('');
    Object.defineProperty(constants, 'expoConfig', { configurable: true, writable: true, value: { version: '1.0.0' } });
  });
});
