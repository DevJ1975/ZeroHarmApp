"""OTIS knowledge base: app help. Fixes for problems with the Zero Harm app itself, not safety content.

Every entry here is kind "support". The phone shows a support entry word for word (it never goes through the on-device
model) and keeps it out of safety answers. So each one is written to be read as it stands: one problem, a title in the
words a worker would type, 2 to 6 short numbered steps on their own lines, under 700 characters. The tags hold the
literal words people use, in English and in Spanish without accents, because every entry is sent as English and a
Spanish question can only find it through its tags.

Every button, switch and screen named below was checked against the app's own code on 2026-11-11 (see
docs/otis-support-kb-review.md, which lists where each fact was confirmed and what the owner should check). Where a
problem cannot be fixed on the phone, the entry says so and says to report it.

No OSHA section numbers in these: the weekly OSHA sync reads every entry for them and would take a help answer out
of OTIS when that rule changed.

This also (a) marks the app help entries from the first seed as support, (b) corrects three of them whose steps
no longer matched the app, and (c) gives two of them Spanish tags. An entry the owner has edited keeps its wording: only its kind changes.
"""
from django.db import migrations

SOURCE = "Zero Harm app help"
SAFETY, SUPPORT = "safety", "support"

ENTRIES = [
    # ---- The app itself ---------------------------------------------------------------------------
    ("The app closed, crashed or froze",
     "If the app crashes, gets stuck or keeps closing, close it all the way and open it again. "
     "Talks and saved sign-in sheets stay on this phone.\n"
     "1. Swipe Zero Harm away from your open apps, then open it again.\n"
     "2. If you see a screen with Try again, tap it.\n"
     "3. If it keeps happening, update Zero Harm from the App Store or Google Play.\n"
     "4. Tell us what you tapped just before it closed: open Settings (top of the Today tab) and tap Report a problem.",
     "crash, crashing, frozen, freeze, stuck, app stuck, closes, quit, black screen, won't open, not working, "
     "stopped working, broken, se cierra, se cerro, se congela, se traba, no funciona, no abre, falla"),
    ("The app shows old content or will not update",
     "With no signal the app shows the copy saved on the phone. You may see No signal. Showing the copy saved on this phone.\n"
     "1. Move to where you have signal or Wi-Fi.\n"
     "2. On the Monday or Today tab, pull down to refresh.\n"
     "3. Or close the app all the way and open it again.\n"
     "4. To get the newest version of the app, update Zero Harm from the App Store or Google Play.\n"
     "5. Still old with a good signal? Open Settings and tap Report a problem.",
     "old, outdated, out of date, not updating, won't update, updates, old talk, refresh, reload, no signal, "
     "offline, viejo, no se actualiza, no actualiza, actualizar, actualizado, sin senal, recargar"),
    ("The app looks different: the holiday look",
     "From December 1 to December 31 the app wears a holiday look: a navy banner, string lights and green accents. "
     "In 2026 it starts on November 10. Nothing is wrong.\n"
     "1. It turns on by the date on your phone. There is no switch for it.\n"
     "2. On the opening screen, tap anywhere to go in.\n"
     "3. On January 1 the normal look comes back by itself.\n"
     "4. If you see it at another time of year, check the date on your phone. If the date is right, report it: Settings, Report a problem.",
     "holiday, christmas, lights, snow, green, colors, theme, look, looks different, changed, design, navy, banner, "
     "navidad, luces, nieve, colores, se ve diferente, cambio, tema"),

    # ---- OTIS -------------------------------------------------------------------------------------
    ("OTIS will not download or the download is stuck",
     "OTIS downloads once, then works with no signal. The Set up OTIS button shows the size, about 500 MB to 1.3 GB.\n"
     "1. Connect to Wi-Fi and keep the phone charged.\n"
     "2. On the Today tab, tap Ask OTIS. If you see Set up OTIS, tap it.\n"
     "3. Watch Setting up OTIS count up to 100%. You can leave the screen. OTIS keeps the download.\n"
     "4. If the percent stops moving, close the app all the way, open it, and open OTIS again.\n"
     "5. If you see OTIS could not finish setting up, check your connection, then open OTIS again.\n"
     "6. Still stuck? Open Settings and tap Report a problem.",
     "otis, downloading, downloaded, install, setup, set up, setting up, slow, percent, not downloading, won't download, "
     "failed, wifi, descargar, descarga, no descarga, instalar, atorado, no avanza"),
    ("Not enough space on the phone for OTIS",
     "OTIS needs free space on the phone. The Set up OTIS button shows the size, about 500 MB to 1.3 GB.\n"
     "1. Open your phone's own settings and look at storage.\n"
     "2. Free more space than the size on the button. Old videos and apps you do not use take the most.\n"
     "3. Open Zero Harm and tap Ask OTIS on the Today tab. Tap Set up OTIS if you see it. If not, the download picks up by itself.\n"
     "The rest of the app works without OTIS.",
     "otis, space, storage, full, memory, not enough, disk, room, no space, too big, size, gb, "
     "espacio, almacenamiento, memoria llena, sin espacio, lleno, no cabe"),
    ("OTIS is slow or stops in the middle of an answer",
     "OTIS runs on your phone, so its speed depends on the phone. It also keeps answers short.\n"
     "1. Tap New chat at the top. Long chats slow OTIS down.\n"
     "2. Ask one short question at a time.\n"
     "3. If you see Starting OTIS, wait for it to finish loading.\n"
     "4. If you see Sorry, OTIS could not answer just now, ask again or tap New chat.\n"
     "5. If OTIS stops every time, close the app all the way and open it again. Then report it: Settings, Report a problem.",
     "otis, otis not working, lag, laggy, takes forever, spinning, loading, stopped working, cut off, no answer, "
     "could not answer, lento, tarda, se tarda, se detiene, se corta, no responde, no contesta"),
    ("OTIS says it needs an update",
     "OTIS can ask for two different things.\n"
     "1. If it says Update Zero Harm from the App Store or Google Play, open your app store, find Zero Harm and tap Update. "
     "Then open OTIS again.\n"
     "2. If it says OTIS has an update, connect to Wi-Fi and tap Update OTIS. It downloads once.\n"
     "3. Not a good time? Tap Not now, keep using OTIS as it is.\n"
     "The rest of the app keeps working in the meantime.",
     "otis, new version, upgrade, app store, google play, play store, old version, otis update, "
     "actualizar otis, actualizacion de otis, nueva version, pide actualizar"),
    ("OTIS is switched off or taking a break",
     "If you see OTIS is taking a short break, or another short message where the chat should be, Trainovate has switched "
     "OTIS off for now. Nothing is wrong with your phone.\n"
     "1. You cannot turn OTIS back on from the phone. Check back later.\n"
     "2. Use the rest of the app as usual. Talks and sign-in sheets do not need OTIS.\n"
     "3. For a safety question right now, ask your supervisor or safety lead. If someone is hurt, call 911.\n"
     "4. If OTIS is still off after a few days, open Settings and tap Report a problem.",
     "otis, off, switched off, turned off, disabled, break, short break, unavailable, not available, gone, missing, won't open, "
     "apagado, desactivado, no disponible, no esta, no abre, descanso"),
    ("OTIS says it does not have that",
     "OTIS answers only from Zero Harm talks, Zero Hour huddle cards and plain-language OSHA General Industry rules. It does not guess.\n"
     "1. Ask again with the plain name of the hazard or tool, like ladder, forklift or lockout.\n"
     "2. Ask one thing at a time.\n"
     "3. If it is still not covered, ask your supervisor or safety lead.\n"
     "4. For a problem with the app itself, type report an app problem, or open Settings and tap Report a problem.\n"
     "If an answer looks wrong, tap Report this answer under it.",
     "otis, don't have that, doesn't know, cannot answer, can't answer, my question, not covered, knowledge base, no answer, "
     "no sabe, no tiene, no lo tiene, no encuentra, no entiende"),

    # ---- Notifications and what shows when --------------------------------------------------------
    ("Notifications are not arriving",
     "Notifications are off until you turn them on.\n"
     "1. Open Settings (top of the Today tab). Under Notifications, turn on the ones you want.\n"
     "2. When the phone asks, allow notifications.\n"
     "3. If you see Notifications are blocked for Zero Harm on this phone, tap Open phone settings and allow them. "
     "Then come back and turn the switches on again.\n"
     "4. Know the times. Monday Minute: Monday at 5:00 AM Pacific. Weekly toolbox talk: Sunday around noon Pacific. "
     "Zero Hour episodes: Thursdays.\n"
     "5. Check that Do Not Disturb or Focus is off on the phone.\n"
     "6. Still nothing? Open Settings and tap Report a problem.",
     "notification, push, reminder, reminders, alerts, not getting, didn't get, no notifications, silent, what time, "
     "notificacion, notificaciones, aviso, avisos, no llegan, no recibo, recordatorio"),
    ("No Monday Minute is showing",
     "A new Monday Minute comes out every Monday at 5:00 AM Pacific.\n"
     "1. Open the Monday tab and pull down to refresh.\n"
     "2. If you see No signal, move to where you have signal or Wi-Fi and pull down again.\n"
     "3. A talk that is running late can come out as late as Wednesday morning.\n"
     "4. If this week's talk is still missing after that, open Settings and tap Report a problem.\n"
     "To get a notification when it is out, turn on Monday Minute in Settings.",
     "monday minute, monday, minute, talk, missing, not showing, blank, empty, nothing, no talk, where, last week, "
     "lunes, charla, no aparece, no sale, no hay, falta, vacio"),
    ("A talk is locked or not there yet",
     "Zero Harm Weekly talks open on Sunday around noon Pacific, ready for Monday. A few open sooner and show as Ready early.\n"
     "1. On the Today tab, pull down to refresh.\n"
     "2. If you see This week's talk isn't out yet, or This talk isn't available yet, it has not opened. "
     "You cannot unlock it from the phone.\n"
     "3. To run a talk today, tap Open the archive and pick one.\n"
     "4. If it is past Sunday noon Pacific and you have signal, open Settings and tap Report a problem.",
     "talk, toolbox talk, locked, lock, unlock, not available, isn't available, not out, not there, missing, coming soon, early, "
     "this week, bloqueada, no disponible, no esta, todavia no, charla, semana"),
    ("Spanish is not offered",
     "A talk shows in Spanish only when it has an approved Spanish version.\n"
     "1. Open a Zero Harm Weekly talk from the Today tab or the Archive.\n"
     "2. Look for the English and Español buttons near the top, and tap Español.\n"
     "3. No buttons? That talk has no approved Spanish yet. You cannot turn it on from the phone.\n"
     "4. Ask OTIS in Spanish and it tries to answer in Spanish.\n"
     "The Monday Minute and the app's menus are in English for now. To ask for more Spanish, open Settings and tap Report a problem.",
     "spanish, espanol, language, languages, translate, translation, english only, no spanish, change language, "
     "idioma, en espanol, traducir, traduccion, ingles, cambiar idioma, no hay espanol"),
    ("The weather and heat card is missing",
     "The weather line is at the top of the Today tab. It needs your location and a signal.\n"
     "1. On Today, tap Show local weather and heat alerts, then allow location.\n"
     "2. If that button is gone and no weather shows, open your phone's settings, find Zero Harm, and allow Location.\n"
     "3. Make sure Location is turned on for the phone.\n"
     "4. Check your signal, then close the app all the way and open it again.\n"
     "Weather comes from the US National Weather Service, so it works only in the United States. "
     "The heat and cold notes show only on days with that risk.",
     "weather, heat, heat index, temperature, forecast, cold, location, gps, permission, missing, not showing, gone, no weather, "
     "clima, tiempo, calor, temperatura, ubicacion, no aparece, no sale"),

    # ---- Crew sign-in and sign-in sheets ----------------------------------------------------------
    ("A signature will not save",
     "1. Type the person's name in Crew member name first. Without a name you see Add your name.\n"
     "2. Have the person sign in the box with a finger.\n"
     "3. Tap Save signature. The name shows below with a check mark.\n"
     "4. To start over, tap Clear and sign again.\n"
     "5. If the box will not take a signature, tap Take a group photo and type the head count instead. "
     "Or use the paper sheet: on the Monday tab, tap Print.",
     "signature, signatures, sign, signing, can't sign, finger, won't save, not saving, box, blank, crew member, name, clear, "
     "firma, firmas, firmar, no guarda, no firma, nombre, dedo"),
    ("Trouble taking the group photo",
     "1. On the Crew sign-in screen, tap Take a group photo.\n"
     "2. When the phone asks, allow the camera. Ask the crew before you take it.\n"
     "3. If the camera does not open, your photo library opens instead. Pick a photo there. To use the camera, "
     "allow Camera for Zero Harm in your phone's settings and try again.\n"
     "4. Type the head count in How many people are in the photo?\n"
     "5. Tap Retake to replace the photo, or Remove to take it off the sheet.",
     "photo, picture, pictures, camera, group photo, take photo, camera won't open, permission, retake, head count, "
     "foto, fotos, camara, no abre, tomar foto, grupo, permiso"),
    ("A sign-in sheet will not save or send",
     "1. Add at least one signature or a group photo. Until then the save buttons do not work.\n"
     "2. Under Save the sheet, fill in Your name and Your email.\n"
     "3. Tap Save sheet to my records.\n"
     "4. If you see Saved on this phone, it has not gone through yet, most often because there is no signal. "
     "The app sends it by itself the next time you open it with signal.\n"
     "5. If you see Could not build the sheet, try again. If it fails again, tap Email or share the PDF.\n"
     "6. Still not sent after a day with good signal? Report it: Settings, Report a problem.",
     "sign-in sheet, sign in sheet, sheet, save, send, won't save, not saving, not sending, failed, records, attendance, roster, "
     "hoja, asistencia, guardar, no guarda, enviar, no envia, registro"),
    ("What Save sheet to my records does",
     "Save sheet to my records does two things.\n"
     "1. It keeps the PDF on this phone. Find it in Settings under My sign-in sheets. Tap Print or Email or share there.\n"
     "2. It sends a copy, with its signatures and photo, to Trainovate Technologies, filed under the email you typed.\n"
     "3. When you see Saved to your Zero Harm records, the copy arrived.\n"
     "Deleting the app deletes the sheets on the phone, so email important ones to yourself. "
     "To ask for a copy later, tap Contact support in Settings.",
     "save sheet to my records, records, my records, where, saved, find, sheet, sheets, my sign-in sheets, copy, download, stored, "
     "donde, guardado, registros, hoja, hojas, encontrar, copia"),
    ("The PDF will not print or share",
     "1. On the Crew sign-in screen, add a signature or a group photo first.\n"
     "2. Tap Print the sheet to print. Tap Email or share the PDF to email it or save it to your files.\n"
     "3. Printing needs a printer your phone can reach, like one on the same Wi-Fi.\n"
     "4. No printer? Tap Email or share the PDF and send it to yourself.\n"
     "5. If you see Could not build the sheet or Could not make the PDF, try again in a moment. If it keeps failing, "
     "report it: Settings, Report a problem.\n"
     "Every sheet you print or share is also kept in Settings under My sign-in sheets.",
     "print, printer, printing, pdf, share, sharing, email, export, airprint, won't print, can't print, no printer, "
     "imprimir, impresora, no imprime, compartir, correo, enviar"),
    ("I left crew sign-in before saving the sheet",
     "A sheet is kept only after you tap Save sheet to my records, Print the sheet or Email or share the PDF.\n"
     "1. If you left before that, the unfinished sheet cannot be opened again.\n"
     "2. Open the talk again and tap Start crew sign-in to start a new sheet.\n"
     "3. Have the crew sign again, or take one group photo and type the head count.\n"
     "4. Before you leave the screen, tap one of the three buttons. The sheet is then in Settings under My sign-in sheets.",
     "lost, lost signatures, disappeared, gone, missing, deleted, went back, back button, unfinished, reopen, start over, sheet, "
     "perdi, perdido, se borro, borraron, desaparecio, firmas, hoja, regresar"),

    # ---- Your account and your data ---------------------------------------------------------------
    ("Signing in with your email",
     "Signing in is free and optional. There is no password.\n"
     "1. Open Settings (top of the Today tab). Under Your account, type Your name and Email.\n"
     "2. Tap Sign in.\n"
     "3. If you see Check the email address, fix it and tap Sign in again.\n"
     "You are signed in right away, even with no signal. You get Zero Harm Weekly by email each week and can unsubscribe anytime. "
     "Everything in the app works without signing in.",
     "sign in, signin, sign up, signup, login, log in, account, email, password, register, can't sign in, forgot password, "
     "iniciar sesion, registrarse, cuenta, correo, contrasena, entrar, no me deja entrar"),
    ("Changing your name or email",
     "Only the phone that first signed up with an email can change that sign-up.\n"
     "1. On that phone, open Settings and tap Remove my info.\n"
     "2. Type the new name and email, then tap Sign in.\n"
     "3. On any other phone the change is not saved, and the app tells you so.\n"
     "4. No longer have the first phone? Open Settings and tap Report a problem, and say what to change.\n"
     "The name on a sign-in sheet is separate. Change it under Save the sheet on the Crew sign-in screen.",
     "change name, change email, wrong name, wrong email, typo, misspelled, edit, update, new email, new phone, details, profile, "
     "cambiar nombre, cambiar correo, nombre mal, corregir, editar, telefono nuevo"),
    ("Removing your info",
     "1. Open Settings (top of the Today tab). Under Your account, tap Remove my info, then tap Remove.\n"
     "2. On the phone that first signed up, this ends your sign-up, and the app stops adding you to Zero Harm Weekly.\n"
     "3. On any other phone, nothing is removed right away. The app sends a request and a person removes your info. "
     "You see We got your request.\n"
     "4. With no signal, it waits on the phone and sends later.\n"
     "5. If you joined Zero Harm Weekly another way, also tap Unsubscribe in one of its emails.",
     "remove my info, remove, unsubscribe, stop emails, sign out, log out, logout, leave, opt out, take me off, "
     "quitar, quitar mi informacion, cancelar, darme de baja, cerrar sesion, salir, no mas correos"),
    ("Deleting your data",
     "1. To end your sign-up, open Settings and tap Remove my info.\n"
     "2. To delete everything tied to your email (sign-ups, saved sign-in sheets, suggestions, comments and problem reports), tap Delete my data "
     "in Settings. It opens an email to us. Send it from the address you signed up with.\n"
     "3. To clear what is kept on the phone, like sign-in sheets and the OTIS download, delete the app.\n"
     "4. To stop the daily count and crash reports, turn off Daily usage count and Crash reports in Settings.",
     "delete, delete my data, delete account, erase, wipe, privacy, personal data, my data, forget me, "
     "borrar, eliminar, mis datos, datos, privacidad, borrar cuenta, eliminar cuenta"),

    # ---- Reporting, crash reports and who to ask --------------------------------------------------
    ("How to report a problem and see the reply",
     "1. Open Settings (top of the Today tab) and tap Report a problem. Or type report an app problem to OTIS.\n"
     "2. Say what happened and what you tapped just before.\n"
     "3. Add your email only if you want us to write back.\n"
     "4. Tap Send report (in OTIS, tap Send). You get a reference like ZH-123. With no signal the report is saved and sends later.\n"
     "5. To see its status and our reply, open Settings and tap My reports.",
     "report, report a problem, bug, ticket, issue, complaint, feedback, my reports, reply, status, reference, "
     "reportar, reportar un problema, queja, falla, problema, respuesta"),
    ("How to flag a wrong OTIS answer",
     "OTIS can be wrong. If an answer looks wrong or unsafe:\n"
     "1. Do not act on it. Follow your site's written steps and ask your supervisor.\n"
     "2. Tap Report this answer under the answer.\n"
     "3. Confirm. That one question and answer go to Trainovate so a person can review them. The rest of the chat is not sent.\n"
     "A flag is for OTIS answers. For a problem with the app, tap Report a problem in Settings.",
     "wrong answer, wrong, bad answer, incorrect, mistake, unsafe, flag, report answer, report this answer, otis is wrong, lied, "
     "respuesta incorrecta, equivocado, mal, reportar respuesta, error"),
    ("What a crash report sends and how to turn it off",
     "When the app hits an error, it can send a crash report so we can fix it.\n"
     "1. It sends the error, the screen you were on, the time, the app version, and your phone model and system version.\n"
     "2. It does not send your name, your email or your OTIS chat. It carries a random id for this copy of the app, "
     "and the server keeps only a scrambled form of it.\n"
     "3. To turn it off, open Settings and turn off Crash reports. Reports still waiting on the phone are deleted.\n"
     "4. Not every sudden close is caught. If the app keeps closing, tap Report a problem in Settings.",
     "diagnostics, error report, privacy, what is sent, tracking, turn off, switch, data, send, sends, automatic, "
     "reporte de fallas, reportes, privacidad, que se envia, apagar, desactivar"),
    ("Who to contact for help",
     "1. Someone hurt or in danger: call 911 first. The app is not for emergencies.\n"
     "2. A safety question about your job: ask your supervisor or safety lead.\n"
     "3. A problem with the app: open Settings (top of the Today tab) and tap Report a problem. Read the reply in My reports.\n"
     "4. Your account or your data: tap Contact support in Settings. It opens an email to Trainovate Technologies.\n"
     "Zero Harm is free and made by Trainovate Technologies in Las Vegas.",
     "contact, support, help, phone number, email, who, call, customer service, trainovate, talk to a person, human, "
     "contacto, soporte, ayuda, telefono, correo, hablar con alguien"),
]

