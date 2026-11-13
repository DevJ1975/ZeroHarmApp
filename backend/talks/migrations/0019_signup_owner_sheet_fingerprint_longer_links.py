"""Round two of the fixes, all the talks model changes in one file:

- AppSignup.removal_requested_at: when a phone that does not own the sign-up asked to remove it (the owner decides).
- SigninSheet.pdf_sha256: a fingerprint of the PDF, so a sheet a phone sends twice is recognised after a restart and
  after the stored PDF has been emptied. SigninSheet.attempts: tries at GoHighLevel (nothing counts it yet).
- Link and image addresses on talks and feed items go from 200 to 500 characters, like every other address column.

Sheets that still hold their PDF (GoHighLevel has not taken them yet) get their fingerprint here. Sheets already
forwarded have no PDF left to fingerprint; a resend of one of those is stored once more, as before."""
import hashlib

from django.db import migrations, models


def fingerprint_waiting_sheets(SigninSheet):
    """Returns how many sheets were given a fingerprint. One PDF in memory at a time: they can be several megabytes."""
    done = 0
    for pk in list(SigninSheet.objects.filter(pdf_sha256="").values_list("pk", flat=True)):
        pdf = bytes(SigninSheet.objects.filter(pk=pk).values_list("pdf", flat=True).first() or b"")
        if pdf:
            done += SigninSheet.objects.filter(pk=pk).update(pdf_sha256=hashlib.sha256(pdf).hexdigest())
    return done


def forwards(apps, schema_editor):
    fingerprint_waiting_sheets(apps.get_model("talks", "SigninSheet"))


# The new not-null columns carry a database default (db_default) as well as a Python one: during a deploy the old
# container keeps serving for a moment after this has run, and its inserts do not know these columns exist.
class Migration(migrations.Migration):
    dependencies = [("talks", "0018_shared_cache_table")]

    operations = [
        migrations.AddField(
            model_name="appsignup",
            name="removal_requested_at",
            field=models.DateTimeField(blank=True, null=True, help_text="A phone other than the one that made this sign-up "
                                       "asked to remove it. Nothing was deleted: check it, then delete the sign-up or clear this."),
        ),
        migrations.AddField(
            model_name="signinsheet",
            name="pdf_sha256",
            field=models.CharField(blank=True, db_default="", db_index=True, editable=False, max_length=64, help_text="Fingerprint (SHA-256) of the PDF as it arrived"),
        ),
        migrations.AddField(
            model_name="signinsheet",
            name="attempts",
            field=models.PositiveIntegerField(default=0, db_default=0, help_text="Tries at sending it to GoHighLevel"),
        ),
        migrations.AlterField(model_name="toolboxtalk", name="hero_url", field=models.URLField(blank=True, max_length=500)),
        migrations.AlterField(model_name="toolboxtalk", name="pdf_url", field=models.URLField(blank=True, max_length=500, help_text="Printable toolbox PDF")),
        migrations.AlterField(
            model_name="feeditem",
            name="link_url",
            field=models.URLField(blank=True, max_length=500, help_text="Where the button goes (course, tool, video, source rule)"),
        ),
        migrations.AlterField(model_name="feeditem", name="image_url", field=models.URLField(blank=True, max_length=500)),
        # Last, after every column change. Going back needs nothing: the column goes with its fingerprints.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
