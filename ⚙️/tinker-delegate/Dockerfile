FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY tinker_delegate/ tinker_delegate/

RUN uv venv /app/.venv && \
    uv sync --frozen --no-dev --extra agent && \
    rm -rf /root/.cache /tmp/*

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8080

CMD ["tinker-delegate", "serve", "--port", "8080"]
