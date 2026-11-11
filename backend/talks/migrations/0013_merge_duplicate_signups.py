from django.db import migrations


def merge_duplicate_signups(AppSignup):
    """One row per email (ignoring capitals). The earliest row is kept, with its sign-up time. Anything it is missing
    (name, company, the GoHighLevel id) is filled in from the later rows, and an offers opt-in on any row is kept.
    Returns how many rows were deleted."""
    groups = {}
    for row in AppSignup.objects.order_by("created_at", "id"):
        groups.setdefault(row.email.strip().lower(), []).append(row)
    deleted = 0
    for email, rows in groups.items():
        keep, extras = rows[0], rows[1:]
        for extra in extras:
            for field in ("first_name", "company"):
                if not getattr(keep, field) and getattr(extra, field):
                    setattr(keep, field, getattr(extra, field))
            if not keep.ghl_contact_id and extra.ghl_contact_id:
                keep.ghl_contact_id, keep.ghl_synced_at = extra.ghl_contact_id, extra.ghl_synced_at
            keep.wants_offers = keep.wants_offers or extra.wants_offers
        keep.email = email
        if keep.source not in ("welcome", "settings"):
            keep.source = "settings"  # every sign-up before the welcome screen came from Settings
        AppSignup.objects.filter(pk__in=[e.pk for e in extras]).delete()
        keep.save()
        deleted += len(extras)
    return deleted


def forwards(apps, schema_editor):
    merge_duplicate_signups(apps.get_model("talks", "AppSignup"))


class Migration(migrations.Migration):

    dependencies = [
        ("talks", "0012_signup_leads_and_alerts"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
