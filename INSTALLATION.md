# Hound Installation Guide

## Quick Start

### Prerequisites

- Python 3.10+
- pip
- Playwright system dependencies

### Install from Source

```bash
# Clone repository
git clone https://github.com/sumitrao9/hound.git
cd hound

# Install in development mode
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Install from PyPI (when published)

```bash
pip install hound-browser-mcp
playwright install chromium
```

### Using Docker

```bash
# Build image
docker build -t hound-browser-mcp .

# Run as MCP server (stdio transport)
docker run -i --rm hound-browser-mcp

# Or with docker-compose
docker-compose up
```

### Using with MCP Clients

#### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hound": {
      "command": "hound-mcp",
      "env": {
        "HOUND_DEFAULT_BUDGET": "1200",
        "HOUND_HEADLESS": "1"
      }
    }
  }
}
```

#### Cursor

Add to Cursor settings:

```json
{
  "mcp": {
    "servers": {
      "hound": {
        "command": "hound-mcp",
        "env": {
          "HOUND_DEFAULT_BUDGET": "1200",
          "HOUND_HEADLESS": "1"
        }
      }
    }
  }
}
```

#### Custom Python Script

```python
import asyncio
from mcp.client import Client
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(["hound-mcp"]) as (read, write):
        client = Client(read, write)
        # Use client to call tools
        result = await client.call_tool("browser_open", {"url": "https://example.com"})
        print(result)

asyncio.run(main())
```

---

## System Requirements

### Linux (Ubuntu/Debian)

```bash
sudo apt-get update && sudo apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libxshmfence1 libxcb-dri3-0
```

### macOS

No additional system dependencies required.

### Windows

Visual C++ Redistributable may be required for Playwright.

---

## Verification

```bash
# Run tests
pytest

# Run benchmark
python -m bench.run --url https://example.com

# Run MCP server
hound-mcp
```

---

## Troubleshooting

### Playwright browsers not found

```bash
playwright install chromium
```

### Permission denied on Linux

```bash
# Ensure user has access to /dev/shm
sudo chmod 1777 /dev/shm
```

### Memory issues

Reduce `HOUND_DEFAULT_BUDGET` or use `headless=true`.

---

## Next Steps

- [Configuration Guide](CONFIGURATION.md)
- [MCP Integration Guide](MCP_INTEGRATION.md)
- [Architecture Overview](ARCHITECTURE.md)
