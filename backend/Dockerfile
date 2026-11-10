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

EXPOSE 8000

# Migrations and the shared cache table are set up on every start (both are a no-op when nothing changed),
# then gunicorn serves on $PORT. The 150 s timeout lets a console Spanish draft (Claude, up to 120 s) finish
# instead of the worker being killed at gunicorn's default 30 s.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && exec gunicorn zeroharm.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 150 --access-logfile -"]
