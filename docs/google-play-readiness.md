# Zero Harm: Google Play readiness

**Date:** 2026-11-11. This is the owner's checklist for getting Zero Harm onto Google Play. It comes from an audit of
the app against Google's and Expo's pages as they read on that day, and from `app.json`, `app.config.js` and `eas.json`
as they are now. No Android store build has been made and nothing has been run on a real Android phone yet, so the
items under "Done in the repo" still need the checks in section 7.

The iPhone checklist is in `docs/app-store-readiness.md`. The privacy policy checklist there covers both stores.

## 1. Where things stand

| | |
|---|---|
| App package name | `ai.trainovate.zeroharm`. It is fixed for good by the first upload. |
| Done in the repo | Permissions, backup, notification icon, release build rules, the submit track, "Report this answer", problem reports and crash reports. |
| Waiting on you | The Google Play account, Firebase, the Play service account, public privacy and deletion pages, the App content forms, the foreground-service video and the store listing. |
| Waiting on the engineer | One line in `app.json` once you hand over the Firebase file, a package update, and the build and submit commands. |

## 2. Done in the repo

Each line was checked against the files today.

| Item | What is in place |
|---|---|
| Approximate location only | The Android build leaves out precise location (`ACCESS_FINE_LOCATION` is in `android.blockedPermissions` in `app.json`). The app only uses a rough position for weather. On the Data safety form answer "Approximate location", not "Precise". |
| No "read storage" permission | `READ_EXTERNAL_STORAGE` is left out too. |
| No "draw over other apps" permission | Tester and store builds (EAS profiles `preview` and `production`) leave out `SYSTEM_ALERT_WINDOW`. `app.config.js` adds it to the blocked list for those builds. A development build keeps it for React Native's developer tools. |
| "Write storage" stays, on purpose | `WRITE_EXTERNAL_STORAGE` is still in the build so the camera works for the crew photo on Android 7, 8 and 9. Newer Android ignores it. If Google asks, that is the reason. |
| Backup is off | `android.allowBackup` is `false`. Crew names, signatures, photos and the phone's install id are not copied to Google Drive, and reinstalling starts the app empty. A direct phone-to-phone transfer (by cable or Wi-Fi, when setting up a new phone) can still copy them on some phones: on Android 12 and later some makers keep that transfer on even when backup is off. Stopping it needs a data extraction rules file; see section 8. |
| OneSignal collects no location | `disableLocation` is on in the OneSignal plugin, so its location part is not built into the app. |
| Notification icon | `assets/images/ic_stat_onesignal_default.png` (white mark on clear, 96x96) with the accent colour `#F5C400`. |
| A paused OTIS download survives an update | Release builds keep the downloader's saved-state classes from being renamed (`extraProguardRules` in `app.json`). |
| Push uses the right service | `app.config.js` switches OneSignal to production when EAS builds the `production` profile. Nobody edits it by hand. |
| Where `eas submit` sends the build | The Internal testing track (`submit.production.android.track` in `eas.json`). Change it to `alpha` (closed testing) or `production` later. |
| Version numbers | EAS keeps the Android version code and raises it by one on every production build (`appVersionSource: remote`, `autoIncrement: true`). The app version is 1.0.0. |
| A way to flag an AI answer | Every finished OTIS reply has "Report this answer". Google's AI content rule asks for an in-app way to report AI output. It works whatever the "Help improve OTIS" switch says. |
| Problem reports and crash reports | Built, with a "Crash reports" switch in Settings (on by default). Both must now be declared on the Data safety form: see section 5. |

Already fine with no change, as found by the audit:

- **Target Android version.** Google asks for API level 36 for new apps. Expo SDK 58 builds for 36. Source: https://support.google.com/googleplay/android-developer/answer/11926878
- **16 KB memory pages.** Google blocks updates that do not support them from Feb 1, 2027. The test build of Nov 10 passed the check. Source: https://developer.android.com/guide/practices/page-sizes
- **App bundle.** The `production` profile makes the `.aab` file Play wants. The `preview` profile makes an `.apk` you can install on a phone.
- **No advertising id.** The build does not ask for it.
- **Size.** The whole test build was 168 MB, well under Google's limit.

