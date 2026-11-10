/** Console screens. The current one lives in the URL hash so a refresh keeps your place. */
export type ScreenId = 'overview' | 'talks' | 'feed' | 'zero-hour' | 'otis' | 'ideas' | 'send';

export const SCREENS: { id: ScreenId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'talks', label: 'Talks' },
  { id: 'feed', label: 'Alerts & resources' },
  { id: 'zero-hour', label: 'Zero Hour' },
  { id: 'otis', label: 'OTIS knowledge base' },
  { id: 'ideas', label: 'Talk ideas' },
  { id: 'send', label: 'Send a notification' },
];

export function screenFromHash(): ScreenId {
  const id = window.location.hash.replace(/^#\/?/, '') as ScreenId;
  return SCREENS.some((s) => s.id === id) ? id : 'overview';
}

export function go(id: ScreenId) {
  window.location.hash = `/${id}`;
}
