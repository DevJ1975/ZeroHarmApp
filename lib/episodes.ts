import Storage from 'expo-sqlite/kv-store';

import { api, isConfigured } from './config';
import { noteStaleContent } from './live';

/** A Zero Hour episode and its huddle card. */
export type Episode = {
  number: number;
  title: string;
  hazard: string;
  story: string;
  zero_hour: string;
  chain: string[];
  checks_label: string;
  checks: string[];
  stop_when: string;
  emergency_label: string;
  emergency: string;
  questions: string[];
  references: string[];
  video_url: string | null;
  thumbnail_url: string | null;
  card_pdf_url: string | null;
  released_at: string;
};

const KEY = 'zero_hour_cache';

/** Released episodes, newest first. The huddle cards are kept on the phone so they open with no signal. */
export async function listEpisodes(): Promise<Episode[]> {
  if (isConfigured()) {
    try {
      const { episodes } = await api<{ episodes: Episode[] }>('/episodes/');
      await Storage.setItem(KEY, JSON.stringify(episodes));
      return episodes;
    } catch {
      noteStaleContent(); // a content change seen now is retried on the next check
      // offline: saved copy
    }
  }
  const raw = await Storage.getItem(KEY);
  return raw ? (JSON.parse(raw) as Episode[]) : [];
}

export async function getEpisode(n: number) {
  return (await listEpisodes()).find((e) => e.number === n) ?? null;
}

export const LEGAL =
  'Zero Hour is a fictional dramatization. The people, companies and events are invented; the hazards and regulations are real. ' +
  'This Huddle Card is for general safety-awareness discussion only. It is not legal advice, not a compliance program, and not a ' +
  'substitute for a site-specific hazard assessment, written procedures, legally required training, or the judgment of a qualified ' +
  'safety professional. Citations are for reference as of November 2026; verify current requirements at ecfr.gov and osha.gov.';
