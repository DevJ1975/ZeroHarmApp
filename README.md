# Zero Harm

The free Zero Harm safety app from Trainovate Technologies, plus the Django backend that serves it.

```
/            Expo / React Native app (iOS and Android)
/backend     Django API + admin, Dockerized, deployed on Railway
```

## The app (Expo SDK 58, React Native 0.88, Expo Router, OneSignal)
- **Today:** this week's talk as a safety-yellow placard, past talks below, offline copy on the phone.
- **Talk screen:** story, crew question, printable PDF, and a weekly-reminder prompt after the first talk.
- **Crew sign-in:** pass the phone around, type a name, sign, share a branded PDF sign-in sheet. Stored on the phone only.
- **Tools:** TRIR and DART rate calculator (200,000-hour base).
- **Settings:** two separate switches, "Weekly toolbox talk" and "News and offers" (promotional, off by default), plus optional email sign-up.
- **Learn:** Zero Hour episodes, free courses and tools published from GoHighLevel, and the newsletter sign-up.

Run it:
1. `npm install`
2. Copy `.env.example` to `.env`; set `EXPO_PUBLIC_API_URL` to the Railway URL and `EXPO_PUBLIC_ONESIGNAL_APP_ID`.
3. OneSignal and the signature pad need native code, so use a development build, not Expo Go:
   `npx eas-cli@latest build --profile development --platform ios`, then `npx expo start`.
4. Before the store build, change `onesignal-expo-plugin` mode in `app.json` to `production`.

## The backend (Django 5.2 LTS, Postgres, Docker, Railway)
- `GET /api/talks/` talks the app shows, newest first: every talk past its Sunday 11:59 AM Pacific send time, plus the next two upcoming talks that have their text (`early: true`), so supervisors can run them ahead with crew sign-in. An early talk leaves out "Last week's answer" until its own send time, so it can't give away the previous crew question. `TALKS_EARLY_COUNT` changes how many open early; `TALKS_UNLOCK_EARLY=0` holds every talk until Sunday. The Sunday push goes out on schedule either way.
- `GET /api/talks/<issue>/` one talk. `POST /api/signups/` optional email sign-up (rate limited), synced to GoHighLevel with tags `zero-harm-app`, `zero-harm-weekly`, and `zero-harm-offers-optin` when they opt in.
- `/admin/` edit talk text, PDF and image links, see sign-ups, send a push or retry a GHL sync by hand.
- All 52 issues of 2027 load automatically on the first migrate.
- `python manage.py cron` sends any due Sunday push (once only) and retries pending GHL syncs.

### Monday Minute (the app's first screen)
A weekly 5-minute crew talk written by AI, separate from Zero Harm Weekly (code in `backend/monday/`, screens in `app/monday/`).
- **Topic bank:** 104 topic briefs (two years with no repeats), each checked against the eCFR text and reviewed in the
  CSP role before use (`backend/monday/topics.json`, review record in `docs/monday-minute-topic-review.md`). Edit them
  in the admin under *Monday Minute topics*.
- **Weekly run, no human approval:** from Wednesday, the cron picks a topic (in season, well rated, not used in two years),
  and the AI (your local model, or Claude) writes the talk from that one brief. Hard checks run on every draft: required lines word for word, no number
  that isn't in the brief, no links, one crew question. A second AI call then reviews it as a Certified Safety
  Professional and maps every point to a brief line. Any MUST FIX finding or ungrounded point means a rewrite, up to
  3 tries on each of 2 topics. With the local model, a second, independent review must also pass, and both must be
  highly confident. If nothing passes, that week
  doesn't publish. Talks publish Monday at 5:00 AM Pacific with a push to devices with *Monday Minute* turned on.
  *Write next week's Monday Minute now* in the admin runs it on demand.
- **Safety gate:** a talk that passes its checks publishes on its own only if the current AI setup (reviewer model, RAG
  on or off, strict review on or off) has passed the safety test in the last 90 days: at least 90% of planted mistakes
  caught, no more than about a third of good talks wrongly blocked, at least 20 planted mistakes tested. Otherwise the
  talk is saved as *Waiting for approval* and a person publishes it with *Approve and publish* in the admin. Changing
  the model or turning RAG off means passing the test again. The bar is set with `MONDAY_GATE_MIN_CATCH`,
  `MONDAY_GATE_MAX_FALSE_BLOCK`, `MONDAY_GATE_MIN_CASES` and `MONDAY_GATE_MAX_AGE_DAYS`; `MONDAY_GATE=0` turns it off.
