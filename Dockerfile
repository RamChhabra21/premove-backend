FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# ── uv / uvx (required by browser-use's ChatBrowserUse model) ──────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# ── System dependencies for Playwright headless browsers ───────────────────
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    # Playwright / Chromium runtime deps
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ─────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Install Playwright browser binaries ────────────────────────────────────
RUN playwright install chromium

# ── App code ────────────────────────────────────────────────────────────────
COPY . .

# Default = API server (celery-worker overrides CMD via docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
