import Storage from 'expo-sqlite/kv-store';

import { api, isConfigured } from './config';
import { savedFirst } from './saved-first';

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

/** Released episodes, newest first. The saved huddle cards come back right away; `onFresh` gets the server's list after. */
export async function listEpisodes(onFresh?: (list: Episode[]) => void): Promise<Episode[]> {
  const { value } = await savedFirst<Episode[]>(
    'episodes',
    async () => {
      const raw = await Storage.getItem(KEY);
      const saved = raw ? (JSON.parse(raw) as Episode[]) : [];
      return saved.length ? saved : null;
    },
    async () => {
      if (!isConfigured()) throw new Error('API not configured');
      const { episodes } = await api<{ episodes: Episode[] }>('/episodes/');
      await Storage.setItem(KEY, JSON.stringify(episodes));
      return episodes;
    },
    { onFresh },
  );
  return value ?? [];
}

export async function getEpisode(n: number, onFresh?: (ep: Episode | null) => void) {
  const find = (list: Episode[]) => list.find((e) => e.number === n) ?? null;
  return find(await listEpisodes(onFresh && ((list) => onFresh(find(list)))));
}

export const LEGAL =
  'Zero Hour is a fictional dramatization. The people, companies and events are invented; the hazards and regulations are real. ' +
  'This Huddle Card is for general safety-awareness discussion only. It is not legal advice, not a compliance program, and not a ' +
  'substitute for a site-specific hazard assessment, written procedures, legally required training, or the judgment of a qualified ' +
  'safety professional. Citations are for reference as of November 2026; verify current requirements at ecfr.gov and osha.gov.';
