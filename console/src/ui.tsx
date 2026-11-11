import { useCallback, useId, useState, type ReactNode } from 'react';

import { ApiError } from './api';

// ---------- Result messages: every write says what happened ----------

export type Result = { kind: 'ok' | 'error' | 'info'; text: string } | null;

export function ResultLine({ result }: { result: Result }) {
  if (!result) return null;
  return (
    <p className={`result result-${result.kind}`} role={result.kind === 'error' ? 'alert' : 'status'}>
      {result.text}
    </p>
  );
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

/** Runs a write, tracks busy state, and turns success or failure into a Result. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const run = useCallback(async <T,>(fn: () => Promise<T>, okText: string | ((v: T) => string)) => {
    setBusy(true);
    setResult(null);
    try {
      const v = await fn();
      setResult({ kind: 'ok', text: typeof okText === 'function' ? okText(v) : okText });
      return v;
    } catch (e) {
      setResult({ kind: 'error', text: errorText(e) });
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, result, setResult, run };
}

// ---------- Buttons ----------

type ButtonKind = 'primary' | 'secondary' | 'danger' | 'quiet';

export function Button(props: {
  kind?: ButtonKind;
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  busy?: boolean;
  type?: 'button' | 'submit';
  title?: string;
}) {
  const { kind = 'secondary', children, onClick, disabled, busy, type = 'button', title } = props;
  return (
    <button type={type} className={`btn btn-${kind}`} onClick={onClick} disabled={disabled || busy} aria-busy={busy || undefined} title={title}>
      {busy ? 'Working…' : children}
    </button>
  );
}

/**
 * Two-step action for anything that reaches phones. The first click shows exactly
 * what will happen; nothing is sent until the second click.
 */
export function ConfirmAction(props: {
  label: string;
  confirmLabel: string;
  message: ReactNode;
  onConfirm: () => void;
  kind?: ButtonKind;
  disabled?: boolean;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button kind={props.kind ?? 'primary'} onClick={() => setOpen(true)} disabled={props.disabled} busy={props.busy}>
        {props.label}
      </Button>
    );
  }
  return (
    <div className="confirm" role="group" aria-label="Confirm">
      <div className="confirm-message">{props.message}</div>
      <div className="row">
        {/* Stays disabled if things change while the confirm step is open (an edit after the dry run, unsaved changes). */}
        <Button kind={props.kind ?? 'primary'} busy={props.busy} disabled={props.disabled} onClick={() => { setOpen(false); props.onConfirm(); }}>
          {props.confirmLabel}
        </Button>
        <Button kind="quiet" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
    </div>
  );
}

// ---------- Form fields ----------

export function Field(props: { label: string; hint?: ReactNode; children: (id: string) => ReactNode; counter?: { value: string; max: number } }) {
  const id = useId();
  const over = props.counter && props.counter.value.length > props.counter.max;
  return (
    <div className="field">
      <div className="field-top">
        <label htmlFor={id}>{props.label}</label>
        {props.counter && (
          <span className={`counter${over ? ' counter-over' : ''}`} aria-live="polite">
            {props.counter.value.length}/{props.counter.max}
          </span>
        )}
      </div>
      {props.children(id)}
      {props.hint && <p className="hint">{props.hint}</p>}
    </div>
  );
}

export function TextField(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: ReactNode;
  placeholder?: string;
  type?: 'text' | 'url' | 'date' | 'datetime-local' | 'number' | 'search';
  max?: number;
}) {
  return (
    <Field label={props.label} hint={props.hint} counter={props.max ? { value: props.value, max: props.max } : undefined}>
      {(id) => (
        <input
          id={id}
          type={props.type ?? 'text'}
          value={props.value}
          placeholder={props.placeholder}
          onChange={(e) => props.onChange(e.target.value)}
        />
      )}
    </Field>
  );
}

export function TextArea(props: { label: string; value: string; onChange: (v: string) => void; hint?: ReactNode; rows?: number; max?: number }) {
  return (
    <Field label={props.label} hint={props.hint} counter={props.max ? { value: props.value, max: props.max } : undefined}>
      {(id) => <textarea id={id} rows={props.rows ?? 4} value={props.value} onChange={(e) => props.onChange(e.target.value)} />}
    </Field>
  );
}

