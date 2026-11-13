from django.db import migrations, models


class Migration(migrations.Migration):
    """Its own migration, after 0008 has set aside any second talk for a week. Kept apart so the index is not made in
    the transaction that just changed rows of the table, which PostgreSQL can refuse ("pending trigger events")."""

    dependencies = [
        ("monday", "0008_lock_owner_gate_pending_screen_failures"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="mondayminute",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "blocked"), _negated=True), fields=("week",), name="one_talk_per_week"
            ),
        ),
    ]
