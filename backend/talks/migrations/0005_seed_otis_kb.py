"""Starter OTIS knowledge base: how the app works and the safety basics Zero Harm Weekly already teaches. Edit in the admin."""
from django.db import migrations

ENTRIES = [
    ("Someone is hurt or in danger right now",
     "Call 911 first. Do not wait for OTIS or the app. Then follow your site's emergency plan and tell your supervisor. "
     "Stay with the person if it is safe, and send someone to meet the ambulance and lead them in.",
     "Zero Harm Weekly", "emergency, injury, hurt, 911, ambulance, unconscious, bleeding"),
    ("What OTIS is",
     "OTIS is the Zero Harm safety assistant from Trainovate Technologies. OTIS answers only from Zero Harm Weekly toolbox talks "
     "and this knowledge base, runs on your phone, and works with no signal. OTIS can be wrong. Always follow your site's written "
     "procedures and ask your supervisor or safety lead when you are not sure. OTIS is not legal or medical advice.",
     "Zero Harm app help", "otis, assistant, chatbot, help, who are you"),
    ("Not sure it is safe",
     "Not sure it's safe? Stop and ask. Always follow your site's written steps. Zero Harm Weekly talks add to your required "
     "training. They do not replace it.",
     "Zero Harm Weekly", "unsure, stop work, ask, procedure, training"),
    ("How to run a toolbox talk in the app",
     "Open this week's talk on the Today screen. Read it with your crew and ask the crew question. Tap Start crew sign-in. "
     "Crew members can each type their name and sign with a finger, or the person running the talk can take one group photo "
     "and enter the head count, or both. Then tap Save sheet to my records to keep the PDF, or Share the PDF.",
     "Zero Harm app help", "sign-in, signature, group photo, attendance, records, pdf"),
    ("Finding past talks",
     "Open the Archive from the Today screen to find every past Zero Harm Weekly talk. Search by topic, or filter by month theme.",
     "Zero Harm app help", "archive, past talks, search, old issue"),
    ("Suggesting a toolbox talk topic",
     "Tap Suggest a talk in the Archive or on the Learn tab. Tell us the topic and what happened at your site. Your idea goes to the "
     "Zero Harm Weekly team.",
     "Zero Harm app help", "suggest, idea, topic, request"),
    ("Regulatory alerts",
     "Regulatory alerts are short, plain-language summaries of new federal OSHA, Nevada and Las Vegas rules that could affect your "
     "site. They are for awareness, not legal advice. Check the rule itself for what applies to you. Turn on Regulatory alerts in "
     "Settings to get a notification.",
     "Zero Harm app help", "alert, rule, regulation, osha, nevada, law"),
    ("Zero Harm Weekly",
     "Zero Harm Weekly is a free weekly safety newsletter. Each issue is a 5-minute toolbox talk with a story and a crew question, "
     "sent every Sunday around noon Pacific so it is ready for Monday's meeting. The talk also appears in this app.",
     "Zero Harm app help", "newsletter, weekly, sunday, email, subscribe"),
]


def seed(apps, schema_editor):
    KbEntry = apps.get_model("talks", "KbEntry")
    for title, body, source, tags in ENTRIES:
        KbEntry.objects.get_or_create(title=title, defaults={"body": body, "source": source, "tags": tags})


class Migration(migrations.Migration):
    dependencies = [("talks", "0004_otis_kb_suggestions")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
