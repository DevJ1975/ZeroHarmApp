# OTIS knowledge base: app help review

**Content:** `backend/talks/migrations/0021_seed_support_kb.py` (28 new entries, plus the six app help entries from the first seed)
**Checked against:** the app's own code on 2026-11-11 (branch `merge-console-into-holiday`, on top of commit 213971f), first before the support screens were built and again after they were (Report a problem, My reports, the Crash reports switch and the error screen are all in the tree now). Every line under "Confirmed in" was found by searching that file for the words the entry uses. Line numbers are from the second check; later edits move them, so if one is off, search the file for the words.
**Tests:** `backend/talks/tests_kb_support.py`
**To change an entry:** edit it in the console (Knowledge base) or in the admin. The seed never overwrites wording you changed.

## What this is

- **Type:** fixes for problems with the app itself: it closed, OTIS will not download, a sheet will not send. It is not
  safety content. These entries have `kind = "support"` ("App help" in the admin and the console).
- **How it is shown:** word for word. A support entry never goes through the on-device model and is never mixed into a
  safety answer. So each one has to read well exactly as written.
- **Shape:** one problem per entry. A title in the words a worker would type. Then 2 to 6 short numbered steps, each on
  its own line, under 700 characters in all. The search words hold what people really type, in English and in Spanish
  without accents (every entry is sent as English, so a Spanish question can only find it through these words).
- **Perimeter:** no OSHA section numbers (the weekly OSHA sync would treat one as a rule the entry depends on, and the
  admin and console now refuse it). No setting that is not in the app. Where a problem cannot be fixed on the phone,
  the entry says so and says to report it. Nothing here stands between a person and 911.

## Verdict

The entries are true to the app as it stands today, with three things to settle before release:

1. **Contact support and Delete my data only show when a support email is set** (`EXPO_PUBLIC_SUPPORT_EMAIL`). It is not
   set in `.env` on this machine. Three entries send people to those buttons. Set the address in the release build, or
   those steps point at nothing.
2. **The entries are in English only.** A Spanish question finds the right entry through its search words, and then
   shows English steps. Real Spanish entries need a translator and a language field on the table (ROADMAP row O4).
3. **Two entries tell people to type "report a problem" to OTIS, and that does not start a report.** OTIS starts one
   only when the words name the app, like "report an app problem" (owner check 15). Change those steps in the seed.

Three older entries are rewritten here. Two had drifted from the app: one named a "Share the PDF" button that is now
"Email or share the PDF", and one sent people to the Learn tab for a link that is on Today. The third (Finding past
talks) was still true; it is now numbered steps and also says where past Monday Minutes are.

> **The support screens are in the tree now.** When this record was first written, Report a problem, My reports, the Crash reports switch and the error screen's Try again did not exist yet, and the entries used the names from the design. All four now exist with those exact words (`app/settings.tsx`, `app/report.tsx`, `app/my-reports.tsx`, `components/CrashScreen.tsx`), and the lines below point at them. One name was wrong: the report form's button is **Send report**, not Send. Step 4 of "How to report a problem and see the reply" now reads "Tap Send report (in OTIS, tap Send)." Check that the seed (`0021_seed_support_kb.py`) says the same before release. The screens have still only been checked by automated tests, so read these entries against them on a phone once.

## For the owner to check

These are the points I could not settle from the code alone, or that are your call.

| # | Entry | What to check |
|---|---|---|
| 1 | Who to contact for help; Deleting your data; What Save sheet to my records does | They say "tap Contact support in Settings" and "tap Delete my data in Settings". Both buttons are hidden until `EXPO_PUBLIC_SUPPORT_EMAIL` is set (`app/settings.tsx`, `config.supportEmail !== ''`). Set it for release. |
| 2 | What Save sheet to my records does | "To ask for a copy later, tap Contact support." The app tells people a saved sheet goes to Trainovate "so you can download it later", but there is no screen to download one. Confirm you will send a copy when asked, or change this line. |
| 3 | OTIS will not download; Not enough space | "About 500 MB to 1.3 GB" are the two built-in model sizes (510 MB and 1,300 MB). If you pin a model release of another size in the admin, change the entries. The button always shows the true size. |
| 4 | OTIS will not download | "OTIS keeps the download" and "open OTIS again" rest on the download library picking up where it stopped. The library says it does, and the app's own screen says the same, but I did not run a download on a phone. |
| 5 | The app looks different: the holiday look | "In 2026 it starts on November 10" is true this year only. Take that sentence out in January 2027. |
| 6 | Changing your name or email | The app has no edit box once you are signed in, so the entry says: Remove my info, then sign in again with the new details. On the first phone that deletes the sign-up and makes a new one (the newsletter tags come off and go back on). Confirm that is what you want people to do. |
| 7 | Removing your info | "You see We got your request" is the start of the line in `lib/account.ts` (`REMOVAL_PENDING_LINE`) for a phone that did not make the sign-up. Settings shows it after Remove my info (`removalLine` in `lib/account.ts`). Check it on a phone. |
| 8 | What a crash report sends | It says a crash report carries "a random id for this copy of the app, and the server keeps only a scrambled form of it". That is what the code does. The store answers now say a crash report cannot be matched to a person, because the server keeps it under a scrambled id made for crash reports only (not the one kept with a sign-up). The entry stays true either way. Make sure the privacy policy says the same. |
| 9 | How to flag a wrong OTIS answer | It does not say where to see what became of a flag, because there is nowhere: "My reports" lists problem reports only, and a reply written on a flagged answer is a private note the person never sees. Do not add a step that promises one. |
| 10 | No Monday Minute is showing | "As late as Wednesday morning" is the server's rule: a late talk stays owed until Wednesday 5:00 AM Pacific, then you get an email. If you change that rule, change the entry. |
| 11 | Notifications are not arriving | Step 5 (Do Not Disturb or Focus) is about the phone, not the app. It is ordinary advice and true of every app, but nothing in our code confirms it. |
| 12 | Spanish is not offered | "Ask OTIS in Spanish and it tries to answer in Spanish." OTIS is told to; a small model does not always manage. "Tries" is the honest word. |
| 13 | All entries | A Spanish speaker gets English steps. See the verdict. |
| 14 | Regulatory alerts; Zero Harm Weekly; What OTIS is | These three older entries are descriptions, not numbered steps. They are still true and were left in their own words. "What OTIS is" gained one sentence: "Your questions stay on the phone unless you choose to report a problem or report an answer." |
| 15 | How to report a problem and see the reply; OTIS says it does not have that | Fixed in the seed: both steps now say "type report an app problem" (or point to Settings, Report a problem). Typing only "report a problem" does not start a report, on purpose: at a plant that usually means a hazard for a supervisor (`ASKS_FOR_SUPPORT` in `lib/support/intent.ts`). |
| 16 | Deleting your data | Fixed in the seed: step 2 now lists "sign-ups, saved sign-in sheets, suggestions, comments and problem reports", matching the email Delete my data opens (`app/settings.tsx`). |