- **Crews:** read it, print it with a paper sign-in sheet, or sign on the phone (finger signatures and/or a group
  photo). Then print, email or save the signed sheet. Every sheet is kept on the phone (*My sign-in sheets*).
- **Thumbs up/down** (one per phone per talk), with reasons on a thumbs down. Three "isn't safe or isn't right"
  reports pull the talk and pause its topic until someone reviews it. Ratings also steer which topics come next.
- **Comments and replies**, screened by AI moderation before they show (in the background with the local model). Held if moderation is down. Two reports hide a
  comment. Anyone can block a commenter on their phone, and people agree to community rules before their first comment.
  The admin can hide or restore any comment.
- API: `/api/v2/monday-minute` (list, detail, `/feedback`, `/comments`, `/comments/{id}/report`).

### Back office inside GoHighLevel
`/backoffice/` is an analytics page built to sit inside GoHighLevel:
- **What it shows:** sign-in sheets and crew members signed in (with 12-week charts), supervisors running talks, email
  sign-ups, Monday Minute thumbs and comments, OTIS ratings, the most-used talks, and a *Needs your attention* list
  (pulled talks, paused topics, OSHA rule changes, comments waiting, sheets that didn't reach GHL, talks held for
  bracketed notes, new suggestions). Every item links to the right admin page.
- **What it can't show:** installs and screen views. The app doesn't track them.
- **Access:** set `BACKOFFICE_KEY` on the web service to a long random value. The page opens with
  `https://<your-api-domain>/backoffice/?key=<BACKOFFICE_KEY>`, or for anyone signed in to the admin. Only GoHighLevel's
  domains may frame it. If you use a white-label app address, add it with `GHL_APP_DOMAINS=https://app.yourbrand.com`.
- **Install in GoHighLevel:** Agency view → Settings → Custom Menu Links → Create new. Give it a name (Zero Harm) and an
  icon, paste the link above, choose *Open in iFrame*, and show it to agency and account admins only, since the link
  holds the key.
- **Admin from GoHighLevel:** add a second custom menu link to `https://<your-api-domain>/admin/` set to *Open in new
  tab*. That works in every browser. To show the admin inside the GHL frame, set `GHL_EMBED_ADMIN=1`: it needs login
  cookies that work inside a frame, which Safari and some Chrome settings block, so the new-tab link is the default.

### OSHA regulation library (RAG) and amendment watch
`backend/regs/` keeps the official eCFR text of every OSHA section that Monday Minute and OTIS cite (49 sections).
They're split into paragraphs like 1910.147(d), with appendices kept separate.
- **Seeded** with the exact text the topic bank and OTIS entries were reviewed against (eCFR as of 2026-11-06), so it
  works on the first deploy.
- **Weekly sync** (`python manage.py regs_sync`, run by the cron) re-downloads those sections. If OSHA changed one,
  it records an *OSHA amendment* in the admin, pauses every Monday Minute topic that cites it, and takes every OTIS
  entry that cites it out of OTIS (with the reason). Turn them back on once they're re-reviewed.
- **Monday Minute reviewer:** each review also gets the regulation paragraphs behind the brief and the talk, plus the
  closest real findings from the CSP review of the topic bank. Any OSHA claim the text doesn't support is MUST FIX.
  `MONDAY_RAG=0` turns this off. The writer still sees only the brief.
- **OTIS:** the phones' knowledge base includes the official paragraphs its entries and the Monday Minute facts point
  to (main text, about 250K characters). Plain-language entries rank first, and OTIS cites and links the section.
- **Safety test:** in the admin, select topics under *Monday Minute topics* and choose *Run the safety test*. Each
  topic gets a faithful talk plus copies with planted mistakes (skipping lockout, gloves at rotating parts,
  predicting a load's path, untrained rescue, a made-up OSHA rule, a shortcut, the topic's own never-say line). It
  reports the catch rate, how often good talks are wrongly blocked, and the time per talk, with and without RAG.
  Results are under *Monday Minute safety test runs*. CLI: `python manage.py monday_eval`. On the local CPU model,
  expect hours.

