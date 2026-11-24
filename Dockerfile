# syntax=docker/dockerfile:1.7

FROM cgr.dev/chainguard/python:latest-dev@sha256:3ca53097911a867be4f8190b8bc272d1465e9d95ef32ecc2cd70d841e2baeac3 AS builder

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build-only dependencies stay out of the runtime image.
RUN apk add --no-cache build-base postgresql-dev

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

FROM cgr.dev/chainguard/python:latest-dev@sha256:3ca53097911a867be4f8190b8bc272d1465e9d95ef32ecc2cd70d841e2baeac3 AS runtime

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

RUN apk add --no-cache \
        glib \
        libglvnd \
        libsndfile \
        libx11 \
        libxcb

COPY --from=builder /wheels /wheels
# mediapipe already supplies the OpenCV implementation required by the runtime;
# omit the duplicate headless wheel from the final image.
RUN rm -f /wheels/opencv_python_headless*.whl \
    && python -m pip install /wheels/* \
    && rm -rf /wheels \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R nonroot:nonroot /app

COPY --from=builder --chown=nonroot:nonroot /build /app

# Application code is immutable at runtime; only runtime data directories stay writable.
RUN find /app -type d -exec chmod 0555 {} + \
    && find /app -type f -exec chmod 0444 {} + \
    && chmod 0755 /app/media /app/staticfiles

USER nonroot

EXPOSE 8000

ENTRYPOINT []

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=3)"

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