## 3. Still to do in the repo (engineer)

| Item | Why |
|---|---|
| Add `"googleServicesFile": "./google-services.json"` under `"android"` in `app.json`, and put the file at the top of the repo | Android push needs Firebase: the key uploaded to OneSignal (step 4.3) is required, and OneSignal recommends shipping this file inside the app as well. It waits for you to make the file. The file must be committed, because EAS only uploads committed files, and its package name must be `ai.trainovate.zeroharm` or the build fails. |
| Run `npx expo install --fix`, then `npx expo-doctor` | At the last check 15 Expo packages were one small version behind. Do it before the store build, when nobody else is running tests. |
| Fix two lines in the app that say OTIS questions never leave the phone | The "Meet OTIS" screen and Settings → OTIS. They should say "unless you choose to send a problem report or flag an answer", to match the store answers. |
| Decide about OneSignal at first launch | OneSignal starts when the app first opens, before any notification is switched on, and records the device model, system, language, time zone, country, carrier, network address and session counts. Either declare that as required on the Data safety form (section 5 does), or hold OneSignal back until the first switch is turned on. |
| Check the permission list after any change to `app.json` or `app.config.js` | Run `EAS_BUILD_PROFILE=production npx expo config --type introspect --json` and read the `uses-permission` list. Check an EAS build, not a build made on a computer: a local build keeps "draw over other apps". |

## 4. Only you can do these (in order)

### 4.1 Google Play developer account, as an Organization

1. Go to https://play.google.com/apps/publish/signup
2. Choose **Organization**, for Trainovate Technologies. Not Personal.
3. Have ready: the D-U-N-S number (the same one Apple needs), the organisation's phone number, website, a contact name and email, and a card in the legal name for the US$25 one-time fee. You must verify your identity.
4. The legal name and address are shown publicly on the store page.

Why Organization: a Personal account made after Nov 13, 2023 must first run a closed test with at least 12 testers for 14 days in a row before it may publish. Google's pages apply that rule to personal accounts only. Sources: https://support.google.com/googleplay/android-developer/answer/13634885 and https://support.google.com/googleplay/android-developer/answer/14151465

### 4.2 Create the app in Play Console

1. Go to https://play.google.com/console
2. Click **Create app**.
3. Name: Zero Harm. Default language: English (United States). Type: **App**. Price: **Free**.

### 4.3 Firebase, and the upload to OneSignal (Android push needs both)

1. Go to https://console.firebase.google.com/ and create a project, or open the one you have.
2. **Project settings** (the gear) → **Cloud Messaging** tab. Check that **Firebase Cloud Messaging API (V1)** says Enabled. If it does not: the three-dot menu → **Manage API in Google Cloud Console** → **Enable**.
3. **Project settings** → **Service accounts** tab → **Generate new private key** → **Generate key**. A JSON file downloads. Keep it out of the repo and do not email it.
4. In the OneSignal dashboard: **Settings** → **Push & In-App** → **Google Android (FCM)** → **Select file**, pick that JSON → **Save & Continue**.
5. If OneSignal says "Invalid request": at https://console.cloud.google.com/iam-admin/iam give that service account the roles **Firebase Cloud Messaging API Admin** and **Firebase Viewer**, then try again.
6. Back in Firebase: **Project settings** → **General** → **Your apps** → **Add app** → the Android icon. Package name: `ai.trainovate.zeroharm`. Download `google-services.json` and give it to the engineer (first row of section 3).

Source: https://documentation.onesignal.com/docs/en/android-firebase-credentials.md

### 4.4 A Play service account, so `eas submit` can upload for you

