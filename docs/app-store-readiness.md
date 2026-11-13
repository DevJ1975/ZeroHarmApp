# Zero Harm: App Store readiness (iPhone first)

**Date:** 2026-11-10. From a read-through of the app against Apple's review rules. No iPhone build has been run yet, so the
items under "Done in code" still need a check on a real build.

## Done in code

| Item | What changed |
|---|---|
| Push notifications in a store build | `app.config.js` switches OneSignal to Apple's production service when EAS builds the `production` profile. Development builds are unchanged. |
| Privacy manifest | `ios.privacyManifests` in `app.json` declares the required-reason APIs the app's libraries use, and that the app does no tracking. |
| Unused permission text | Location is "while using the app" and approximate only. The always-on, motion and full-accuracy strings are no longer added. |
| OTIS background download | Added the downloader's config plugin, which the "you can leave this screen" promise depends on. |
| iPad | `supportsTablet` is off for version 1. The app runs on iPad in iPhone size, and no iPad screenshots are needed. |
| Comments (rule 1.2) | Rules are built into the app so the box is never empty; the box says rule-breakers are removed and reports are handled in 24 hours; Block also sends a report. |
| AI and safety notes | OTIS chat shows "AI assistant, can be wrong, call 911"; Weekly talks say they add to training; Settings has an "About and privacy" section, including "not part of OSHA". |
| Settings | Privacy policy, Terms of use, Contact support and Delete my data rows appear once their addresses are set (see below). Settings is now reachable from the Monday tab. |
| Wording | Removed the hard-coded "January 3" date, the PDF mention when there is no PDF, and "your first issue arrives Sunday". |
| Simulator | `eas.json` has a `simulator` profile for an iPhone Simulator build. |
| Sign-in is optional (rule 5.1.1) | The welcome screen asks for a name and email and says the app is free, with a "Not now" link. Every feature works without signing in. No password and no email code. |
| Newsletter consent | One line under the button says they will get Zero Harm Weekly by email each week and can unsubscribe anytime. The server stores that line and the time. |
| Removing a sign-up in the app | "Remove my info" removes that phone from the sign-up (`POST /api/signups/remove/`). When it was the last phone linked to the email, the name and email are deleted from the server at once and the newsletter tags the app added come off in GoHighLevel. Tags the contact had before the app are left alone. A phone can never remove someone else's sign-up. |
| Privacy policy (2026-11-13) | Served by the backend at https://zero-harm-api.up.railway.app/privacy/ (new `backend/legal` app; also `/privacy` without the slash). Covers every item in the data inventory by feature, each outside party and what it gets, retention from the code (usage 400 days, removal record up to 7 days, PDFs cleared after the GHL copy), "Remove my info", deletion by email within 30 days, under 16, crew members, state rights. Effective November 13, 2026. |
| Terms of use (2026-11-13) | https://zero-harm-api.up.railway.app/terms/ . Free app, safety info is not a substitute for training or advice, not OSHA, AI can be wrong, call 911, the five community rules with the zero-tolerance line and 24-hour reports, permission to record people, license, warranty and liability limits, Nevada law. Linked from the comment rules box (`components/MondayMinuteView.tsx`) and Settings. |
| Production build values | `eas.json` `build.production.env` sets `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL` and `EXPO_PUBLIC_SUPPORT_EMAIL` (jamil@trainovations.com). |

## Only you can do these (in order)

