import { useEffect } from 'react';

import { api, type Counts, type Overview as OverviewData, type UpcomingItem } from '../api';
import { go, type ScreenId } from '../nav';
import { formatPacific } from '../time';
import { Button, Loading, PageHeader, Pill, Section, useLoad } from '../ui';

const COUNT_LABELS: { key: keyof Counts; label: string; screen: ScreenId }[] = [
  { key: 'talks_released', label: 'Talks live', screen: 'talks' },
  { key: 'talks', label: 'Talks in total', screen: 'talks' },
  { key: 'talks_needing_review', label: 'Talks needing review', screen: 'talks' },
  { key: 'feed_live', label: 'Alerts & resources live', screen: 'feed' },
  { key: 'episodes_released', label: 'Zero Hour episodes out', screen: 'zero-hour' },
  { key: 'kb_entries', label: 'OTIS entries', screen: 'otis' },
  { key: 'suggestions_new', label: 'New talk ideas', screen: 'ideas' },
  { key: 'tickets_open', label: 'Open support tickets', screen: 'tickets' },
  { key: 'sheets_failed', label: 'Sign-in sheets not saved to GHL', screen: 'overview' },
];

const TYPE_LABEL: Record<string, string> = { talk: 'Talk', feed: 'Alert / resource', episode: 'Zero Hour', broadcast: 'Notification' };
const TYPE_SCREEN: Record<string, ScreenId> = { talk: 'talks', feed: 'feed', episode: 'zero-hour', broadcast: 'send' };

function UpcomingRow({ item }: { item: UpcomingItem }) {
  return (
    <li className="list-row">
      <div>
        <div className="row-title">{item.title}</div>
        <div className="muted small">{TYPE_LABEL[item.type]} · {formatPacific(item.at)}</div>
      </div>
      <div className="row">
        {item.push ? <Pill tone="green">Push on</Pill> : <Pill tone="outline">No push</Pill>}
        <Button kind="quiet" onClick={() => go(TYPE_SCREEN[item.type])}>Open</Button>
      </div>
    </li>
  );
}

/** The "Needs attention" lines. Each one names the screen where it gets fixed. */
export function warningsFor(data: OverviewData): { text: string; screen: ScreenId }[] {
  const warnings: { text: string; screen: ScreenId }[] = [];
  if (!data.onesignal_configured) warnings.push({ text: 'OneSignal is not configured on the web service, so no notifications can go out. Set ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY on Railway.', screen: 'send' });
  if (data.counts.talks_needing_review > 0) warnings.push({ text: `${data.counts.talks_needing_review} talk(s) need review and are held out of the app.`, screen: 'talks' });
  // A web service older than this console sends no ticket count. That is not a warning.
  const open = data.counts.tickets_open ?? 0;
  if (open > 0) warnings.push({ text: `${open} support ticket${open === 1 ? ' is' : 's are'} open. Someone reported a problem, flagged an OTIS answer, or the app crashed.`, screen: 'tickets' });
  if (data.counts.sheets_failed > 0) warnings.push({ text: `${data.counts.sheets_failed} crew sign-in sheet(s) failed to save to GoHighLevel. Check them in the Django admin.`, screen: 'overview' });
  if (!data.anthropic_configured) warnings.push({ text: 'Spanish drafting is off: ANTHROPIC_API_KEY is not set on the web service.', screen: 'talks' });
  return warnings;
}

export default function Overview() {
  const { data, error, loading, reload } = useLoad(api.overview);
  useEffect(() => { reload(); }, [reload]);

  const warnings = data ? warningsFor(data) : [];

  return (
    <>
      <PageHeader
        title="Overview"
        intro="What’s live in the app, what goes out next, and anything that needs you."
        actions={<Button onClick={reload} busy={loading}>Refresh</Button>}
      />
      {error && !data && <p className="result result-error" role="alert">{error}</p>}
      {!data && !error && <Loading what="the overview" />}
      {data && (
        <>
          {warnings.length > 0 && (
            <section className="card card-warn" aria-label="Needs attention">
              <h2>Needs attention</h2>
              <ul className="plain">
                {warnings.map((w) => (
                  <li key={w.text} className="list-row">
                    <span>{w.text}</span>
                    {w.screen !== 'overview' && <Button kind="quiet" onClick={() => go(w.screen)}>Go</Button>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="stats">
            {COUNT_LABELS.map((c) => (
              <button key={c.key} type="button" className="stat" onClick={() => go(c.screen)}>
                <span className="stat-value">{data.counts[c.key] ?? '—'}</span>
                <span className="stat-label">{c.label}</span>
              </button>
            ))}
          </div>

          <div className="two-col">
            <Section title="What goes out next">
              {data.upcoming.length === 0 ? (
                <p className="muted">Nothing is scheduled. Set a send time on a talk, alert or episode to see it here.</p>
              ) : (
                <ul className="plain">{data.upcoming.map((u) => <UpcomingRow key={`${u.type}-${u.id}`} item={u} />)}</ul>
              )}
            </Section>
            <Section title="Recent pushes">
              {data.recent_pushes.length === 0 ? (
                <p className="muted">No notifications have gone out yet.</p>
              ) : (
                <ul className="plain">
                  {data.recent_pushes.map((p) => (
                    <li key={`${p.type}-${p.id}-${p.at}`} className="list-row">
                      <div>
                        <div className="row-title">{p.title}</div>
                        <div className="muted small">{TYPE_LABEL[p.type] ?? p.type} · {formatPacific(p.at)}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>

          <p className="muted small">
            Content version <code>{data.content_version}</code>. Phones compare this when the app opens and reload anything that changed.
          </p>
        </>
      )}
    </>
  );
}
