"""The Settings switch is now called "Daily usage count" (it is not anonymous: it uses the same scrambled id as a sign-up).
A database that ran 0021 before its wording changed gets the new name here. save(), not update(), so the content version phones watch moves."""
from django.db import migrations

OLD, NEW = "Anonymous usage count", "Daily usage count"


def rename(apps, schema_editor, old=OLD, new=NEW):
    KbEntry = apps.get_model("talks", "KbEntry")
    for entry in KbEntry.objects.filter(body__contains=old):
        entry.body = entry.body.replace(old, new)
        entry.save()


def back(apps, schema_editor):
    rename(apps, schema_editor, NEW, OLD)


class Migration(migrations.Migration):
    dependencies = [("talks", "0021_seed_support_kb")]
    operations = [migrations.RunPython(rename, back)]