1. Go to https://console.cloud.google.com/projectcreate and make a project, or reuse the Firebase one.
2. Go to https://console.cloud.google.com/iam-admin/serviceaccounts → **Create Service Account** → give it a name → **Create** and close. Copy its email address.
3. On that account: the three-dot menu → **Manage keys** → **Create new key** → **JSON** → **Create**. A second JSON file downloads. Keep it out of the repo too.
4. Go to https://console.cloud.google.com/apis/library/androidpublisher.googleapis.com and click **Enable**.
5. Go to https://play.google.com/console/users-and-permissions → **Invite new users** → paste the service account's email → **App permissions** tab → select Zero Harm and tick:
   - View app information (read-only)
   - Edit and delete draft apps
   - Release to production, exclude devices, and use Play App Signing
   - Release apps to testing tracks
   - Manage testing tracks and edit tester lists
   - Manage store presence

   Then **Invite user**.
6. Give the key to Expo: the Expo dashboard → the Zero Harm project → **Credentials** → **Android** → `ai.trainovate.zeroharm` → **Service credentials** → **Add a Google service account key** → **Upload new key** → **Save**. (Or the engineer does it from the command line, step 5 in section 6.)

Source: https://github.com/expo/fyi/blob/main/creating-google-service-account.md

### 4.5 Signing

Nothing to prepare. The first Android build asks to make a signing key and Expo keeps it. On the first release, Play signs the app with its own key by default.

### 4.6 Public pages and a mailbox

Google needs these to exist before review:

- A **privacy policy** page. The checklist of what it must cover is in `docs/app-store-readiness.md`, and it now includes crash reports, problem reports, that reports reach GoHighLevel, and Hugging Face.
- A **terms of use** page, with a no-tolerance line for abusive comments.
- A **support email** that someone reads every day.
- A **public web page where someone can ask for their data to be deleted** without opening the app. It must name the app or the developer. The server has no such page today, so it has to be made on the Trainovate website. Google does not count "deactivate" as deletion. Sources: https://support.google.com/googleplay/android-developer/answer/13327111

Then give the three addresses to the engineer to set in EAS (step 2 in section 6): `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`, `EXPO_PUBLIC_SUPPORT_EMAIL`. On Nov 11 they were not set. Without them the app hides its Privacy policy, Terms of use, Contact support and Delete my data buttons, and Google requires the privacy link inside the app as well as on the listing.

### 4.7 The App content forms

In Play Console: **Policy and programs** → **App content**. Source: https://support.google.com/googleplay/android-developer/answer/9859455

| Form | Answer |
|---|---|
| Privacy policy | Paste the address of the privacy page. |
| Ads | No. |
| App access | All functionality is available without signing in. |
| Target audience | 18 and over only. |
| Content ratings | Fill in the questionnaire. Say that people can post content others see (the comments). No purchases. No location shared with other people. |
| Data safety | Section 5 below. |
| Health apps | Every app must fill this in, even with no health features. Workplace safety training is not on Google's list of health categories. Heat illness and first-aid content is the grey area. If you declare no health features, keep medical claims out of the listing. If you declare one, the description must say the app is not a medical device. |
| Foreground service | Required: see 4.8. |
| Advertising ID | No. |
| Countries | United States only. Weather comes from the US National Weather Service and the emergency number in the app is 911. |

What Google's reviewers may look at, and where the app stands:

- **Comments.** Google wants rules people accept before posting, moderation, a way to report content and people, and a way to block. The app has the rules step, screening before a comment shows, Report, Block (which also reports) and auto-hide after two reports. Still missing: a public terms page with the no-abuse line (4.6), an alert to you on each report, and a "Blocked people" list. Source: https://support.google.com/googleplay/android-developer/answer/9876937
- **AI content.** Monday Minute is written by AI without a person typing a prompt, so it sits outside Google's AI content rule; say it is AI-written in the listing. OTIS is covered by "Report this answer". Source: https://support.google.com/googleplay/android-developer/answer/13985936
- **OSHA.** Claiming to be part of government is not allowed. Settings already says Trainovate is not part of OSHA; say it in the listing too. Source: https://support.google.com/googleplay/android-developer/answer/9888077
- **911.** The button opens the phone's dialer. The app asks for no call permission.
- **The OTIS download.** Google forbids downloading program code from outside Play. OTIS downloads model data that the code already inside the app reads, not code. The foreground-service form and video below are the real requirement.

