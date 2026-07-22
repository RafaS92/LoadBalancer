FROM python:3.12.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app \
        --shell /usr/sbin/nologin app

COPY pyproject.toml README.md ./
COPY backend/src ./backend/src

RUN python -m pip install --no-cache-dir --no-compile .

USER app:app

EXPOSE 8080
STOPSIGNAL SIGTERM

CMD ["load-balancer", "--listen-host", "0.0.0.0", "--listen-port", "8080"]
