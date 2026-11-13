"""Creates the "shared" database cache table (settings.CACHES), so it exists wherever migrate runs:
Railway, docker compose, runserver and tests. createcachetable skips tables that already exist."""
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", "--database", schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("talks", "0017_remove_appsignup_install_hash")]
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
