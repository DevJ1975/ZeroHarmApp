"""Crash reports can no longer be matched to a person, and a report sent again is counted once.

Crash rows are now stored under their own hash of the install id (support/api.py crash_hash), and a crash ticket keeps
no install hash. Rows saved before this carry the hash a sign-up from the same phone carries. That cannot be turned
into the new one (the raw install id was never kept), so it is replaced by a label that matches nothing. The only cost:
a phone sending one of those old reports again would have it counted again.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def unlink_old_crash_rows(apps, schema_editor):
    Ticket = apps.get_model("support", "Ticket")
    CrashReport = apps.get_model("support", "CrashReport")
    Ticket.objects.filter(kind="crash").exclude(install_hash="").update(install_hash="")
    for pk in CrashReport.objects.exclude(install_hash__startswith="unlinked:").values_list("pk", flat=True).iterator():
        CrashReport.objects.filter(pk=pk).update(install_hash=f"unlinked:{pk}")


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='owner_alert_unsure_at',
            field=models.DateTimeField(blank=True, help_text='When an email about it was handed to GoHighLevel but no answer came back in time. It may have arrived; the cron sends it again later in a list, marked as possibly a repeat.', null=True),
        ),
        migrations.AlterField(
            model_name='crashreport',
            name='install_hash',
            field=models.CharField(help_text="The phone's random id, hashed under its own label for crashes: it cannot be matched to a sign-up or a person's report.", max_length=64),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='install_hash',
            field=models.CharField(blank=True, help_text="Hashed random id of the phone that sent a person's report; the same hash a sign-up from that phone carries. Blank on a crash ticket.", max_length=64),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='reply',
            field=models.TextField(blank=True, help_text='Your answer. On a problem report the person sees it in the app under My reports. On a flagged OTIS answer or a crash it is a private note: the person never sees it. Write to them by email instead, if they gave one.', max_length=2000),
        ),
        migrations.CreateModel(
            name='CrashKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('install_hash', models.CharField(help_text='The same crash-only hash as CrashReport.install_hash.', max_length=64)),
                ('client_key', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='support.ticket')),
            ],
            options={
                'verbose_name': 'counted crash report',
                'indexes': [models.Index(fields=['created_at'], name='support_crashkey_when')],
                'constraints': [models.UniqueConstraint(fields=('install_hash', 'client_key'), name='support_count_each_crash_report_once')],
            },
        ),
        migrations.RunPython(unlink_old_crash_rows, migrations.RunPython.noop),
    ]
