FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=ClipAI.settings

WORKDIR /app

# System deps (install git for pip VCS if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY req.txt /app/req.txt
RUN python -m pip install --upgrade pip && pip install -r req.txt

COPY . /app

EXPOSE 8000

CMD ["/bin/sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]