## Found while checking (not wording, but worth knowing)

- **An unfinished sign-in sheet cannot be reopened.** If a supervisor leaves the Crew sign-in screen before tapping Save
  sheet to my records, Print the sheet or Email or share the PDF, the signatures stay in the phone's database but no
  screen leads back to them. The entry "I left crew sign-in before saving the sheet" says so plainly. A "continue this
  sheet" link would remove the problem.
- **How-to questions need a way in.** The six older entries (how to run a talk, finding past talks, what OTIS is and so
  on) are now app help, and the phone only looks at app help when a message reads like a problem ("not working",
  "report a problem"). "How do I find past talks?" is not a problem, so unless the phone also tries app help when the
  safety search finds nothing, OTIS will say it does not have that. Raised with the phone work.
- **Small words can pull a weak match.** In the phone's support search, "the app has a problem" matches on "has" and
  "the video won't play" on "play" (Google Play). Adding words like has, have, got, out, use and play to the list of
  words it ignores would stop that. Raised with the phone work.
- **A suggestion is not saved for later.** Unlike sheets, votes and sign-ups, "Send my idea" needs a signal at that
  moment. The corrected entry says so.

## The new entries

Each block is the entry exactly as seeded: title, text, search words, then where each fact was confirmed.

### The app closed, crashed or froze

```text
If the app crashes, gets stuck or keeps closing, close it all the way and open it again. Talks and saved sign-in sheets stay on this phone.
1. Swipe Zero Harm away from your open apps, then open it again.
2. If you see a screen with Try again, tap it.
3. If it keeps happening, update Zero Harm from the App Store or Google Play.
4. Tell us what you tapped just before it closed: open Settings (top of the Today tab) and tap Report a problem.
```

**Search words:** crash, crashing, frozen, freeze, stuck, app stuck, closes, quit, black screen, won't open, not working, stopped working, broken, se cierra, se cerro, se congela, se traba, no funciona, no abre, falla

*442 characters.* Confirmed in:

- Talks and sheets are kept on the phone: `components/HowTo.tsx:44`
- A signature is written to the phone the moment Save signature is tapped, so a later crash does not lose it: `lib/signins.ts:43`
- The error screen offers Try again: `components/CrashScreen.tsx:104`
- Settings has Report a problem: `app/settings.tsx:258`
- Why the entry does not promise a crash report was sent: `lib/support/crash.ts:5`

### The app shows old content or will not update

```text
With no signal the app shows the copy saved on the phone. You may see No signal. Showing the copy saved on this phone.
1. Move to where you have signal or Wi-Fi.
2. On the Monday or Today tab, pull down to refresh.
3. Or close the app all the way and open it again.
4. To get the newest version of the app, update Zero Harm from the App Store or Google Play.
5. Still old with a good signal? Open Settings and tap Report a problem.
```

**Search words:** old, outdated, out of date, not updating, won't update, updates, old talk, refresh, reload, no signal, offline, viejo, no se actualiza, no actualiza, actualizar, actualizado, sin senal, recargar

*431 characters.* Confirmed in:

- The exact no-signal line: `components/ui.tsx:60`
- Pull down to refresh on the Monday tab: `app/(tabs)/index.tsx:45`
- The same when a Monday Minute is showing: `components/MondayMinuteView.tsx:78`
- Pull down to refresh on the Today tab: `app/(tabs)/today.tsx:45`
- The app checks for new content each time it comes back to the front (at most once a minute), so closing and reopening works: `lib/live.ts:98`
- With no signal the saved copy is shown: `lib/saved-first.ts:2`

### The app looks different: the holiday look

```text
From December 1 to December 31 the app wears a holiday look: a navy banner, string lights and green accents. In 2026 it starts on November 10. Nothing is wrong.
1. It turns on by the date on your phone. There is no switch for it.
2. On the opening screen, tap anywhere to go in.
3. On January 1 the normal look comes back by itself.
4. If you see it at another time of year, check the date on your phone. If the date is right, report it: Settings, Report a problem.
```

**Search words:** holiday, christmas, lights, snow, green, colors, theme, look, looks different, changed, design, navy, banner, navidad, luces, nieve, colores, se ve diferente, cambio, tema

*465 characters.* Confirmed in:

- December 1 to 31 every year, by the phone's own date: `lib/season.ts:16`
- The 2026 season starts November 10: `lib/season.ts:19`
- The server can also force it on or off (APP_THEME), which is why step 4 says to report it: `lib/season.ts:24`
- Navy banner, string lights, evergreen accent: `components/Holiday.tsx:2`
- A tap anywhere leaves the opening screen (it also leaves by itself after about 4 seconds): `components/Holiday.tsx:275`
- Settings has no switch for the look (read the whole screen: there is none): `app/settings.tsx:224`

### OTIS will not download or the download is stuck

```text
OTIS downloads once, then works with no signal. The Set up OTIS button shows the size, about 500 MB to 1.3 GB.
1. Connect to Wi-Fi and keep the phone charged.
2. On the Today tab, tap Ask OTIS. If you see Set up OTIS, tap it.
3. Watch Setting up OTIS count up to 100%. You can leave the screen. OTIS keeps the download.
4. If the percent stops moving, close the app all the way, open it, and open OTIS again.
5. If you see OTIS could not finish setting up, check your connection, then open OTIS again.
6. Still stuck? Open Settings and tap Report a problem.
```

**Search words:** otis, downloading, downloaded, install, setup, set up, setting up, slow, percent, not downloading, won't download, failed, wifi, descargar, descarga, no descarga, instalar, atorado, no avanza

*557 characters.* Confirmed in:

- Downloads once; the size is shown: `app/otis.tsx:135`
- The button is Set up OTIS with the size in brackets: `app/otis.tsx:139`
- The progress line and percent: `app/otis.tsx:367`
- You can leave the screen; OTIS keeps the download: `app/otis.tsx:371`
- The exact failure line: `app/otis.tsx:364`
- Sizes: 1300 MB and 510 MB: `lib/otis/manifest.ts:30`
- Shown as 1.3 GB and 510 MB: `lib/otis/manifest.ts:90`
- The server's copy of the same sizes: `backend/talks/api_v2.py:38`
- The download library picks up where it stopped: `node_modules/react-native-executorch/src/fetcher/fetcher.ts:36`
- Ask OTIS is on the Today tab: `app/(tabs)/today.tsx:118`

### Not enough space on the phone for OTIS

```text
OTIS needs free space on the phone. The Set up OTIS button shows the size, about 500 MB to 1.3 GB.
1. Open your phone's own settings and look at storage.
2. Free more space than the size on the button. Old videos and apps you do not use take the most.
3. Open Zero Harm and tap Ask OTIS on the Today tab. Tap Set up OTIS if you see it. If not, the download picks up by itself.
The rest of the app works without OTIS.
```

**Search words:** otis, space, storage, full, memory, not enough, disk, room, no space, too big, size, gb, espacio, almacenamiento, memoria llena, sin espacio, lleno, no cabe

*416 characters.* Confirmed in:

- The size is on the button: `app/otis.tsx:139`
- Sizes: 1300 MB and 510 MB: `lib/otis/manifest.ts:30`
- After the first tap on Set up OTIS the setup screen is skipped and the download starts by itself: `app/otis.tsx:119`
- The rest of the app does not depend on OTIS (talks and sign-in never load it): `app/settings.tsx:206`

### OTIS is slow or stops in the middle of an answer

```text
OTIS runs on your phone, so its speed depends on the phone. It also keeps answers short.
1. Tap New chat at the top. Long chats slow OTIS down.
2. Ask one short question at a time.
3. If you see Starting OTIS, wait for it to finish loading.
4. If you see Sorry, OTIS could not answer just now, ask again or tap New chat.
5. If OTIS stops every time, close the app all the way and open it again. Then report it: Settings, Report a problem.
```

**Search words:** otis, otis not working, lag, laggy, takes forever, spinning, loading, stopped working, cut off, no answer, could not answer, lento, tarda, se tarda, se detiene, se corta, no responde, no contesta

*438 characters.* Confirmed in:

- The app's own advice: New chat: `app/otis.tsx:482`
- New chat is at the top of the OTIS screen: `app/otis.tsx:348`
- The loading line: `app/otis.tsx:367`
- The exact failure line: `app/otis.tsx:332`
- Answers are capped in length, so a long one ends early: `app/otis.tsx:159`
- Phones with less memory get the smaller model: speed depends on the phone: `lib/otis/manifest.ts:46`

### OTIS says it needs an update

```text
OTIS can ask for two different things.
1. If it says Update Zero Harm from the App Store or Google Play, open your app store, find Zero Harm and tap Update. Then open OTIS again.
2. If it says OTIS has an update, connect to Wi-Fi and tap Update OTIS. It downloads once.
3. Not a good time? Tap Not now, keep using OTIS as it is.
The rest of the app keeps working in the meantime.
```

**Search words:** otis, new version, upgrade, app store, google play, play store, old version, otis update, actualizar otis, actualizacion de otis, nueva version, pide actualizar

*379 characters.* Confirmed in:

- The exact line when the app is too old: `app/otis.tsx:110`
- When the server sends it (the owner sets a minimum app version): `backend/talks/api_v2.py:202`
- The second kind: a new download for OTIS itself: `app/otis.tsx:126`
- Its button: `app/otis.tsx:139`
- The way to put it off: `app/otis.tsx:145`

### OTIS is switched off or taking a break

```text
If you see OTIS is taking a short break, or another short message where the chat should be, Trainovate has switched OTIS off for now. Nothing is wrong with your phone.
1. You cannot turn OTIS back on from the phone. Check back later.
2. Use the rest of the app as usual. Talks and sign-in sheets do not need OTIS.
3. For a safety question right now, ask your supervisor or safety lead. If someone is hurt, call 911.
4. If OTIS is still off after a few days, open Settings and tap Report a problem.
```

**Search words:** otis, off, switched off, turned off, disabled, break, short break, unavailable, not available, gone, missing, won't open, apagado, desactivado, no disponible, no esta, no abre, descanso

*497 characters.* Confirmed in:

- The default line; the owner can write another: `app/otis.tsx:111`
- The server decides; nothing on the phone turns it back on: `backend/talks/api_v2.py:207`
- The switches the owner controls: `backend/talks/models.py:457`

### OTIS says it does not have that

```text
OTIS answers only from Zero Harm talks, Zero Hour huddle cards and plain-language OSHA General Industry rules. It does not guess.
1. Ask again with the plain name of the hazard or tool, like ladder, forklift or lockout.
2. Ask one thing at a time.
3. If it is still not covered, ask your supervisor or safety lead.
4. For a problem with the app itself, type report an app problem, or open Settings and tap Report a problem.
If an answer looks wrong, tap Report this answer under it.
```

**Search words:** otis, don't have that, doesn't know, cannot answer, can't answer, my question, not covered, knowledge base, no answer, no sabe, no tiene, no lo tiene, no encuentra, no entiende

*434 characters.* Confirmed in:

- The line OTIS gives when nothing matches: `app/otis.tsx:64`
- OTIS is told not to guess: `lib/otis/prompt.ts:6`
- What OTIS answers from: `app/otis.tsx:128`
- Typing report a problem starts a report: **false.** A bare "report a problem" is not an app problem to OTIS (`ASKS_FOR_SUPPORT` in `lib/support/intent.ts`): plants report problems to supervisors. Only wording that names the app, like "report an app problem" or "report a bug in the app", starts one. Step 4 needs new words (owner check 15).
- Report this answer under a reply: `lib/support/flow.ts:150`

### Notifications are not arriving

```text
Notifications are off until you turn them on.
1. Open Settings (top of the Today tab). Under Notifications, turn on the ones you want.
2. When the phone asks, allow notifications.
3. If you see Notifications are blocked for Zero Harm on this phone, tap Open phone settings and allow them. Then come back and turn the switches on again.
4. Know the times. Monday Minute: Monday at 5:00 AM Pacific. Weekly toolbox talk: Sunday around noon Pacific. Zero Hour episodes: Thursdays.
5. Check that Do Not Disturb or Focus is off on the phone.
6. Still nothing? Open Settings and tap Report a problem.
```

