# Quickstart

## Install (from source - not on PyPI)
```bash
git clone https://github.com/sumitrao9/hound.git
cd hound
pip install -e ".[dev]"
playwright install chromium
```

Or:
```bash
pip install git+https://github.com/sumitrao9/hound
playwright install chromium
```

## Configure MCP client

### Claude Code
Add to your Claude Code MCP config. Location varies by setup; refer to Claude Code docs. Use the config from [../templates/mcp-config.json](../templates/mcp-config.json).

### Cursor
Add to Cursor's MCP settings. Refer to Cursor docs for config location. Use the same config.

### Claude Desktop
Add to `claude_desktop_config.json`. Location: macOS `~/Library/Application Support/Claude/claude_desktop_config.json`, Windows `%APPDATA%\Claude\claude_desktop_config.json`. Use the same config.

## Run
```bash
hound-mcp
```

## Verify install
Run `scripts/check-install.sh` from the skill package or follow the steps in [troubleshooting.md](troubleshooting.md).
