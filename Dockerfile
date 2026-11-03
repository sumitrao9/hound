# Hound Browser MCP Server - Docker Image
FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libxshmfence1 libxcb-dri3-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY hound/ ./hound/
COPY bench/ ./bench/
COPY tests/ ./tests/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Set environment variables
ENV HOUND_HEADLESS=1
ENV HOUND_DEFAULT_BUDGET=1200
ENV HOUND_MAX_BUDGET=20000

# Expose port for potential HTTP transport (future)
EXPOSE 8000

# Default command
ENTRYPOINT ["hound-mcp"]
