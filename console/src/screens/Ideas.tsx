import { useEffect, useState } from 'react';

import { api, type Suggestion, type SuggestionStatus } from '../api';
import { formatPacific } from '../time';
import { Button, Loading, PageHeader, Pill, ResultLine, Select, TextField, useAction, useLoad, type Result } from '../ui';

const STATUSES: { value: SuggestionStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'planned', label: 'Planned' },
  { value: 'used', label: 'Used in an issue' },
  { value: 'declined', label: 'Not a fit' },
];

const issueText = (s: Suggestion) => (s.used_in_issue ? String(s.used_in_issue) : '');

function IdeaCard({ s, onSaved }: { s: Suggestion; onSaved: (s: Suggestion) => void }) {
  // Edits are compared with the copy the card last loaded, so a Refresh with newer values can update an untouched card.
  const [loaded, setLoaded] = useState(s);
  const [status, setStatus] = useState(s.status);
  const [issue, setIssue] = useState(issueText(s));
  const save = useAction();
  const dirty = status !== loaded.status || issue !== issueText(loaded);

  function load(x: Suggestion) {
    setLoaded(x);
    setStatus(x.status);
    setIssue(issueText(x));
  }
  if (s !== loaded && !dirty) load(s); // a newer server copy, and nothing typed here yet

  async function submit() {
    const n = issue.trim() ? Number(issue) : null;
    if (n !== null && (!Number.isInteger(n) || n < 1)) return save.setResult({ kind: 'error', text: 'Issue must be a whole number.' });
    const saved = await save.run(() => api.updateSuggestion(s.id, { status, used_in_issue: n }), 'Saved.');
    if (saved) {
      load(saved);
      onSaved(saved);
    }
  }

  return (
    <li className="card idea">
      <div className="card-head">
        <h2>{s.topic}</h2>
        <Pill tone={s.status === 'new' ? 'red' : s.status === 'used' ? 'green' : s.status === 'declined' ? 'outline' : 'neutral'}>
          {STATUSES.find((x) => x.value === s.status)?.label}
        </Pill>
      </div>
      {s.details && <p className="pre">{s.details}</p>}
      <p className="muted small">
        {s.month_theme && <>Theme: {s.month_theme} · </>}
        {s.name || 'Anonymous'}{s.company ? `, ${s.company}` : ''}
        {s.email && s.may_contact ? <> · <a href={`mailto:${s.email}`}>{s.email}</a> (ok to contact)</> : s.email ? ' · do not contact' : ''}
        {' · '}{formatPacific(s.created_at)}
      </p>
      <div className="form-row compact">
        <Select<SuggestionStatus> label="Status" value={status} options={STATUSES} onChange={setStatus} />
        <TextField label="Used in issue #" type="number" value={issue} onChange={setIssue} />
        <div className="field field-end">
          <Button kind="primary" onClick={submit} busy={save.busy} disabled={!dirty}>Save</Button>
        </div>
      </div>
      <ResultLine result={save.result} />
      {s !== loaded && (
        <p className="hint" role="status">
          This idea changed on the server while you were editing. Saving overwrites it.{' '}
          <Button kind="quiet" onClick={() => load(s)}>Load the newer version</Button>
        </p>
      )}
    </li>
  );
}

export default function Ideas() {
  const { data, setData, error, loading, reload } = useLoad(api.suggestions);
  const [filter, setFilter] = useState<SuggestionStatus | 'all'>('new');
  const [last, setLast] = useState<Result>(null);
  useEffect(() => { reload(); }, [reload]);
  const shown = (data ?? []).filter((s) => filter === 'all' || s.status === filter);

  // An idea can leave the filtered list when its status changes, so the result is also shown up here.
  function saved(x: Suggestion) {
    setData((list) => list?.map((y) => (y.id === x.id ? x : y)));
    setLast({ kind: 'ok', text: `Saved “${x.topic}” as ${STATUSES.find((s) => s.value === x.status)?.label}.` });
  }

  return (
    <>
      <PageHeader title="Talk ideas" intro="Ideas sent from the app’s Suggest a talk screen." actions={<Button onClick={reload} busy={loading}>Refresh</Button>} />
      {error && !data && <p className="result result-error" role="alert">{error}</p>}
      {!data && !error && <Loading what="talk ideas" />}
      {data && (
        <>
          <div className="filters">
            <Select<SuggestionStatus | 'all'> label="Show" value={filter} onChange={setFilter} options={[{ value: 'all', label: 'All ideas' }, ...STATUSES]} />
          </div>
          <ResultLine result={last} />
          {shown.length === 0 ? (
            <p className="muted">No ideas here.</p>
          ) : (
            <ul className="plain ideas">
              {shown.map((s) => <IdeaCard key={s.id} s={s} onSaved={saved} />)}
            </ul>
          )}
        </>
      )}
    </>
  );
}
