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

## Only you can do these (in order)

1. **Apple Developer Program** for Trainovate Technologies (needs the D-U-N-S number), then `npx eas-cli@latest init` and create the app record for `ai.trainovate.zeroharm`.
2. **Deploy the backend** on Railway: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY`, `BACKOFFICE_KEY` on web and cron. It must stay up through review.
3. **Give the build its public values** in EAS (production environment): `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_ONESIGNAL_APP_ID`, `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`. Without the first two the store build shows an empty app.
4. **Privacy policy and terms of use** on a public page. The policy must cover: email, name, company, crew names, signatures, crew photos, comments, ratings, push token, approximate location, the random install id, OneSignal, GoHighLevel, hosting, how long records are kept and how to ask for deletion. The terms need a no-tolerance line for abusive comments. Have a lawyer review both.
5. **A support email** that someone reads daily. Apple expects comment reports to be acted on within 24 hours.
6. **Real content before review:** at least one approved Monday Minute (two or three is better), the text for Zero Harm Weekly issues 1 and 2, one alert and one Learn item. Empty screens are the most common rejection.
7. **Push:** upload an APNs key (.p8) to OneSignal and send a test push to a TestFlight build.
8. **App Store Connect listing:** 6.9-inch iPhone screenshots from the real build, description that says Monday Minute is AI-written and OTIS is an on-device AI assistant (no claim of OSHA compliance), support and privacy URLs, age rating with user-generated content declared, and the App Privacy answers below.
9. **Test on a real iPhone:** the OTIS download (0.5 to 1.3 GB) with the app in the background, crew sign-in, print and share, and the holiday opening screen.

## App Privacy answers

| Data | Linked to the person | Tracking | Purpose |
|---|---|---|---|
| Email address | Yes | No | App functionality; marketing (newsletter, offers when turned on) |
| Name | Yes | No | App functionality |
| Photos (crew photo on a saved sheet) | Yes | No | App functionality |
| Other user content (signed sheets, comments, notes, suggestions, OTIS question if opted in) | Yes | No | App functionality; analytics |
| Device ID (push id, hashed install id) | No | No | App functionality |
| Product interaction (thumbs, OTIS ratings, notification opens) | No | No | Analytics; app functionality |
| Coarse location (rounded to about 1 km for weather) | No | No | App functionality |

## Notes for the reviewer (paste into App Store Connect)

- No login. Every feature works without signing up.
- Monday tab: this week's AI-written talk. Scroll down for thumbs, comments, Report and Block (the ••• on a comment) and the community rules shown before a first post. Comments are screened before they show, and reports are handled within 24 hours at the support address.
- Crew sign-in: Start crew sign-in, type a name, sign, optionally take a group photo, then Print or Share.
- OTIS: an AI assistant that runs on the phone. First use downloads a model over Wi-Fi. Questions never leave the phone.
- Notifications are off until turned on in Settings. "News and offers" is the only promotional one.
- The app gives general safety awareness. It is not legal, medical or compliance advice.

## Still open in code

- A server-side "delete my data" endpoint and deleting your own comment (today it is an email request).
- An alert to you on every comment report (audit item A2), so the 24-hour promise does not depend on checking the dashboard.
- A reason picker on reports, a "Blocked people" list, and blocking agency words in display names (audit B6).
- The sign-in sheet note should say a contact record is created (audit E2). Wording needs the privacy policy first.
