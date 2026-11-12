from django.db import migrations, models
from django.utils import timezone


def set_aside_duplicate_weeks(apps, schema_editor):
    """Until now nothing stopped two talks for one week. The next migration adds that rule, and it could not be added
    while such a pair exists, so keep one talk per week and set the others aside as blocked drafts (nothing is deleted).
    Kept: the one that is out or ready first, then one waiting for approval, then a pulled one; among equals, one a
    person approved, then the one written first."""
    MondayMinute = apps.get_model("monday", "MondayMinute")
    rank = {"ready": 0, "held": 1, "pulled": 2}
    by_week = {}
    for m in MondayMinute.objects.exclude(status="blocked").order_by("pk"):
        by_week.setdefault(m.week, []).append(m)
    for week, talks in by_week.items():
        talks.sort(key=lambda m: (rank.get(m.status, 3), not m.approved_by_person, m.pk))
        for extra in talks[1:]:
            extra.check_log = ((extra.check_log + "\n" if extra.check_log else "")
                               + f"Set aside {timezone.now():%b %d, %Y}: a second talk for the week of {week:%b %d}, which was "
                                 f"{extra.status} until then. Talk {talks[0].pk} is the one kept.")
            extra.status = "blocked"
            extra.save(update_fields=["status", "check_log"])


def mark_talks_not_out_yet(apps, schema_editor):
    """Talks the safety gate already let through that have not reached their publish time get the same last check at
    publish time as talks written from now on. Talks that are already out, and talks a person approved, are left alone."""
    MondayMinute = apps.get_model("monday", "MondayMinute")
    MondayMinute.objects.filter(status="ready", approved_by_person=False, publish_at__gt=timezone.now()).update(gate_pending=True)


# The new not-null columns carry a database default (db_default) as well as a Python one: during a deploy the old
# container keeps serving for a moment after this has run, and its inserts do not know these columns exist.
class Migration(migrations.Migration):

    dependencies = [
        ("monday", "0007_approval_and_conclusive_runs"),
    ]

    operations = [
        migrations.AddField(
            model_name="mondaylock",
            name="owner",
            field=models.CharField(blank=True, db_default="", help_text="Random id of the run holding the lock", max_length=40),
        ),
        migrations.AlterField(
            model_name="mondaylock",
            name="locked_at",
            field=models.DateTimeField(help_text="Last time the run holding the lock said it was still working"),
        ),
        migrations.AddField(
            model_name="mondaycomment",
            name="screen_failures",
            field=models.PositiveSmallIntegerField(
                default=0,
                db_default=0,
                help_text="Times the AI check could not give an answer for this comment. After a few it is hidden for a person to look at",
            ),
        ),
        migrations.AddField(
            model_name="mondayminute",
            name="gate_pending",
            field=models.BooleanField(
                default=False,
                db_default=False,
                help_text="The safety gate let this talk through when it was written. It is checked once more at the moment the talk goes out, and the talk is not shown until then",
            ),
        ),
        migrations.RunPython(set_aside_duplicate_weeks, migrations.RunPython.noop),
        migrations.RunPython(mark_talks_not_out_yet, migrations.RunPython.noop),
    ]
