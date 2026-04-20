# ── Psychiatry Weekly Review — Google Cloud Run Job ───────────────────────────
# Python 3.12-slim base; installs Playwright (Chromium), notebooklm-py, and gh CLI
# Auth JSON is injected at runtime via NOTEBOOKLM_AUTH_JSON env var from GCP Secret Manager

FROM python:3.12-slim

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── GitHub CLI (gh) — for uploading Release assets ────────────────────────────
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && apt-get install -y gh && \
    rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt playwright && \
    playwright install chromium --with-deps

# ── Application code ───────────────────────────────────────────────────────────
COPY scripts/ scripts/
COPY summaries/ summaries/

# ── Entry point ────────────────────────────────────────────────────────────────
CMD ["python", "scripts/weekly_review.py"]
