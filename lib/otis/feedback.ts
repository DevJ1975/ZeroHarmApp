import Storage from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';

import { api, isConfigured } from '../config';
import { appVersion } from './manifest';

/** Both off unless the person turns them on in Settings. OTIS never sends anything on its own. */
export type FeedbackPrefs = { helpImprove: boolean; shareQuestion: boolean };
const KEY = 'otis_feedback_prefs';

export async function getFeedbackPrefs(): Promise<FeedbackPrefs> {
  const raw = await Storage.getItem(KEY);
  return raw ? (JSON.parse(raw) as FeedbackPrefs) : { helpImprove: false, shareQuestion: false };
}

export async function saveFeedbackPrefs(p: FeedbackPrefs) {
  await Storage.setItem(KEY, JSON.stringify({ helpImprove: p.helpImprove, shareQuestion: p.helpImprove && p.shareQuestion }));
}

/** Sends one "Was this helpful?" rating. Only the question text when shareQuestion is on; never a name or device id. */
export async function sendFeedback(f: { helpful: boolean; question: string; sourceIds: string[]; modelKey: string; lang: 'en' | 'es' }) {
  const prefs = await getFeedbackPrefs();
  if (!prefs.helpImprove || !isConfigured()) return false;
  try {
    await api('/v2/otis/feedback', {
      method: 'POST',
      body: JSON.stringify({
        helpful: f.helpful,
        question: prefs.shareQuestion ? f.question.slice(0, 500) : '',
        source_ids: f.sourceIds.slice(0, 8),
        model_key: f.modelKey.slice(0, 60),
        platform: Platform.OS === 'ios' ? 'ios' : 'android',
        app_version: appVersion(),
        lang: f.lang,
      }),
    });
    return true;
  } catch {
    return false;
  }
}