1. **Apple Developer Program** for Trainovate Technologies (needs the D-U-N-S number), then `npx eas-cli@latest init` and create the app record for `ai.trainovate.zeroharm`.
2. **Deploy the backend** on Railway: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY`, `BACKOFFICE_KEY` on web and cron. It must stay up through review.
3. **Give the build its OneSignal app id.** `eas.json` now sets the API, privacy, terms and support values for production. Still missing: `EXPO_PUBLIC_ONESIGNAL_APP_ID` (not in the repo). Add it to `build.production.env` in `eas.json` or as an EAS environment variable. Without it, pushes do not work in the store build.
4. **Lawyer review of the privacy policy and terms.** Both pages are live once the backend deploys (`/privacy/`, `/terms/`). The points to confirm are marked `[LAWYER REVIEW]` in HTML comments in `backend/legal/templates/legal/privacy.html` and `terms.html`: how long to keep sign-in sheets as training records, crew photo and signature consent, the state law section, which AI provider production uses (`AI_PROVIDER`), the access-log wording for weather, warranty and liability wording, the $100 cap, Nevada venue and Apple's standard EULA terms. After any change, update `EFFECTIVE_DATE` / `LAST_UPDATED` in `backend/legal/views.py`. Enter the same URLs in App Store Connect.
5. **A support email** that someone reads daily. Apple expects comment reports to be acted on within 24 hours.
6. **Real content before review:** at least one approved Monday Minute (two or three is better), the text for Zero Harm Weekly issues 1 and 2, one alert and one Learn item. Empty screens are the most common rejection.
7. **Push:** upload an APNs key (.p8) to OneSignal and send a test push to a TestFlight build.
8. **App Store Connect listing:** 6.9-inch iPhone screenshots from the real build, description that says Monday Minute is AI-written and OTIS is an on-device AI assistant (no claim of OSHA compliance), support and privacy URLs, age rating with user-generated content declared, and the App Privacy answers below.
9. **Test on a real iPhone:** the OTIS download (0.5 to 1.3 GB) with the app in the background, crew sign-in, print and share, and the holiday opening screen.
10. **After approval:** set `APP_STORE_URL` (and `PLAY_STORE_URL` once Android is live) on the Railway web service. The invite link sent from GoHighLevel (`/get/?c={{contact.id}}`) then sends phones straight to the store, with no app update. Until then it shows "Coming soon".

## App Privacy answers

| Data | Linked to the person | Tracking | Purpose |
|---|---|---|---|
| Email address (now also asked for on the welcome screen; optional) | Yes | No | App functionality; marketing (the weekly newsletter, offers when turned on) |
| Name (now also asked for on the welcome screen; optional) | Yes | No | App functionality; marketing (the newsletter is addressed to them) |
| Photos (crew photo on a saved sheet) | Yes | No | App functionality |
| Other user content (signed sheets, comments, notes, suggestions, OTIS question if opted in) | Yes | No | App functionality; analytics |
| Device ID (push id, hashed install id) | Yes (the hashed install id is linked to the sign-up for people who signed in) | No | App functionality |
| Product interaction (thumbs, OTIS ratings, notification opens, the once-a-day app open count) | Yes (thumbs and the daily count carry the hashed install id) | No | Analytics; app functionality |
| Coarse location (rounded to about 1 km for weather; city, state and country for the daily usage count) | Yes (the daily count's city is stored with the hashed install id) | No | App functionality; analytics |

## Notes for the reviewer (paste into App Store Connect)

- No account is needed. The first screen asks for a name and email for the free weekly newsletter. Tap "Not now" to skip it. Every feature works without signing in, and there is no password.
- A sign-up can be removed in the app, in Settings.
- Monday tab: this week's AI-written talk. Scroll down for thumbs, comments, Report and Block (the ••• on a comment) and the community rules shown before a first post. Comments are screened before they show, reports are acted on within 24 hours (the owner is emailed on the first report of each comment), and a poster can be stopped from commenting from the admin.
- Crew sign-in: Start crew sign-in, type a name, sign, optionally take a group photo, then Print or Share.
- OTIS: an AI assistant that runs on the phone. First use downloads a model over Wi-Fi. Questions never leave the phone.
- Notifications are off until turned on in Settings. "News and offers" is the only promotional one.
- The app gives general safety awareness. It is not legal, medical or compliance advice.

## Still open in code

- Removing a sign-up (name and email) in the app is done: a phone removes itself, and the sign-up goes when its last phone is removed. Still open: deleting your own comment and saved sign-in sheets from the server (today that is an email request), and deleting the GoHighLevel contact itself (removal takes the tags off and marks it; the contact is deleted by hand).
- Done: an email to `OWNER_ALERT_EMAIL` on the first report of each comment (audit item A2; the cron resends it if GoHighLevel was down), and a per-phone comment ban ("Hide and stop the poster from commenting" in the comment admin; delete the ban row to lift it).
- A reason picker on reports, a "Blocked people" list, and blocking agency words in display names (audit B6).
- The sign-in sheet note should say a contact record is created (audit E2). The privacy policy now says it, so the in-app wording can follow.
- Privacy policy accuracy: gunicorn's access log (`backend/Dockerfile`) likely writes the weather lat/lon query string to Railway logs, and the sign-in sheet and suggestion rate limits key the cache on the raw IP (`backend/talks/views.py`). The policy describes both as they are. Turning off the access log and hashing those two keys would let it say less.
- Retention limits: only the usage count has one (400 days). Sign-in sheet records, comments, votes, reports, suggestions, OTIS ratings and invite taps are kept until deleted on request, as the policy says.