### 4.8 The foreground-service video

The OTIS download keeps running when the app is in the background, and on Android that uses a "foreground service" of the kind "data sync". Google makes every app that uses one describe it and link a short video.

1. On the App content page, open **Foreground service permissions**.
2. Pick the type **Data sync**, and the use that fits: network transfer, download.
3. Describe it in one or two plain sentences: "A person taps to download the OTIS assistant's model, 0.5 to 1.3 GB, once. The download carries on with a progress notification if they leave the app."
4. Record a video on a real Android phone that shows a person tapping to start the OTIS download, then the progress notification while the app is in the background. Put it somewhere Google can open it (an unlisted YouTube link works) and paste the link.

Source: https://support.google.com/googleplay/android-developer/answer/13392821

### 4.9 Store listing

| Asset | Size and rules | State |
|---|---|---|
| App icon | 512 x 512, 32-bit PNG, at most 1024 KB | To make. Export it from `assets/images/icon.png` (1024 x 1024). |
| Feature graphic | 1024 x 500, JPEG or 24-bit PNG with no transparency | To make. |
| Phone screenshots | At least 2, at most 8. JPEG or 24-bit PNG. Each side 320 to 3840 px, and the long side at most twice the short side. 1080 x 1920 upright or better gets the app onto Google's recommendation pages. | To take, from the real Android build. |
| Tablet screenshots | Optional. If you give any, at least 4, sides 1080 to 7680 px. | Skip for version 1. |
| Short description | At most 80 characters | To write. |
| Full description | Say that Monday Minute is written by AI, that OTIS is an AI assistant that runs on the phone and can be wrong, that OTIS needs a one-time download of 0.5 to 1.3 GB, that the app gives general safety awareness, and that Trainovate is not part of OSHA. Do not say "official" or "OSHA compliant". | To write. |
| Support email | The mailbox from 4.6 | To set. |

Source for the sizes: https://support.google.com/googleplay/android-developer/answer/9866151

### 4.10 After approval

On Railway, on the web service, set `PLAY_STORE_URL=https://play.google.com/store/apps/details?id=ai.trainovate.zeroharm`. The invite link sent from GoHighLevel then sends Android phones straight to the store, with no app update.

**Changing a variable restarts the web service.** A Monday Minute safety test running at that moment stops and its hours are lost. Check the admin (*Monday Minute safety test runs*) first, and set it when none is running. See "Changing a Railway variable" in the README.

## 5. Data safety form: proposed answers

Google's rules, in short: "collected" means sent off the phone. Data that stays on the phone is not collected. Sending data to a company that only works for you (a service provider) is not "sharing". Data collected by a library inside the app counts as yours. A network address used to work out a place counts as location. Source: https://support.google.com/googleplay/android-developer/answer/10787469

**Answers for the whole form**

| Question | Answer |
|---|---|
| Does the app collect or share any of the required data types? | Yes. |
| Is all data encrypted in transit? | Yes. |
| Do you provide a way to ask for data to be deleted? | Yes: "Remove my info" in Settings, the "Delete my data" email, and the public page from 4.6. |
| Is data shared with third parties? | No. OneSignal, GoHighLevel, Railway and the AI that screens comments work for Trainovate as service providers. Check that each contract says so. |

**Answers by kind of data.** Changed since the audit: crash logs and diagnostics are now collected, problem reports are new, and an OTIS question can now leave the phone through "Report this answer".