# ---- The app help entries that were already there -----------------------------------------------------------------
# The six from the first seed (0005). They become support. "OSHA rules in OTIS: what they cover" carries the same
# source label but stays a safety entry: it explains the safety content, and a safety question has to keep finding it.
EXISTING = [
    "What OTIS is",
    "How to run a toolbox talk in the app",
    "Finding past talks",
    "Suggesting a toolbox talk topic",
    "Regulatory alerts",
    "Zero Harm Weekly",
]
STAYS_SAFETY = "OSHA rules in OTIS: what they cover"

# Three of them no longer matched the app (a button that is now called something else, a link that moved). Each is
# replaced only while it still reads exactly as it was seeded, so wording the owner changed is never overwritten.
# title: (body as seeded, tags as seeded, new body, new tags)
REWRITES = {
    "How to run a toolbox talk in the app": (
        "Open this week's talk on the Today screen. Read it with your crew and ask the crew question. Tap Start crew sign-in. "
        "Crew members can each type their name and sign with a finger, or the person running the talk can take one group photo "
        "and enter the head count, or both. Then tap Save sheet to my records to keep the PDF, or Share the PDF.",
        "sign-in, signature, group photo, attendance, records, pdf",
        "1. Open the talk. The Monday Minute is on the Monday tab. The Zero Harm Weekly talk is on the Today tab: tap Open the talk.\n"
        "2. Read it to your crew and ask the crew question.\n"
        "3. Tap Start crew sign-in.\n"
        "4. Each person types a name, signs with a finger and taps Save signature. Or tap Take a group photo and type the head count. "
        "You can do both.\n"
        "5. Tap Save sheet to my records, Print the sheet or Email or share the PDF.",
        "how to, run a talk, toolbox talk, start, crew sign-in, sign-in, signature, group photo, attendance, records, pdf, "
        "como, dar la charla, charla, asistencia, firma",
    ),
    "Finding past talks": (
        "Open the Archive from the Today screen to find every past Zero Harm Weekly talk. Search by topic, or filter by month theme.",
        "archive, past talks, search, old issue",
        "1. On the Today tab, tap Open the archive.\n"
        "2. Type a word in Search toolbox talks, like ladder or heat. Or tap a month theme to filter.\n"
        "3. Tap a talk to open it.\n"
        "4. For older Monday Minutes, open the Monday tab, scroll to the bottom and tap Past Monday Minutes.",
        "archive, past talks, old talks, search, find, last week, previous, old issue, history, "
        "archivo, charlas pasadas, buscar, anteriores, semana pasada",
    ),
    "Suggesting a toolbox talk topic": (
        "Tap Suggest a talk in the Archive or on the Learn tab. Tell us the topic and what happened at your site. Your idea goes to the "
        "Zero Harm Weekly team.",
        "suggest, idea, topic, request",
        "1. On the Today tab, tap Suggest a talk. Or tap Suggest a toolbox talk at the bottom of the Archive.\n"
        "2. Type the topic. Add what happened or why it matters if you want. Leave out names and anything that identifies an injured person.\n"
        "3. Tap Send my idea. Sending needs a signal.\n"
        "Your idea goes to the Zero Harm Weekly team.",
        "suggest, suggestion, idea, topic, request, send my idea, sugerir, sugerencia, tema, proponer",
    ),
}