export function Select<T extends string>(props: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; hint?: ReactNode }) {
  return (
    <Field label={props.label} hint={props.hint}>
      {(id) => (
        <select id={id} value={props.value} onChange={(e) => props.onChange(e.target.value as T)}>
          {props.options.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function Toggle(props: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: ReactNode }) {
  const id = useId();
  return (
    <div className="toggle">
      <input id={id} type="checkbox" checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} />
      <label htmlFor={id}>
        <span>{props.label}</span>
        {props.hint && <span className="hint">{props.hint}</span>}
      </label>
    </div>
  );
}

/** Editable list of short lines (huddle-card checks, questions, references). */
export function ListEditor(props: { label: string; items: string[]; onChange: (items: string[]) => void; hint?: ReactNode; addLabel?: string }) {
  const { items, onChange } = props;
  const set = (i: number, v: string) => onChange(items.map((x, j) => (j === i ? v : x)));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= items.length) return;
    const next = [...items];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  return (
    <fieldset className="list-editor">
      <legend>{props.label}</legend>
      {props.hint && <p className="hint">{props.hint}</p>}
      {items.length === 0 && <p className="hint">Nothing here yet.</p>}
      <ol>
        {items.map((item, i) => (
          <li key={i}>
            <textarea rows={2} aria-label={`${props.label} item ${i + 1}`} value={item} onChange={(e) => set(i, e.target.value)} />
            <div className="list-tools">
              <button type="button" className="icon-btn" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move item ${i + 1} up`}>↑</button>
              <button type="button" className="icon-btn" onClick={() => move(i, 1)} disabled={i === items.length - 1} aria-label={`Move item ${i + 1} down`}>↓</button>
              <button type="button" className="icon-btn icon-danger" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label={`Remove item ${i + 1}`}>✕</button>
            </div>
          </li>
        ))}
      </ol>
      <Button kind="quiet" onClick={() => onChange([...items, ''])}>{props.addLabel ?? '+ Add a line'}</Button>
    </fieldset>
  );
}

// ---------- Status pills and layout bits ----------

// Safety yellow is kept for primary actions and the placard, so pills never use it.
export type Tone = 'green' | 'red' | 'neutral' | 'outline';

export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function PageHeader({ title, intro, actions }: { title: string; intro?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {intro && <p className="intro">{intro}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="muted" role="status">Loading {what}…</p>;
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Loads data once and on demand. Errors are shown in place and in the connection banner. */
export function useLoad<T>(fn: () => Promise<T>) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fn());
      setError('');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
    // fn is defined inline by callers and is stable in practice; reload when they ask.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { data, setData, error, loading, reload };
}

/**
 * An editor's working copy of one server record. A newer copy from the server (Refresh, or a push
 * that re-fetched it) replaces the draft only while you have no unsaved edits. With edits, they are
 * kept and `stale` says the server copy moved; Discard (load(server)) picks up the new one.
 * Call load(saved) after your own save, so the editor starts clean from what the server stored.
 */
export function useDraft<S, D>(server: S, toDraft: (s: S) => D, isDirty: (base: D, d: D) => boolean) {
  const [loaded, setLoaded] = useState(server);
  const [base, setBase] = useState(() => toDraft(server));
  const [d, setD] = useState(base);
  const dirty = isDirty(base, d);

  const load = useCallback((s: S) => {
    const fresh = toDraft(s);
    setLoaded(s);
    setBase(fresh);
    setD(fresh);
  }, [toDraft]);

  // Adjusting state while rendering (not in an effect), so a refresh never flashes the old copy.
  if (server !== loaded && !dirty) load(server);

  return { base, d, setD, dirty, stale: server !== loaded, load };
}

export function StaleNote({ what }: { what: string }) {
  return (
    <p className="hint" role="status">
      This {what} changed on the server while you were editing. Your edits are kept. Discard to load the newer version, or save to overwrite it.
    </p>
  );
}
