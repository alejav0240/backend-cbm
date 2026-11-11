# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build-only dependencies stay out of the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip \
    && python -m pip wheel --wheel-dir /wheels -r requirements.txt

COPY . .

# Collect static assets during the build without requiring production secrets.
RUN python -m pip install --no-index --find-links=/wheels -r requirements.txt

RUN SECRET_KEY=build-only-secret \
    DEBUG=False \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Runtime libraries only. SSH clients and compilers are intentionally excluded.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        libgl1 \
        libglib2.0-0 \
        libpq5 \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
# mediapipe already supplies the OpenCV implementation required by the runtime;
# omit the duplicate headless wheel from the final image.
RUN rm -f /wheels/opencv_python_headless*.whl \
    && python -m pip install /wheels/* \
    && rm -rf /wheels

RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app

COPY --from=builder --chown=app:app /build /app

USER app

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
