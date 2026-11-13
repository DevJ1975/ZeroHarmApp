# Zero Harm backend: Django + gunicorn. Same image runs on your Mac (OrbStack) and on Railway.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files for the admin are baked into the image; the key here is a build-time placeholder only.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# City database for the back office's "Where the app is used" (free DB-IP Lite, CC BY 4.0). Downloaded as appuser so
# the file isn't copied again by the chown above. If db-ip.com can't be reached the build carries on without it:
# places from the network are then blank until the next build. Same placeholder key as collectstatic.
RUN DJANGO_SECRET_KEY=build-only python manage.py geo_update || echo "Geo: skipped, the build continues without the city database"

EXPOSE 8000

# Migrations and the shared cache table are set up on every start (both are a no-op when nothing changed), then
# gunicorn serves on $PORT. One process with 8 threads: the work is waiting on the database and other services, so
# threads handle it, memory stays low, and rate limits and caches (kept in process memory) are the same for every
# request. 150 s covers a slow sign-in sheet upload to GoHighLevel and lets a console Spanish draft (Claude, up to
# 120 s) finish instead of the worker being killed.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && exec gunicorn zeroharm.wsgi:application --bind 0.0.0.0:${PORT} --worker-class gthread --workers 1 --threads 8 --timeout 150 --graceful-timeout 30 --access-logfile -"]
