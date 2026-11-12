import { useEffect, useState } from 'react';

import { api, onConnection, type Connection } from './api';
import { SCREENS, screenFromHash, type ScreenId } from './nav';
import Broadcast from './screens/Broadcast';
import Episodes from './screens/Episodes';
import Feed from './screens/Feed';
import Ideas from './screens/Ideas';
import Kb from './screens/Kb';
import Overview from './screens/Overview';
import Talks from './screens/Talks';
import Tickets from './screens/Tickets';
import { Button } from './ui';

function ConnectionBanner({ conn }: { conn: Connection | null }) {
  const [checking, setChecking] = useState(false);
  if (!conn || conn.ok) return null;
  const title =
    conn.status === 401 ? 'The console key was not accepted.'
    : conn.status === 429 ? 'The console key is wrong, and it has been tried too many times.'
    : conn.status === 503 ? 'The content console is switched off or not set up.'
    : 'Can’t reach the Zero Harm API.';
  const help =
    conn.status === 401 || conn.status === 429 ? 'Make sure CONSOLE_KEY in console/.env.local matches the CONSOLE_KEY variable on Railway, then restart npm run dev. The right key works straight away; waiting does not fix a wrong one.'
    : conn.status === 0 ? ''
    : 'Check CONSOLE_API_URL in console/.env.local and that the Railway web service is running.';
  async function retry() {
    setChecking(true);
    try {
      await api.overview();
    } catch {
      // The banner updates from the request itself.
    } finally {
      setChecking(false);
    }
  }
  return (
    <div className="banner" role="alert">
      <div>
        <strong>{title}</strong>
        <p>The server said: “{conn.error}”</p>
        {help && <p>{help}</p>}
      </div>
      <Button kind="secondary" onClick={retry} busy={checking}>Try again</Button>
    </div>
  );
}

export default function App() {
  const [screen, setScreen] = useState<ScreenId>(screenFromHash);
  const [conn, setConn] = useState<Connection | null>(null);

  useEffect(() => {
    const onHash = () => setScreen(screenFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => onConnection(setConn), []);
  useEffect(() => {
    document.title = `${SCREENS.find((s) => s.id === screen)?.label} · Zero Harm Console`;
    document.getElementById('main')?.focus();
  }, [screen]);

  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <nav className="nav" aria-label="Console sections">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">ZH</span>
          <span>
            <span className="brand-name">Zero Harm</span>
            <span className="brand-sub">Content console</span>
          </span>
        </div>
        <ul>
          {SCREENS.map((s) => (
            <li key={s.id}>
              <a href={`#/${s.id}`} aria-current={screen === s.id ? 'page' : undefined}>{s.label}</a>
            </li>
          ))}
        </ul>
        <p className="nav-note">Changes go live in the app the next time someone opens it.</p>
        <p className="nav-credit">Made with love ❤️ from Las Vegas, Trainovate</p>
      </nav>
      <main id="main" tabIndex={-1}>
        <ConnectionBanner conn={conn} />
        {screen === 'overview' && <Overview />}
        {screen === 'talks' && <Talks />}
        {screen === 'feed' && <Feed />}
        {screen === 'zero-hour' && <Episodes />}
        {screen === 'otis' && <Kb />}
        {screen === 'ideas' && <Ideas />}
        {screen === 'tickets' && <Tickets />}
        {screen === 'send' && <Broadcast />}
      </main>
    </div>
  );
}
