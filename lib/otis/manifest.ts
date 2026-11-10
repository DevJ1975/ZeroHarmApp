import Constants from 'expo-constants';
import * as Device from 'expo-device';
import Storage from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';
import { getRegisteredBackends, models, type LLMModel } from 'react-native-executorch';

import { api, isConfigured } from '../config';

/** Built-in react-native-executorch models OTIS knows how to use. */
export type BuiltinName = 'QWEN3_1_7B' | 'QWEN3_0_6B';

/** What this phone should run, from POST /api/v2/otis/manifest. The model always runs on the phone. */
export type Manifest = {
  enabled: boolean;
  message: string;
  update_required: boolean;
  model: {
    key: string;
    label: string;
    size_mb: number;
    builtin: BuiltinName | null;
    files: { model_url: string; tokenizer_url: string; tokenizer_config_url: string } | null;
  } | null;
  kb: { version: string; changed: boolean };
  feedback_enabled: boolean;
};

const KEY = 'otis_manifest';
const KB_VERSION_KEY = 'otis_kb_version';
const BUILTIN_SIZE: Record<BuiltinName, number> = { QWEN3_1_7B: 1300, QWEN3_0_6B: 510 };

export const appVersion = () => Constants.expoConfig?.version ?? '';
export const memoryGb = () => (Device.totalMemory ?? 0) / 1024 ** 3;

/** The ExecuTorch backends this app build can run (e.g. mlx, xnnpack), so the server only offers files the phone can load. */
function backends(): string[] {
  try {
    return getRegisteredBackends().map((b) => b.toLowerCase());
  } catch {
    return [];
  }
}

/** Used when there's no signal and no saved manifest: the library's built-in model, chosen by memory, like OTIS v1. */
function offlineDefault(): Manifest {
  const name: BuiltinName = memoryGb() >= 6 ? 'QWEN3_1_7B' : 'QWEN3_0_6B';
  return {
    enabled: true,
    message: '',
    update_required: false,
    model: { key: `builtin-${name}`, label: name === 'QWEN3_1_7B' ? 'OTIS standard' : 'OTIS compact', size_mb: BUILTIN_SIZE[name], builtin: name, files: null },
    kb: { version: '', changed: false },
    feedback_enabled: false,
  };
}

/** Asks the server what to run; keeps the last answer so OTIS opens on the dock with no signal. */
export async function getManifest(): Promise<Manifest> {
  if (isConfigured()) {
    try {
      const m = await api<Manifest>('/v2/otis/manifest', {
        method: 'POST',
        body: JSON.stringify({
          platform: Platform.OS === 'ios' ? 'ios' : 'android',
          memory_gb: Math.round(memoryGb() * 10) / 10,
          app_version: appVersion(),
          os_version: String(Device.osVersion ?? '').slice(0, 20),
          backends: backends(),
          kb_version: (await Storage.getItem(KB_VERSION_KEY)) ?? '',
        }),
      });
      await Storage.setItem(KEY, JSON.stringify(m));
      return m;
    } catch {
      // no signal or older server: fall back below
    }
  }
  const saved = await Storage.getItem(KEY);
  return saved ? (JSON.parse(saved) as Manifest) : offlineDefault();
}

/** Turns the manifest's model into what useLLMChatSession loads: pinned files, or a built-in model. */
export function llmModel(m: NonNullable<Manifest['model']>): LLMModel {
  if (m.files) {
    return { modelPath: m.files.model_url, tokenizerPath: m.files.tokenizer_url, tokenizerConfigPath: m.files.tokenizer_config_url };
  }
  return models.llm[m.builtin ?? 'QWEN3_0_6B'].DEFAULT;
}

export const sizeLabel = (mb: number) => (mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${mb} MB`);

export const kbVersionKey = KB_VERSION_KEY;