| Data in the app | Google's data type | Collected | Shared | Purpose | Optional or required | Can it be deleted |
|---|---|---|---|---|---|---|
| Email: sign-in, talk ideas, the supervisor's email on a saved sheet, and a problem report when the person wants a reply | Personal info: Email address | Yes | No | App functionality; Developer communications; Advertising or marketing (the newsletter, offers) | Optional | In the app (Remove my info, from the phone that signed up) and by request |
| Name: sign-in, the name shown with a comment, the supervisor's name | Personal info: Name | Yes | No | App functionality; Developer communications | Optional | Same. Comment names by request only |
| Company | Personal info: Other info | Yes | No | App functionality | Optional | By request |
| Crew names on a saved sheet | Personal info: Name; Files and docs | Only when "Save sheet to my records" is tapped | No | App functionality | Optional | By request only (email) |
| Finger signatures on a saved sheet | Files and docs (the PDF); App activity: Other user-generated content | Same | No | App functionality | Optional | By request only |
| Crew photo on a saved sheet | Photos and videos: Photos | Same | No | App functionality | Optional | By request only |
| Comments, replies, talk ideas, notes with a thumbs down | App activity: Other user-generated content | Yes | No (comments are public inside the app) | App functionality; Analytics | Optional | By request only |
| **Problem reports:** what the person writes about a problem with the app, and their email if they give one for a reply | App activity: Other user-generated content | Yes, when the person sends one | No | App functionality (support) | Optional | By request (the "Delete my data" email). They stay until deleted. They are tied to the person: kept with the phone's install id, the same one kept with a sign-up, and they may hold an email |
| **An OTIS question and answer:** only when the person taps "Report this answer" and confirms, or has both OTIS switches on in Settings | App activity: Other user-generated content | Yes, only then | No | App functionality; Analytics | Optional | By request. A flagged answer is kept with the phone's install id, so it can be matched to a sign-up from that phone |
| Thumbs, thumbs-down reasons, OTIS "Was this helpful?" ratings, notification opens | App activity: App interactions | Yes | No | Analytics; App functionality | Optional | By request. Thumbs are stored under the same scrambled install id as a sign-up, so for someone who signed in they can be matched to them (see section 8) |
| **Crash logs:** the error, where in the app's code it happened, the screen, the time, and whether the app could carry on | App info and performance: Crash logs | Yes | No | Analytics (finding and fixing bugs) | Optional: the "Crash reports" switch in Settings, on by default | Single reports are deleted after 90 days. Not tied to a person: kept under a scrambled id made for crash reports only, which does not match the id of a sign-up or a problem report |
| **Diagnostics:** phone model, Android version and app version, sent with a crash report, a problem report or a flagged answer | App info and performance: Diagnostics | Yes | No | Analytics; App functionality | Optional (it only goes with a report) | Same as the report it came with: deleted after 90 days with a single crash report; kept with a problem report or flagged answer until deleted on request |
| Push token and OneSignal's subscription id, plus what OneSignal records by itself: device model, system, language, time zone, country, carrier, network address, session count and length | Device or other IDs; App activity: App interactions | Yes, from first launch | No | App functionality; Developer communications | Required as built (see section 3) | By request |
| Approximate location: position rounded to about 1 km for weather; city, state and country kept with the daily count; the place worked out from the network address when location is not allowed | Location: Approximate location | Yes. The weather lookup is not kept; the city-level place is | No | App functionality; Analytics | Optional (the permission prompt; the usage switch) | Rows are deleted after 400 days (`USAGE_KEEP_DAYS`). The place is kept under the same scrambled install id as a sign-up, so for someone who signed in it can be matched to them (see section 8) |
| The phone's random install id. The server keeps only a scrambled form. It goes with the once-a-day count, votes, comments, sign-in, crash reports and problem reports | Device or other IDs | Yes | No | Analytics; App functionality; Fraud prevention, security and compliance (one vote per phone, limits) | The daily count and crash reports are optional; the id is required when voting, commenting, signing in or sending a report | By request. Tied to the person once they sign in: the scrambled id is kept with their name and email. Crash reports use a separate scrambled id |