**Search words:** notification, push, reminder, reminders, alerts, not getting, didn't get, no notifications, silent, what time, notificacion, notificaciones, aviso, avisos, no llegan, no recibo, recordatorio

*593 characters.* Confirmed in:

- Off until turned on: `components/HowTo.tsx:45`
- Settings is the link at the top of the Today tab (the Monday tab has one at the bottom too): `app/(tabs)/today.tsx:49`
- The Monday Minute switch and its time: `app/settings.tsx:225`
- Weekly toolbox talk: Sunday around noon Pacific: `app/settings.tsx:226`
- Zero Hour episodes: Thursdays: `app/settings.tsx:228`
- The phone asks the first time a switch is turned on: `lib/push.ts:116`
- If the phone says no, every switch goes back to off, so they must be turned on again afterwards: `lib/push.ts:120`
- The exact blocked line: `app/settings.tsx:232`
- The button under it: `app/settings.tsx:233`
- The Monday Minute publishes at 5:00 AM Pacific: `backend/monday/models.py:94`
- Pushes go out on a 15 minute cycle, so a few minutes late is normal: `backend/talks/management/commands/cron.py:28`

### No Monday Minute is showing

```text
A new Monday Minute comes out every Monday at 5:00 AM Pacific.
1. Open the Monday tab and pull down to refresh.
2. If you see No signal, move to where you have signal or Wi-Fi and pull down again.
3. A talk that is running late can come out as late as Wednesday morning.
4. If this week's talk is still missing after that, open Settings and tap Report a problem.
To get a notification when it is out, turn on Monday Minute in Settings.
```

**Search words:** monday minute, monday, minute, talk, missing, not showing, blank, empty, nothing, no talk, where, last week, lunes, charla, no aparece, no sale, no hay, falta, vacio

*435 characters.* Confirmed in:

- Publish time: `backend/monday/models.py:94`
- Pull down to refresh on the Monday tab: `app/(tabs)/index.tsx:45`
- The no-signal line on that tab: `app/(tabs)/index.tsx:54`
- A late talk stays owed until Wednesday 5:00 AM, then the owner is told: `backend/monday/generate.py:16`
- The switch name: `app/(tabs)/index.tsx:56`

### A talk is locked or not there yet

```text
Zero Harm Weekly talks open on Sunday around noon Pacific, ready for Monday. A few open sooner and show as Ready early.
1. On the Today tab, pull down to refresh.
2. If you see This week's talk isn't out yet, or This talk isn't available yet, it has not opened. You cannot unlock it from the phone.
3. To run a talk today, tap Open the archive and pick one.
4. If it is past Sunday noon Pacific and you have signal, open Settings and tap Report a problem.
```

**Search words:** talk, toolbox talk, locked, lock, unlock, not available, isn't available, not out, not there, missing, coming soon, early, this week, bloqueada, no disponible, no esta, todavia no, charla, semana

*455 characters.* Confirmed in:

- Talks open Sunday 11:59 AM Pacific: `backend/talks/models.py:56`
- The next few open early: `backend/talks/models.py:13`
- How many (2 by default): `backend/zeroharm/settings.py:208`
- They show as Ready early: `app/(tabs)/today.tsx:76`
- The exact line on Today: `app/(tabs)/today.tsx:64`
- The exact line on a talk that is not open: `app/talk/[issue].tsx:40`
- The archive link on Today: `app/(tabs)/today.tsx:160`

### Spanish is not offered

```text
A talk shows in Spanish only when it has an approved Spanish version.
1. Open a Zero Harm Weekly talk from the Today tab or the Archive.
2. Look for the English and Español buttons near the top, and tap Español.
3. No buttons? That talk has no approved Spanish yet. You cannot turn it on from the phone.
4. Ask OTIS in Spanish and it tries to answer in Spanish.
The Monday Minute and the app's menus are in English for now. To ask for more Spanish, open Settings and tap Report a problem.
```

**Search words:** spanish, espanol, language, languages, translate, translation, english only, no spanish, change language, idioma, en espanol, traducir, traduccion, ingles, cambiar idioma, no hay espanol

*488 characters.* Confirmed in:

- The language buttons show only when the talk has Spanish: `app/talk/[issue].tsx:85`
- The two buttons: `app/talk/[issue].tsx:95`
- Only an approved translation is sent: `backend/talks/views.py:619`
- A Monday Minute has no Spanish fields: `lib/monday.ts:10`
- OTIS is told to answer in the language asked (a small model: it tries): `lib/otis/prompt.ts:13`

### The weather and heat card is missing

```text
The weather line is at the top of the Today tab. It needs your location and a signal.
1. On Today, tap Show local weather and heat alerts, then allow location.
2. If that button is gone and no weather shows, open your phone's settings, find Zero Harm, and allow Location.
3. Make sure Location is turned on for the phone.
4. Check your signal, then close the app all the way and open it again.
Weather comes from the US National Weather Service, so it works only in the United States. The heat and cold notes show only on days with that risk.
```

**Search words:** weather, heat, heat index, temperature, forecast, cold, location, gps, permission, missing, not showing, gone, no weather, clima, tiempo, calor, temperatura, ubicacion, no aparece, no sale

*542 characters.* Confirmed in:

- Top of the Today tab: `app/(tabs)/today.tsx:57`
- The button shown before the phone has been asked: `components/WeatherBar.tsx:33`
- After a no, nothing is shown at all: `components/WeatherBar.tsx:21`
- It looks once when the app starts, which is why step 4 is close and reopen: `components/WeatherBar.tsx:14`
- No location fix means no weather: `lib/weather.ts:36`
- Where the weather comes from: `lib/weather.ts:24`
- US only: `backend/talks/views.py:669`
- The heat and cold notes show only when there is that risk: `components/WeatherBar.tsx:51`

### A signature will not save

```text
1. Type the person's name in Crew member name first. Without a name you see Add your name.
2. Have the person sign in the box with a finger.
3. Tap Save signature. The name shows below with a check mark.
4. To start over, tap Clear and sign again.
5. If the box will not take a signature, tap Take a group photo and type the head count instead. Or use the paper sheet: on the Monday tab, tap Print.
```

**Search words:** signature, signatures, sign, signing, can't sign, finger, won't save, not saving, box, blank, crew member, name, clear, firma, firmas, firmar, no guarda, no firma, nombre, dedo

