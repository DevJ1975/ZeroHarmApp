# Zero Harm content console

Your control room for the Zero Harm app. It runs on your Mac and edits the live content on the
Railway backend: weekly talks (and their Spanish), alerts and free resources, Zero Hour episodes
and huddle cards, the OTIS knowledge base, talk ideas, and one-off push notifications.

Phones check for new content every time the app comes back to the foreground, and right away when
a Zero Harm notification arrives. So a saved change shows up the next time someone opens the app.

## Setup (once)

You need Node 20 or newer.

```bash
cd console
npm install
cp .env.example .env.local
```

Open `console/.env.local` and fill in:

- `CONSOLE_API_URL` – the Railway URL of the Zero Harm web service, for example
  `https://zero-harm-api.up.railway.app` (no trailing slash).
- `CONSOLE_KEY` – the same value as the `CONSOLE_KEY` variable on the Railway web service.
  Make it long and random, e.g. `openssl rand -hex 32`, and set it in both places. The backend keeps the
  console off if the key is shorter than 32 characters.

If `CONSOLE_KEY` is not set on Railway, the console endpoints are switched off and the console
shows "The content console is off."

## Run it

```bash
cd console
npm run dev
```

Then open <http://127.0.0.1:5174>. Stop it with Ctrl+C.

Other scripts: `npm run typecheck` and `npm run build` (checks that everything compiles).

## Safety notes

- **The key stays in `.env.local`.** It is git-ignored. The console's local server adds the key to
  each request on its way to Railway, so it never reaches the browser, the page source or the
  browser's storage. Don't paste it anywhere else.
- **The server listens on 127.0.0.1 only**, so other computers on your network can't reach it.
  It also refuses requests that don't come from the console page itself, so other websites open
  in your browser can't use it.
- **Wrong key?** After 10 failed attempts in an hour the backend blocks your IP for the rest of the
  hour. Fix `.env.local`, restart `npm run dev`, and wait if needed.
- **Pushes can't be taken back.** Every push asks you to confirm and names who gets it.
  Anything promotional goes to **News and offers** only – that's the group people opt in to
  separately, and it's what Apple's rules require.
- **OTIS answers only from the knowledge base text.** Review every entry against its source.
- Nothing is ever hard-deleted from the console. "Unpublish" hides an item; publish it again anytime.