Not collected: precise location, contacts, calendar, messages, health and fitness data, financial data, web browsing, audio, and the advertising id.

What the listing and the privacy policy must agree with:

- Crash reports hold no name, email, typed text, photo, location or OTIS chat, and are kept under their own scrambled id, so they cannot be matched to a person. They are on by default and can be switched off.
- Problem reports and flagged answers can be matched to a person: they are kept with the install id that a sign-up from the same phone also has, and a problem report may hold an email.
- OTIS questions stay on the phone unless the person chooses to send a problem report or flag an answer, or turns on both OTIS switches.
- OTIS's model files download from Hugging Face, which sees the phone's network address during the download.
- "Save sheet to my records" sends the PDF with its signatures and photo to Trainovate, filed under the email typed.

## 6. Build and submit (engineer, in this order)

Run from the top of the repo. Nothing here has been run yet.

```sh
# 1. After the items in section 3: bring packages into line and check
npx expo install --fix
npx expo-doctor
npx expo lint && npx tsc --noEmit && npm test

# 2. Public values for tester and store builds (the owner supplies the real addresses)
npx eas-cli@latest env:set --name EXPO_PUBLIC_PRIVACY_URL   --value <https address> --environment production --environment preview --visibility plaintext
npx eas-cli@latest env:set --name EXPO_PUBLIC_TERMS_URL     --value <https address> --environment production --environment preview --visibility plaintext
npx eas-cli@latest env:set --name EXPO_PUBLIC_SUPPORT_EMAIL --value <email address> --environment production --environment preview --visibility plaintext
npx eas-cli@latest env:list production

# 3. A build to install on a phone (.apk). The first run asks to make the Android signing key: answer yes.
npx eas-cli@latest build --platform android --profile preview

# 4. The store build (.aab). The version code comes from EAS and goes up by one each time.
npx eas-cli@latest build --platform android --profile production

# 5. Once only: attach the Play service account key from 4.4
#    (production > Google Service Account > Manage your Google Service Account Key for Play Store Submissions > Set up ...)
npx eas-cli@latest credentials --platform android

# 6. Upload to Play. This makes the Internal testing release.
npx eas-cli@latest submit --platform android --profile production --latest

# Later releases, in one step:
npx eas-cli@latest build --platform android --profile production --auto-submit
```

Sources: https://docs.expo.dev/submit/android.md, https://docs.expo.dev/eas/environment-variables.md, https://docs.expo.dev/build/automate-submissions.md

After step 6, in Play Console: finish App content and the listing, add testers to Internal testing, then promote the release to closed testing and on to production.

## 7. Test on a real Android phone

Install the build from step 3 and check these before making the store build.

- [ ] **OTIS download:** start it, put the app in the background, watch the progress notification, and let it finish. Start another, force-stop the app, open it again and check the download picks up. Record the video for 4.8 while you are here.
- [ ] **OTIS answers** a question once it is set up, and "Report this answer" under the reply asks first and then says it was sent.
- [ ] **Push:** send a test push from OneSignal. It arrives, shows the Zero Harm icon (not a plain bell), and opens the right screen.
- [ ] **Crew sign-in:** sign with a finger, take the crew photo with the camera, print, share, and "Save sheet to my records".
- [ ] **Weather:** the prompt asks for approximate location only, and the weather card shows.
- [ ] **Keyboard:** on the OTIS chat, the comment box, the welcome screen and the Report a problem form, the keyboard does not cover what you are typing or the Send button.
- [ ] **Report a problem:** send one with signal and one in airplane mode. The second says "Saved on this phone. It will send when you have signal." and goes out when the app next comes to the front. Both show under My reports, and a reply typed in the admin or the console shows there.
- [ ] **Crash reports:** turn the switch off and on in Settings → About and privacy. If the error screen ever shows, check that it reads well, that "Try again" works, and that "Report this problem" opens the form.
- [ ] **Permissions:** in the phone's Settings → Apps → Zero Harm, the location permission offers approximate only, and Zero Harm is not listed under "Display over other apps".
- [ ] **A reinstall starts empty** (backup is off): delete the app, install it again, and check no old sheets or sign-in come back. This does not test a phone-to-phone transfer, which can still copy them on some phones (section 8).

