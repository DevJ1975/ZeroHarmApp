import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Phones linked to a sign-up, and the tags a contact already had before the app tagged it."""

    dependencies = [
        ("talks", "0014_one_signup_per_email"),
    ]

    operations = [
        migrations.CreateModel(
            name="SignupPhone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("install_hash", models.CharField(db_index=True, help_text="Hashed random id of the phone. Not a person.", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("signup", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="phones", to="talks.appsignup")),
            ],
            options={
                "ordering": ["created_at"],
                "constraints": [models.UniqueConstraint(fields=("signup", "install_hash"), name="one_link_per_phone_per_signup")],
            },
        ),
        migrations.AddField(
            model_name="appsignup",
            name="ghl_had_tags",
            field=models.JSONField(blank=True, null=True, help_text="Newsletter tags the GoHighLevel contact already had before the app "
                                   "tagged it. A removal leaves these on. Empty until the first sync."),
        ),
        migrations.AddField(
            model_name="signupremoval",
            name="ghl_had_tags",
            field=models.JSONField(blank=True, null=True, help_text="Copied from the sign-up: tags the contact had before the app"),
        ),
        migrations.AddField(
            model_name="signupremoval",
            name="attempts",
            field=models.PositiveIntegerField(default=0, help_text="Tries at the GoHighLevel step"),
        ),
        migrations.AddField(
            model_name="signupremoval",
            name="last_tried_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