### OTIS on-device AI (API v2, Django Ninja)
OTIS's model runs on the phone with ExecuTorch: MLX or Core ML on iPhone, XNNPACK or Vulkan on Android. The server never runs it.
API v2 (`/api/v2/`, docs at `/api/v2/docs`) tells each phone what to run:
- `POST /api/v2/otis/manifest` takes the platform, memory, app version and the ExecuTorch backends the build links. It returns
  the on/off switch, the model to download (a pinned release, or the library's built-in Qwen3 chosen by memory) and the
  knowledge base version.
- `GET /api/v2/otis/kb` returns the knowledge base with an ETag. Phones send `If-None-Match` and get a 304 when nothing changed.
- `POST /api/v2/otis/feedback` takes "Was this helpful?" ratings, only from people who turn on *Help improve OTIS* in Settings
  (off by default). The question text is sent only if they also turn on *Include my question*.

In the admin:
- **OTIS rollout:** turn OTIS off per platform, set a minimum app version, or pause feedback.
- **OTIS model releases:** pin the exact model files (HTTPS links to the `.pte`, `tokenizer.json` and `tokenizer_config.json`)
  per platform, backend and memory tier. Change a release's key and phones offer an "Update OTIS" download. With no active
  release, phones use the built-in model.
- **OTIS feedback:** review the ratings.

The v1 endpoints (`/api/otis/kb/`, `/api/otis/config/`) stay up for app builds already installed.
The OSHA General Industry knowledge base and its safety review: `docs/otis-osha-kb-review.md`.

Run it locally with OrbStack or Docker Desktop:
```
cd backend
docker compose up --build
docker compose exec web python manage.py createsuperuser
```
Then open http://localhost:8000/admin/. Tests: `docker compose exec web python manage.py test talks`.

## Railway layout
- **Postgres** database.
- **web** service: this repo, root directory `/backend`, built from the Dockerfile, health check `/api/health/`.
- **cron** service: same repo and root, start command `python manage.py cron`, schedule `*/15 * * * *` (every 15 minutes).
  Each run sends any due push (the Sunday talk, Monday Minute, Zero Hour, feed items) once only, runs queued GHL syncs,
  writes next week's Monday Minute when it's due, screens held comments, and retries pending sign-in sheets.

Variables (web and cron): `DJANGO_SECRET_KEY`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
`ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `GHL_LOCATION_ID`.
Monday Minute's AI runs on your own **ollama** service by default (see below). Set on web and cron:
`AI_PROVIDER=local`, `LOCAL_AI_URL=http://ollama.railway.internal:11434`, optionally `LOCAL_AI_MODEL` (default `qwen3:8b`),
`LOCAL_AI_REVIEW_MODEL` (a bigger model for the safety review only, e.g. `qwen3:14b`), `LOCAL_AI_THREADS` (set it to the
ollama service's vCPU limit) and `LOCAL_AI_TIMEOUT` (seconds per call, default 1800). To use Claude instead: `AI_PROVIDER=anthropic` and
`ANTHROPIC_API_KEY` (optional `MONDAY_MODEL`, default `claude-opus-5-5`). `MONDAY_MINUTE_ENABLED=0` stops writing new talks.

- **ollama** service (local AI, CPU only, since Railway has no GPUs): deploy the Docker image `ollama/ollama`.
  Run it in the same region as Postgres (us-west2). Add a volume mounted at `/root/.ollama` so the model downloads once,
  and set the variables `OLLAMA_HOST=[::]:11434` (listen on Railway's private network), `OLLAMA_KEEP_ALIVE=10m` (unload
  when idle, so memory and cost drop between runs) and `OLLAMA_NO_CLOUD=true` (no Ollama cloud models, so nothing leaves
  your servers). On web and cron, `LOCAL_AI_URL=http://${{ollama.RAILWAY_PRIVATE_DOMAIN}}:11434`. Don't give it a public domain: only web and cron talk to it, over the private network. The first cron run pulls
  the model (about 5 GB for `qwen3:8b`). While loaded it uses about 6 GB of memory; a talk takes several minutes on CPU.
Create the admin login once with `railway ssh` → `python manage.py createsuperuser`.

## Still to do before App Store submission
- App icon, splash art and store screenshots (current images are Expo placeholders).
- Paste the talk text for each issue in the admin, and clear the open pre-send flags in the topic ledger.
- Privacy policy URL and App Privacy answers (email, push token, crash data).
- Apple Developer account under Trainovate Technologies (D-U-N-S) and Google Play account.