*398 characters.* Confirmed in:

- The name box: `app/signin/[session].tsx:187`
- What shows without a name: `app/signin/[session].tsx:51`
- The button: `app/signin/[session].tsx:204`
- The name with a check mark: `app/signin/[session].tsx:208`
- Clear: `app/signin/[session].tsx:201`
- The other way to record who was there: `app/signin/[session].tsx:183`
- Print on the Monday tab includes a paper sign-in sheet: `components/MondayMinuteView.tsx:95`

### Trouble taking the group photo

```text
1. On the Crew sign-in screen, tap Take a group photo.
2. When the phone asks, allow the camera. Ask the crew before you take it.
3. If the camera does not open, your photo library opens instead. Pick a photo there. To use the camera, allow Camera for Zero Harm in your phone's settings and try again.
4. Type the head count in How many people are in the photo?
5. Tap Retake to replace the photo, or Remove to take it off the sheet.
```

**Search words:** photo, picture, pictures, camera, group photo, take photo, camera won't open, permission, retake, head count, foto, fotos, camara, no abre, tomar foto, grupo, permiso

*433 characters.* Confirmed in:

- The screen is titled Crew sign-in: `app/_layout.tsx:135`
- The button: `app/signin/[session].tsx:183`
- The phone asks for the camera: `app/signin/[session].tsx:64`
- Without the camera, the photo library opens instead: `app/signin/[session].tsx:73`
- Ask the crew first: `app/signin/[session].tsx:164`
- The head count box: `app/signin/[session].tsx:172`
- Retake: `app/signin/[session].tsx:175`
- Remove: `app/signin/[session].tsx:178`

### A sign-in sheet will not save or send

```text
1. Add at least one signature or a group photo. Until then the save buttons do not work.
2. Under Save the sheet, fill in Your name and Your email.
3. Tap Save sheet to my records.
4. If you see Saved on this phone, it has not gone through yet, most often because there is no signal. The app sends it by itself the next time you open it with signal.
5. If you see Could not build the sheet, try again. If it fails again, tap Email or share the PDF.
6. Still not sent after a day with good signal? Report it: Settings, Report a problem.
```

**Search words:** sign-in sheet, sign in sheet, sheet, save, send, won't save, not saving, not sending, failed, records, attendance, roster, hoja, asistencia, guardar, no guarda, enviar, no envia, registro

*535 characters.* Confirmed in:

- The buttons are off until there is a signature or a photo: `app/signin/[session].tsx:155`
- The Save the sheet section: `app/signin/[session].tsx:211`
- Name and a valid email are needed: `app/signin/[session].tsx:99`
- The button: `app/signin/[session].tsx:222`
- The line when it did not go through: `app/signin/[session].tsx:116`
- It waits in an outbox on the phone: `lib/sheets.ts:29`
- It is sent again each time the app opens or comes back to the front: `app/_layout.tsx:93`
- The exact failure line: `app/signin/[session].tsx:120`
- Server limit: 20 MB a sheet (step 6 covers a sheet the server keeps refusing): `backend/talks/views.py:530`
- Server limit: 30 sheets an hour from one network: `backend/talks/views.py:506`

### What Save sheet to my records does

```text
Save sheet to my records does two things.
1. It keeps the PDF on this phone. Find it in Settings under My sign-in sheets. Tap Print or Email or share there.
2. It sends a copy, with its signatures and photo, to Trainovate Technologies, filed under the email you typed.
3. When you see Saved to your Zero Harm records, the copy arrived.
Deleting the app deletes the sheets on the phone, so email important ones to yourself. To ask for a copy later, tap Contact support in Settings.
```

**Search words:** save sheet to my records, records, my records, where, saved, find, sheet, sheets, my sign-in sheets, copy, download, stored, donde, guardado, registros, hoja, hojas, encontrar, copia

*480 characters.* Confirmed in:

- The app's own words for both halves: `app/signin/[session].tsx:228`
- Where the phone's copy is: `app/settings.tsx:238`
- Print and Email or share on that screen: `app/sheets.tsx:34`
- The copy goes to Trainovate's GoHighLevel: `backend/talks/integrations.py:272`
- Filed under the email typed: `backend/talks/integrations.py:296`
- The line when the copy arrived: `app/signin/[session].tsx:115`
- Deleting the app deletes the phone's copies: `app/sheets.tsx:20`
- Contact support in Settings: `app/settings.tsx:291`

### The PDF will not print or share

```text
1. On the Crew sign-in screen, add a signature or a group photo first.
2. Tap Print the sheet to print. Tap Email or share the PDF to email it or save it to your files.
3. Printing needs a printer your phone can reach, like one on the same Wi-Fi.
4. No printer? Tap Email or share the PDF and send it to yourself.
5. If you see Could not build the sheet or Could not make the PDF, try again in a moment. If it keeps failing, report it: Settings, Report a problem.
Every sheet you print or share is also kept in Settings under My sign-in sheets.
```

**Search words:** print, printer, printing, pdf, share, sharing, email, export, airprint, won't print, can't print, no printer, imprimir, impresora, no imprime, compartir, correo, enviar

*544 characters.* Confirmed in:

- Print the sheet: `app/signin/[session].tsx:223`
- Email or share the PDF: `app/signin/[session].tsx:224`
- Share goes to mail, files and so on: `lib/pdf.ts:51`
- Printing uses the phone's own print service: `lib/pdf.ts:58`
- The failure line here: `app/signin/[session].tsx:146`
- The failure line for the Monday Minute handout: `components/MondayMinuteView.tsx:71`
- Printed and shared sheets are kept too: `app/signin/[session].tsx:144`

### I left crew sign-in before saving the sheet

```text
A sheet is kept only after you tap Save sheet to my records, Print the sheet or Email or share the PDF.
1. If you left before that, the unfinished sheet cannot be opened again.
2. Open the talk again and tap Start crew sign-in to start a new sheet.
3. Have the crew sign again, or take one group photo and type the head count.
4. Before you leave the screen, tap one of the three buttons. The sheet is then in Settings under My sign-in sheets.
```

**Search words:** lost, lost signatures, disappeared, gone, missing, deleted, went back, back button, unfinished, reopen, start over, sheet, perdi, perdido, se borro, borraron, desaparecio, firmas, hoja, regresar

*443 characters.* Confirmed in:

