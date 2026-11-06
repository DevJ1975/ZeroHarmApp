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

# Migrations run on every start (they are a no-op when nothing changed), then gunicorn serves on $PORT.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn zeroharm.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --access-logfile -"]