# "What OTIS is" said nothing about what leaves the phone. Reporting a problem or an answer now can, when the person
# chooses to, so the entry says so. One sentence is added after the one below, and only if that sentence is still there.
WHAT_OTIS_IS_ANCHOR = "OTIS runs on your phone and works with no signal."
WHAT_OTIS_IS_ADDED = " Your questions stay on the phone unless you choose to report a problem or report an answer."
WHAT_OTIS_IS_TAGS = (
    "otis, assistant, chatbot, help, who are you, osha, general industry",  # as the earlier seeds left them
    "otis, what is otis, about otis, assistant, chatbot, who are you, osha, general industry, privacy, que es otis, quien eres, asistente",
)


# Two of them had English tags only, and every entry is sent as English, so a Spanish question could not find them.
# Spanish words are added, only while the tags are still as first seeded. title: (tags as seeded, new tags)
SPANISH_TAGS = {
    "Regulatory alerts": (
        "alert, rule, regulation, osha, nevada, law",
        "alert, alerts, rule, rules, regulation, regulatory, osha, nevada, law, new rule, "
        "alerta, alertas, regla, reglas, regulacion, norma, normas, ley, leyes, reglas nuevas",
    ),
    "Zero Harm Weekly": (
        "newsletter, weekly, sunday, email, subscribe",
        "newsletter, weekly, sunday, email, subscribe, zero harm weekly, "
        "boletin, semanal, domingo, correo, suscribir, suscribirme, suscripcion",
    ),
}