- Every tap on Start crew sign-in makes a new, empty sheet: `lib/signins.ts:24`
- My sign-in sheets lists only sheets that were saved, printed or shared: `lib/signins.ts:71`
- A sheet is kept only by those three buttons: `app/signin/[session].tsx:127`
- Nothing in the app lists an unfinished sheet, so it cannot be opened again: `app/sheets.tsx:8`

### Signing in with your email

```text
Signing in is free and optional. There is no password.
1. Open Settings (top of the Today tab). Under Your account, type Your name and Email.
2. Tap Sign in.
3. If you see Check the email address, fix it and tap Sign in again.
You are signed in right away, even with no signal. You get Zero Harm Weekly by email each week and can unsubscribe anytime. Everything in the app works without signing in.
```

**Search words:** sign in, signin, sign up, signup, login, log in, account, email, password, register, can't sign in, forgot password, iniciar sesion, registrarse, cuenta, correo, contrasena, entrar, no me deja entrar

*398 characters.* Confirmed in:

- The section: `app/settings.tsx:166`
- The button: `app/settings.tsx:219`
- No password: `lib/account.ts:2`
- The exact error: `lib/account.ts:47`
- Signed in at once; the sign-up is sent in the background: `lib/account.ts:289`
- Zero Harm Weekly by email, unsubscribe anytime: `lib/account.ts:14`
- Optional: `app/settings.tsx:206`

### Changing your name or email

```text
Only the phone that first signed up with an email can change that sign-up.
1. On that phone, open Settings and tap Remove my info.
2. Type the new name and email, then tap Sign in.
3. On any other phone the change is not saved, and the app tells you so.
4. No longer have the first phone? Open Settings and tap Report a problem, and say what to change.
The name on a sign-in sheet is separate. Change it under Save the sheet on the Crew sign-in screen.
```

**Search words:** change name, change email, wrong name, wrong email, typo, misspelled, edit, update, new email, new phone, details, profile, cambiar nombre, cambiar correo, nombre mal, corregir, editar, telefono nuevo

*452 characters.* Confirmed in:

- The rule, in the server's own words: `backend/talks/views.py:149`
- Any other phone changes nothing and is told so: `backend/talks/views.py:217`
- What the app says on that other phone: `lib/account.ts:111`
- Signed in, Settings shows only Remove my info: there is no edit box, so the way to change is remove, then sign in again: `app/settings.tsx:184`
- A removal and a new sign-up made together are sent in that order: `lib/account.ts:207`
- The name on sign-in sheets is separate: `lib/account.ts:20`

### Removing your info

```text
1. Open Settings (top of the Today tab). Under Your account, tap Remove my info, then tap Remove.
2. On the phone that first signed up, this ends your sign-up, and the app stops adding you to Zero Harm Weekly.
3. On any other phone, nothing is removed right away. The app sends a request and a person removes your info. You see We got your request.
4. With no signal, it waits on the phone and sends later.
5. If you joined Zero Harm Weekly another way, also tap Unsubscribe in one of its emails.
```

**Search words:** remove my info, remove, unsubscribe, stop emails, sign out, log out, logout, leave, opt out, take me off, quitar, quitar mi informacion, cancelar, darme de baja, cerrar sesion, salir, no mas correos

*496 characters.* Confirmed in:

- The confirm box: `app/settings.tsx:120`
- The owner phone: the sign-up is deleted and the newsletter tags the app added come off: `backend/talks/views.py:301`
- Any other phone: nothing is deleted, the owner is asked: `backend/talks/views.py:339`
- With no signal the request waits in the outbox: `lib/account.ts:323`
- The line the app shows for a request: We got your request. A person will remove your info.: `lib/account.ts:113`
- The line with no signal: `lib/account.ts:114`

### Deleting your data

```text
1. To end your sign-up, open Settings and tap Remove my info.
2. To delete everything tied to your email (sign-ups, saved sign-in sheets, suggestions, comments and problem reports), tap Delete my data in Settings. It opens an email to us. Send it from the address you signed up with.
3. To clear what is kept on the phone, like sign-in sheets and the OTIS download, delete the app.
4. To stop the daily count and crash reports, turn off Anonymous usage count and Crash reports in Settings.
```

**Search words:** delete, delete my data, delete account, erase, wipe, privacy, personal data, my data, forget me, borrar, eliminar, mis datos, datos, privacidad, borrar cuenta, eliminar cuenta

*472 characters.* Confirmed in:

- Remove my info: `app/settings.tsx:184`
- Delete my data opens an email that lists sign-ups, saved sheets, suggestions, comments and problem reports: `app/settings.tsx:295`. Step 2 of the entry leaves out problem reports (owner check 16).
- That button shows only when a support email is set (see what to check): `app/settings.tsx:289`
- Deleting the app clears what is on the phone: `app/sheets.tsx:20`
- The usage switch: `app/settings.tsx:270`
- The crash switch: `app/settings.tsx:279`

### How to report a problem and see the reply

```text
1. Open Settings (top of the Today tab) and tap Report a problem. Or type report an app problem to OTIS.
2. Say what happened and what you tapped just before.
3. Add your email only if you want us to write back.
4. Tap Send report (in OTIS, tap Send). You get a reference like ZH-123. With no signal the report is saved and sends later.
5. To see its status and our reply, open Settings and tap My reports.
```

**Search words:** report, report a problem, bug, ticket, issue, complaint, feedback, my reports, reply, status, reference, reportar, reportar un problema, queja, falla, problema, respuesta

*401 characters.* Confirmed in:

- Settings is the link at the top of the Today tab: `app/(tabs)/today.tsx:49`
- Report a problem in Settings: `app/settings.tsx:258`
- My reports in Settings: `app/settings.tsx:259`
- The form and its Send report button: `app/report.tsx:122`
- In the OTIS chat the button reads Send while a report is being written: `app/otis.tsx:509`
- Status and reply are shown: `app/my-reports.tsx:55` and `app/my-reports.tsx:60`
- A report has a number like ZH-123 once the server has it, and waits on the phone with no signal: `lib/support/reports.ts:27`
- What OTIS says when a report is sent: `lib/support/flow.ts:140`
- What it says with no signal: `lib/support/flow.ts:108`
- The email is optional: `lib/support/flow.ts:88`
- Typing report a problem to OTIS starts a report: **false.** See "OTIS says it does not have that" above: only wording that names the app, like "report an app problem" or "report a bug in the app", starts one (`ASKS_FOR_SUPPORT` in `lib/support/intent.ts`). Step 1 needs new words (owner check 15).

