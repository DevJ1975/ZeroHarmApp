/**
 * A phone-sized copy of the app's talk screen: hero, safety-yellow placard band,
 * Barlow Condensed title, paragraphs, and the boxed crew question.
 */
export interface PreviewTalk {
  number: number;
  month_theme: string;
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string;
  hero_url: string;
  pdf_url: string;
}

const LABELS = {
  en: { issue: 'Issue', ask: 'Ask your crew', pdf: 'Open the printable PDF', pending: 'The full talk text will appear here. Until then, open the printable PDF below.' },
  es: { issue: 'Número', ask: 'Pregunte a su equipo', pdf: 'Abrir el PDF para imprimir', pending: 'El texto completo aparecerá aquí. Mientras tanto, abra el PDF para imprimir.' },
};

/** Same rules as the app: blank lines split paragraphs, "## " starts a heading, ** is dropped. */
function blocks(body: string) {
  return body
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\*\*/g, '').trim())
    .filter(Boolean)
    .map((p) => ({ heading: p.startsWith('#'), text: p.replace(/^#+\s*/, '') }));
}

export default function TalkPreview({ talk, lang }: { talk: PreviewTalk; lang: 'en' | 'es' }) {
  const l = LABELS[lang];
  const parts = blocks(talk.body_md);
  return (
    <div className="phone" aria-label="App preview">
      <div className="phone-notch" aria-hidden="true" />
      <div className="phone-screen">
        {talk.hero_url.startsWith('https://') && <img className="phone-hero" src={talk.hero_url} alt="" />}
        <div className="placard">{l.issue} {String(talk.number).padStart(2, '0')} · {talk.month_theme || '—'}</div>
        <h3 className="phone-title">{talk.title || 'Untitled talk'}</h3>
        <p className="phone-story">{talk.story_title}</p>
        {parts.length > 0 ? (
          parts.map((b, i) => (b.heading ? <h4 key={i} className="phone-h2">{b.text}</h4> : <p key={i} className="phone-body">{b.text}</p>))
        ) : (
          <p className="phone-body phone-muted">{l.pending}</p>
        )}
        <div className="phone-question">
          <div className="phone-qlabel">{l.ask}</div>
          <p className="phone-body">{talk.crew_question}</p>
        </div>
        {talk.pdf_url && <div className="phone-btn">{l.pdf}</div>}
      </div>
    </div>
  );
}
