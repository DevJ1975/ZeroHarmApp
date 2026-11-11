from django.db import migrations, models


class Migration(migrations.Migration):
    """The phone now lives in SignupPhone (copied there by 0016), so the old one-phone column goes."""

    dependencies = [
        ("talks", "0016_copy_signup_phones"),
    ]

    operations = [
        migrations.RemoveField(model_name="appsignup", name="install_hash"),
    ]
