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

## Only you can do these (in order)

1. **Apple Developer Program** for Trainovate Technologies (needs the D-U-N-S number), then `npx eas-cli@latest init` and create the app record for `ai.trainovate.zeroharm`.
2. **Deploy the backend** on Railway: set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `ONESIGNAL_APP_ID`, `ONESIGNAL_REST_API_KEY`, `GHL_PRIVATE_TOKEN`, `INGEST_KEY`, `BACKOFFICE_KEY` on web and cron. It must stay up through review.
3. **Give the build its public values** in EAS (production environment): `EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_ONESIGNAL_APP_ID`, `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`. Without the first two the store build shows an empty app.
4. **Privacy policy and terms of use** on a public page. The policy must cover: email, name, company, crew names, signatures, crew photos, comments, ratings, push token, approximate location, the random install id, the anonymous daily usage count (once a day the app tells the server that a phone opened it, with the platform, app version and an approximate city, state and country; the place comes from the phone's approximate location when allowed, otherwise it is worked out from the network address, which is not stored; people can switch the count off in Settings), DB-IP as the source of the network place lookup, OneSignal, GoHighLevel, hosting, how long records are kept and how to ask for deletion. The terms need a no-tolerance line for abusive comments. Have a lawyer review both.
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
| Device ID (push id, hashed install id) | No | No | App functionality |
| Product interaction (thumbs, OTIS ratings, notification opens, the anonymous once-a-day app open count) | No | No | Analytics; app functionality |
| Coarse location (rounded to about 1 km for weather; city, state and country for the anonymous usage count) | No | No | App functionality; analytics |

## Notes for the reviewer (paste into App Store Connect)

- No account is needed. The first screen asks for a name and email for the free weekly newsletter. Tap "Not now" to skip it. Every feature works without signing in, and there is no password.
- A sign-up can be removed in the app, in Settings.
- Monday tab: this week's AI-written talk. Scroll down for thumbs, comments, Report and Block (the ••• on a comment) and the community rules shown before a first post. Comments are screened before they show, and reports are handled within 24 hours at the support address.
- Crew sign-in: Start crew sign-in, type a name, sign, optionally take a group photo, then Print or Share.
- OTIS: an AI assistant that runs on the phone. First use downloads a model over Wi-Fi. Questions never leave the phone.
- Notifications are off until turned on in Settings. "News and offers" is the only promotional one.
- The app gives general safety awareness. It is not legal, medical or compliance advice.

## Still open in code

- Removing a sign-up (name and email) in the app is done: a phone removes itself, and the sign-up goes when its last phone is removed. Still open: deleting your own comment and saved sign-in sheets from the server (today that is an email request), and deleting the GoHighLevel contact itself (removal takes the tags off and marks it; the contact is deleted by hand).
- An alert to you on every comment report (audit item A2), so the 24-hour promise does not depend on checking the dashboard.
- A reason picker on reports, a "Blocked people" list, and blocking agency words in display names (audit B6).
- The sign-in sheet note should say a contact record is created (audit E2). Wording needs the privacy policy first.