### How to flag a wrong OTIS answer

```text
OTIS can be wrong. If an answer looks wrong or unsafe:
1. Do not act on it. Follow your site's written steps and ask your supervisor.
2. Tap Report this answer under the answer.
3. Confirm. That one question and answer go to Trainovate so a person can review them. The rest of the chat is not sent.
A flag is for OTIS answers. For a problem with the app, tap Report a problem in Settings.
```

**Search words:** wrong answer, wrong, bad answer, incorrect, mistake, unsafe, flag, report answer, report this answer, otis is wrong, lied, respuesta incorrecta, equivocado, mal, reportar respuesta, error

*388 characters.* Confirmed in:

- OTIS can be wrong: `app/otis.tsx:135`
- The control under a reply: `lib/support/flow.ts:150`
- The question it asks before sending: `lib/support/flow.ts:152`
- Only that one question and answer are sent: `lib/support/reports.ts:352`

### What a crash report sends and how to turn it off

```text
When the app hits an error, it can send a crash report so we can fix it.
1. It sends the error, the screen you were on, the time, the app version, and your phone model and system version.
2. It does not send your name, your email or your OTIS chat. It carries a random id for this copy of the app, and the server keeps only a scrambled form of it.
3. To turn it off, open Settings and turn off Crash reports. Reports still waiting on the phone are deleted.
4. Not every sudden close is caught. If the app keeps closing, tap Report a problem in Settings.
```

**Search words:** diagnostics, error report, privacy, what is sent, tracking, turn off, switch, data, send, sends, automatic, reporte de fallas, reportes, privacidad, que se envia, apagar, desactivar

*553 characters.* Confirmed in:

- What is sent, including the random install id: `lib/support/crash.ts:7`
- What is never sent: `lib/support/crash.ts:9`
- Turning it off deletes what was waiting: `lib/support/crash.ts:15`
- Not every crash is caught: `lib/support/crash.ts:4`
- The switch: `app/settings.tsx:279`

### Who to contact for help

```text
1. Someone hurt or in danger: call 911 first. The app is not for emergencies.
2. A safety question about your job: ask your supervisor or safety lead.
3. A problem with the app: open Settings (top of the Today tab) and tap Report a problem. Read the reply in My reports.
4. Your account or your data: tap Contact support in Settings. It opens an email to Trainovate Technologies.
Zero Harm is free and made by Trainovate Technologies in Las Vegas.
```

**Search words:** contact, support, help, phone number, email, who, call, customer service, trainovate, talk to a person, human, contacto, soporte, ayuda, telefono, correo, hablar con alguien

*447 characters.* Confirmed in:

- 911 first: `app/otis.tsx:486`
- Safety questions go to the supervisor or safety lead: `app/otis.tsx:65`
- Report a problem: `app/settings.tsx:258`
- My reports: `app/settings.tsx:259`
- Contact support opens an email: `app/settings.tsx:291`
- Made in Las Vegas by Trainovate: `app/settings.tsx:300`
- Free: `lib/account.ts:15`

## The six entries that were already there

All six are now app help. Three were corrected because their steps no longer matched the app. An entry the owner has edited keeps its wording.

### How to run a toolbox talk in the app

```text
1. Open the talk. The Monday Minute is on the Monday tab. The Zero Harm Weekly talk is on the Today tab: tap Open the talk.
2. Read it to your crew and ask the crew question.
3. Tap Start crew sign-in.
4. Each person types a name, signs with a finger and taps Save signature. Or tap Take a group photo and type the head count. You can do both.
5. Tap Save sheet to my records, Print the sheet or Email or share the PDF.
```

**Search words:** how to, run a talk, toolbox talk, start, crew sign-in, sign-in, signature, group photo, attendance, records, pdf, como, dar la charla, charla, asistencia, firma

*419 characters.* Confirmed in:

- The Monday tab is the Monday Minute: `app/(tabs)/_layout.tsx:32`
- Open the talk on Today: `app/(tabs)/today.tsx:84`
- Start crew sign-in (Monday Minute): `components/MondayMinuteView.tsx:90`
- Start crew sign-in (Zero Harm Weekly): `app/talk/[issue].tsx:16`
- Save signature: `app/signin/[session].tsx:204`
- Take a group photo: `app/signin/[session].tsx:183`
- The three finishing buttons. The old entry said Share the PDF, which is not a button: `app/signin/[session].tsx:224`

Was: "Open this week's talk on the Today screen. Read it with your crew and ask the crew question. Tap Start crew sign-in. Crew members can each type their name and sign with a finger, or the person running the talk can take one group photo and enter the head count, or both. Then tap Save sheet to my records to keep the PDF, or Share the PDF."

### Finding past talks

```text
1. On the Today tab, tap Open the archive.
2. Type a word in Search toolbox talks, like ladder or heat. Or tap a month theme to filter.
3. Tap a talk to open it.
4. For older Monday Minutes, open the Monday tab, scroll to the bottom and tap Past Monday Minutes.
```

**Search words:** archive, past talks, old talks, search, find, last week, previous, old issue, history, archivo, charlas pasadas, buscar, anteriores, semana pasada

*261 characters.* Confirmed in:

- Open the archive on Today: `app/(tabs)/today.tsx:160`
- The search box: `app/archive.tsx:42`
- Month theme filters: `app/archive.tsx:51`
- Past Monday Minutes, at the bottom of the Monday tab: `components/MondayMinuteView.tsx:130`

Was: "Open the Archive from the Today screen to find every past Zero Harm Weekly talk. Search by topic, or filter by month theme."

### Suggesting a toolbox talk topic

```text
1. On the Today tab, tap Suggest a talk. Or tap Suggest a toolbox talk at the bottom of the Archive.
2. Type the topic. Add what happened or why it matters if you want. Leave out names and anything that identifies an injured person.
3. Tap Send my idea. Sending needs a signal.
Your idea goes to the Zero Harm Weekly team.
```

**Search words:** suggest, suggestion, idea, topic, request, send my idea, sugerir, sugerencia, tema, proponer

*322 characters.* Confirmed in:

- Suggest a talk is on Today. The old entry said the Learn tab, which has no such link: `app/(tabs)/today.tsx:161`
- Suggest a toolbox talk at the bottom of the Archive: `app/archive.tsx:80`
- Send my idea: `app/suggest.tsx:96`
- A suggestion is not saved for later: it needs a signal: `app/suggest.tsx:95`
- The privacy line: `app/suggest.tsx:72`

