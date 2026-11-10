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
- **Inspect, Report, Learn:** placeholders for the first updates.

Run it:
1. `npm install`
2. Copy `.env.example` to `.env`; set `EXPO_PUBLIC_API_URL` to the Railway URL and `EXPO_PUBLIC_ONESIGNAL_APP_ID`.
3. OneSignal and the signature pad need native code, so use a development build, not Expo Go:
   `npx eas-cli@latest build --profile development --platform ios`, then `npx expo start`.
4. Before the store build, change `onesignal-expo-plugin` mode in `app.json` to `production`.

## The backend (Django 5.2 LTS, Postgres, Docker, Railway)
- `GET /api/talks/` released talks, newest first. A talk stays hidden until its Sunday 11:59 AM Pacific send time.
- `GET /api/talks/<issue>/` one talk. `POST /api/signups/` optional email sign-up (rate limited), synced to GoHighLevel with tags `zero-harm-app`, `zero-harm-weekly`, and `zero-harm-offers-optin` when they opt in.
- `/admin/` edit talk text, PDF and image links, see sign-ups, send a push or retry a GHL sync by hand.
- All 52 issues of 2027 load automatically on the first migrate.
- `python manage.py cron` sends any due Sunday push (once only) and retries pending GHL syncs.

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
- **cron** service: same repo and root, start command `python manage.py cron`, schedule `59 18,19 * * 0`
  (Sundays at 18:59 and 19:59 UTC, which covers 11:59 AM Pacific in both summer and winter time).

Variables (web and cron): `DJANGO_SECRET_KEY`, `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
`ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `GHL_LOCATION_ID`.
Create the admin login once with `railway ssh` → `python manage.py createsuperuser`.

## Still to do before App Store submission
- App icon, splash art and store screenshots (current images are Expo placeholders).
- Paste the talk text for each issue in the admin, and clear the open pre-send flags in the topic ledger.
- Privacy policy URL and App Privacy answers (email, push token, crash data).
- Apple Developer account under Trainovate Technologies (D-U-N-S) and Google Play account.