On the store build from step 4, the engineer also confirms the 16 KB check on the real bundle: `bundletool dump config --bundle=<file>.aab | grep alignment` should show `PAGE_ALIGNMENT_16K`.

## 8. Not verified

- **Nothing has been run on a real Android phone.** The release build, OTIS loading, resumed downloads, OneSignal, the error screen, the report form and the crash reporter have been checked by reading code and by automated tests only.
- **Phone-to-phone transfer still copies the app's data on some phones.** Google's Auto Backup page says that for apps aimed at Android 12 or later, some makers' phones keep the device-to-device transfer on when `allowBackup` is `false`. The build has no `dataExtractionRules`, so such a transfer can copy the saved sheets and the install id to a new phone. Follow-up for the engineer: a small config plugin that adds a data extraction rules file excluding everything under both `<cloud-backup>` and `<device-transfer>`. Source: https://developer.android.com/identity/data/autobackup
- **The crash-report id.** The Data safety answers above say crash reports cannot be matched to a person. That holds only once the server keeps them under their own scrambled id and clears the first phone's details on a crash ticket after `SUPPORT_CRASH_KEEP_DAYS` (90 days). Both are in the code now (`crash_hash` in `backend/support/api.py`, and `support_prune`). Check that this is in the deployed server before you send the form.
- **Thumbs and the daily count share the sign-up's scrambled id.** For anyone who signed in, votes and the once-a-day open count can be matched to their name and email, and so can the city, state and country kept on that day's count. Either give them their own id in code, as crash reports have, or say so in the privacy policy. The App Store answers for these (Product interaction and Coarse location) are "Yes, linked" until the code changes.
- **The permission list of a real EAS build.** The settings are right in `app.json` and `app.config.js`; the list inside a built app has not been read since they changed. The test build of Nov 10 is older than these changes.
- **Whether the dev build still works** with the changed permissions, and whether the camera works on Android 7 to 9.
- **The first upload.** Expo's page says `eas submit` makes the first release itself on the Internal testing track. If Google refuses it because the app's setup is not finished, add `"releaseStatus": "draft"` to the submit profile in `eas.json` and finish the release in Play Console.
- **Keyboard behaviour** on Android 15 and 16, where the app draws edge to edge. It needs the check in section 7.
- **The 16 KB check** was done on the Nov 10 test build made on this Mac, not on an EAS store build.
- **How Google will class the app.** Whether its reviewers see OTIS as a main chatbot feature (the "Report this answer" control covers that case), and whether they see heat and first-aid content as a health feature.
- **Which Data safety type fits a problem report.** "Other user-generated content" is proposed. "Messages: Other in-app messages" is the other candidate.
- **Service provider status.** That the contracts with OneSignal, GoHighLevel, Railway and the comment-screening AI make them service providers, and that Railway does not keep request addresses (the weather position travels in the address of the request).
- **Google's exact questionnaire wording** for the content rating, and the length limits for the title and full description, were not on the pages that could be read.
- **Giving EAS the Firebase file without committing it** (as an EAS file variable) was not looked into. The plan above commits it.
- **Which public values are set in EAS today.** On Nov 11 only `EXPO_PUBLIC_API_URL` and `EXPO_PUBLIC_ONESIGNAL_APP_ID` were set for production. Step 2 in section 6 ends with a command that lists them.
- **Google's and Expo's rules were read on Nov 11, 2026.** They change. Open the links before you rely on a number.
