FROM python:3.12-slim

# System deps for Tesseract (captcha fallback) + playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY captcha-solver/ captcha-solver/
COPY email_oracle/ email_oracle/

# Install dependencies (non-editable for Docker)
RUN uv venv /app/.venv && \
    . /app/.venv/bin/activate && \
    uv pip install "./captcha-solver" && \
    uv pip install "." && \
    playwright install chromium --with-deps

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Data volume for encrypted credentials
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Default: serve (auto-genesis if no creds)
CMD ["email-oracle", "serve"]
