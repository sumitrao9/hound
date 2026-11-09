FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0t64 libcups2t64 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2t64 libxshmfence1 libxcb-dri3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY hound/ ./hound/
COPY bench/ ./bench/

RUN pip install --no-cache-dir ".[server]" && playwright install --with-deps chromium

ENV HOUND_HEADLESS=1
ENV HOUND_DEFAULT_BUDGET=1200
ENV HOUND_MAX_BUDGET=20000
ENV HOUND_HOST=0.0.0.0
ENV HOUND_PORT=8000
EXPOSE 8000
CMD ["hound-mcp-http"]
