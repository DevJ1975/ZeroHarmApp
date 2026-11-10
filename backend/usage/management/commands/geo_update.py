import datetime as dt
import gzip
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from usage import geo

URL = "https://download.db-ip.com/free/dbip-city-lite-{month:%Y-%m}.mmdb.gz"
MIN_BYTES = 1024 * 1024  # the real file is tens of megabytes; anything tiny is an error page, not a database


def fetch(url):
    """Open the download. Kept separate so the tests can stand in for the network."""
    request = urllib.request.Request(url, headers={"User-Agent": "geo-update"})
    return urllib.request.urlopen(request, timeout=120)


class Command(BaseCommand):
    help = ("Downloads this month's free DB-IP 'IP to City Lite' database (CC BY 4.0, credit: IP geolocation by DB-IP) to "
            "GEOIP_DB_PATH. Run when the image is built. A failed download is reported, never an error.")

    def handle(self, *args, **opts):
        target = Path(settings.GEOIP_DB_PATH)
        this_month = timezone.localdate().replace(day=1)
        last_month = (this_month - dt.timedelta(days=1)).replace(day=1)  # DB-IP posts each month's file a little late
        problems = []
        for month in (this_month, last_month):
            url = URL.format(month=month)
            try:
                size = self._download(url, target)
            except Exception as err:
                problems.append(f"{month:%Y-%m}: {err}")
                continue
            geo.reset()
            self.stdout.write(f"Geo: saved the {month:%Y-%m} DB-IP city database to {target} ({size / 1_000_000:.1f} MB)")
            return
        kept = "The database already on disk stays in use." if target.exists() else "Places from the network will be blank until it works."
        self.stdout.write(f"Geo: could not download the DB-IP city database ({'; '.join(problems)}). {kept}")

    def _download(self, url, target: Path) -> int:
        """Gunzip into a temporary file next to the target, then swap it in, so a half-written file is never read."""
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=target.parent, prefix=".geo-", suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as out, fetch(url) as response, gzip.GzipFile(fileobj=response) as unzipped:
                shutil.copyfileobj(unzipped, out, 1024 * 1024)
            size = os.path.getsize(tmp)
            if size < MIN_BYTES:
                raise ValueError(f"the file is only {size} bytes")
            os.chmod(tmp, 0o644)
            os.replace(tmp, target)
            return size
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