def seed(apps, schema_editor):
    KbEntry = apps.get_model("talks", "KbEntry")

    for title, body, tags in ENTRIES:
        KbEntry.objects.get_or_create(title=title, defaults={"body": body, "source": SOURCE, "tags": tags, "kind": SUPPORT})

    # Entries the owner added under the same label are app help too. save(), not update(): the change has to move
    # updated_at, which is part of the content version phones watch.
    old = KbEntry.objects.filter(title__in=EXISTING) | KbEntry.objects.filter(source=SOURCE)
    for entry in old.exclude(title=STAYS_SAFETY).exclude(kind=SUPPORT):
        entry.kind = SUPPORT
        if entry.title in REWRITES:
            was, was_tags, now, now_tags = REWRITES[entry.title]
            if entry.body.strip() == was:
                entry.body = now
                if entry.tags.strip() == was_tags:
                    entry.tags = now_tags
        if entry.title == "What OTIS is":
            if WHAT_OTIS_IS_ANCHOR in entry.body and WHAT_OTIS_IS_ADDED not in entry.body:
                entry.body = entry.body.replace(WHAT_OTIS_IS_ANCHOR, WHAT_OTIS_IS_ANCHOR + WHAT_OTIS_IS_ADDED, 1)
            if entry.tags.strip() == WHAT_OTIS_IS_TAGS[0]:
                entry.tags = WHAT_OTIS_IS_TAGS[1]
        if entry.title in SPANISH_TAGS and entry.tags.strip() == SPANISH_TAGS[entry.title][0]:
            entry.tags = SPANISH_TAGS[entry.title][1]
        entry.save()


def unseed(apps, schema_editor):
    """Back to how 0020 left it: the new entries gone, the old ones safety entries with their first wording, unless
    someone has edited them since."""
    KbEntry = apps.get_model("talks", "KbEntry")
    KbEntry.objects.filter(title__in=[title for title, _, _ in ENTRIES], kind=SUPPORT).delete()
    for entry in KbEntry.objects.filter(kind=SUPPORT):
        entry.kind = SAFETY
        if entry.title in REWRITES:
            was, was_tags, now, now_tags = REWRITES[entry.title]
            if entry.body == now:
                entry.body = was
            if entry.tags == now_tags:
                entry.tags = was_tags
        if entry.title == "What OTIS is":
            entry.body = entry.body.replace(WHAT_OTIS_IS_ADDED, "")
            if entry.tags == WHAT_OTIS_IS_TAGS[1]:
                entry.tags = WHAT_OTIS_IS_TAGS[0]
        if entry.title in SPANISH_TAGS and entry.tags == SPANISH_TAGS[entry.title][1]:
            entry.tags = SPANISH_TAGS[entry.title][0]
        entry.save()


class Migration(migrations.Migration):
    dependencies = [("talks", "0020_kbentry_kind")]
    operations = [migrations.RunPython(seed, unseed)]
