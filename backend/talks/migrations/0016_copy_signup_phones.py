from django.db import migrations


def copy_phones(AppSignup, SignupPhone):
    """Each sign-up's one saved phone becomes its first linked phone. Safe to run again."""
    made = 0
    for signup_id, install_hash, created_at in AppSignup.objects.exclude(install_hash="").values_list("pk", "install_hash", "created_at"):
        _, new = SignupPhone.objects.get_or_create(signup_id=signup_id, install_hash=install_hash)
        if new:
            SignupPhone.objects.filter(signup_id=signup_id, install_hash=install_hash).update(created_at=created_at)
            made += 1
    return made


def forwards(apps, schema_editor):
    copy_phones(apps.get_model("talks", "AppSignup"), apps.get_model("talks", "SignupPhone"))


def backwards(apps, schema_editor):
    """Puts the earliest linked phone back on the sign-up row."""
    AppSignup, SignupPhone = apps.get_model("talks", "AppSignup"), apps.get_model("talks", "SignupPhone")
    for signup in AppSignup.objects.filter(install_hash=""):
        phone = SignupPhone.objects.filter(signup=signup).order_by("created_at").first()
        if phone:
            signup.install_hash = phone.install_hash
            signup.save(update_fields=["install_hash"])


class Migration(migrations.Migration):
    # Kept apart from the column changes on either side: Postgres won't alter a table in the same transaction that
    # just wrote rows pointing at it.

    dependencies = [
        ("talks", "0015_signup_phones"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
