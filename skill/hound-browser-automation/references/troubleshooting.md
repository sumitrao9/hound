# Troubleshooting

## hound-mcp not found
- Ensure installed: `pip show hound-browser-mcp` or check PATH
- If using venv, activate it
- Try `python -m hound.mcp.server` if entry point missing

## Chromium not installed
```bash
playwright install chromium
```

## Wrong Hound installed
PyPI has `hound-mcp` (different project). Check: `pip show hound-mcp hound-browser-mcp`. Uninstall conflicting package if needed.

## Budget truncated
Increase `HOUND_DEFAULT_BUDGET` or use `browser_find`/`browser_extract` for targeted data.

## Selector fails
Use `browser_heal` with `selector` and `logical_key`. It will verify and remember if successful.