Was: "Tap Suggest a talk in the Archive or on the Learn tab. Tell us the topic and what happened at your site. Your idea goes to the Zero Harm Weekly team."

### What OTIS is

```text
OTIS is the Zero Harm safety assistant from Trainovate Technologies. OTIS answers only from Zero Harm Weekly toolbox talks, Zero Hour huddle cards, and plain-language summaries of federal OSHA General Industry rules in this knowledge base. OTIS runs on your phone and works with no signal. Your questions stay on the phone unless you choose to report a problem or report an answer. OTIS can be wrong. Always follow your site's written procedures and ask your supervisor or safety lead when you are not sure. OTIS is not legal or medical advice.
```

**Search words:** otis, what is otis, about otis, assistant, chatbot, who are you, osha, general industry, privacy, que es otis, quien eres, asistente

*544 characters.* Confirmed in:

- Runs on the phone, works with no signal: `app/otis.tsx:132`
- What can now leave the phone, and only when the person chooses: `lib/support/reports.ts:3`

### Regulatory alerts

```text
Regulatory alerts are short, plain-language summaries of new federal OSHA, Nevada and Las Vegas rules that could affect your site. They are for awareness, not legal advice. Check the rule itself for what applies to you. Turn on Regulatory alerts in Settings to get a notification.
```

**Search words:** alert, rule, regulation, osha, nevada, law

*280 characters.* Confirmed in:

- What alerts are: `app/alerts.tsx:24`
- The switch: `app/settings.tsx:227`
- For awareness, not legal advice: `app/alert/[id].tsx:34`

### Zero Harm Weekly

```text
Zero Harm Weekly is a free weekly safety newsletter. Each issue is a 5-minute toolbox talk with a story and a crew question, sent every Sunday around noon Pacific so it is ready for Monday's meeting. The talk also appears in this app.
```

**Search words:** newsletter, weekly, sunday, email, subscribe

*234 characters.* Confirmed in:

- Sunday 11:59 AM Pacific: `backend/talks/models.py:56`
- The newsletter: `app/(tabs)/learn.tsx:38`
- Free: `lib/account.ts:15`

## Decisions made in the seed

- **"OSHA rules in OTIS: what they cover" stays a safety entry.** It carries the "Zero Harm app help" label, but it
  explains the safety content and names the OSHA parts. A safety question has to keep finding it, and the phone keeps
  app help out of safety answers.
- **Anything else you added under the "Zero Harm app help" label becomes app help** when the migration runs. Change it
  back in the console if that is wrong for an entry.
- **Wording you edited is kept.** The three corrections are applied only to an entry that still reads exactly as it was
  first seeded. A new entry is created only if no entry has that title.
- **App help cannot name an OSHA section number.** The admin and the console refuse it, with a plain message.
- **Titles were tuned for the phone's search.** Three entries were renamed during testing so that the bare words "not
  working" lead to "The app closed, crashed or froze" and not to whichever entry had "work" in its title.

## How the words were tried

`SupportSearchTests` holds a Python copy of the phone's support search (`lib/otis/kb.ts`, `searchSupport`, as of
2026-11-11) and 91 questions, 59 in English and 32 in Spanish. Every new entry has at least one of each. For every
question the right entry has to come **first**, because the phone shows the best match word for word. A sample:

| Typed | Entry shown |
|---|---|
| the app keeps crashing | The app closed, crashed or froze |
| la app se cierra sola | The app closed, crashed or froze |
| OTIS download is stuck at 40% | OTIS will not download or the download is stuck |
| otis no descarga | OTIS will not download or the download is stuck |
| no tengo espacio para otis | Not enough space on the phone for OTIS |
| otis is taking a short break | OTIS is switched off or taking a break |
| no me llegan las notificaciones | Notifications are not arriving |
| there is no monday minute this week | No Monday Minute is showing |
| talk isn't out yet | A talk is locked or not there yet |
| no hay espanol | Spanish is not offered |
| no aparece el clima | The weather and heat card is missing |
| la firma no se guarda | A signature will not save |
| sign in sheet not sending | A sign-in sheet will not save or send |
| donde se guardan las hojas | What Save sheet to my records does |
| no puedo imprimir | The PDF will not print or share |
| i went back and the sheet is gone | I left crew sign-in before saving the sheet |
| what is my password | Signing in with your email |
| quiero darme de baja | Removing your info |
| borrar mis datos | Deleting your data |
| why are there christmas lights | The app looks different: the holiday look |
| did you reply to my report | How to report a problem and see the reply |
| otis gave a wrong answer | How to flag a wrong OTIS answer |
| turn off crash reports | What a crash report sends and how to turn it off |
| is there a phone number for support | Who to contact for help |

If the phone's search rules change, change the copy in the test with them. To run it:
`cd backend && python manage.py test talks.tests_kb_support`

## Not in this seed (drafts you can add in the console)

The seed stops at 28 entries. These three are real problems too. Each fact was read from the code, but none is seeded.

- **A Zero Hour video will not play.** The video plays from the internet and is not saved on the phone, so it needs a
  signal (`app/zero-hour/[n].tsx`, `useVideoPlayer(ep.video_url ...)`). "The episode video is on its way" means the
  video is not posted yet. The huddle card under it still works with no signal.
- **My comment is not showing.** Comments on a Monday Minute are checked before they show (`components/MondayMinuteView.tsx`,
  Community rules). The line under Post comment says what happened. Posting needs a signal: a comment is not saved for later.
- **My thumbs up did not count.** With no signal you see "Saved on this phone. It will send when you have signal."
  The vote goes out the next time the app opens with signal.

## Keep untouched

- **"1. Someone hurt or in danger: call 911 first. The app is not for emergencies."** It is the first line of "Who to
  contact for help" on purpose, and a test holds it there.
- **The exact button names.** "Save sheet to my records", "Email or share the PDF", "Open phone settings" and the rest
  are copied from the screens. If a button is renamed in the app, `OnScreenWordsTests` fails until the entry is changed too.
- **"You cannot ... from the phone."** Four entries say plainly that something cannot be fixed on the phone (a locked
  talk, missing Spanish, OTIS switched off, an unfinished sheet). Do not soften these into steps that will not work.
- **"Only the phone that first signed up with an email can change that sign-up."** This is the server's real rule.
