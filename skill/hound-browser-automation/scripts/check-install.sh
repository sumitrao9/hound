#!/bin/bash
set -e

echo "Checking Python version..."
python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}.{v.micro}'); sys.exit(0 if v.major==3 and v.minor>=10 else 1)" || { echo "Python >= 3.10 required"; exit 1; }

echo "Checking for hound-mcp command or module..."
if command -v hound-mcp >/dev/null 2>&1; then
    echo "hound-mcp found in PATH"
elif python3 -c "import hound.mcp.server" >/dev/null 2>&1; then
    echo "hound module found (use: python -m hound.mcp.server or hound-mcp if on PATH)"
else
    echo "hound not installed"
    echo "Install: pip install git+https://github.com/sumitrao9/hound"
    exit 1
fi

echo "Checking Playwright Chromium..."
python3 -c "
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        browser.close()
    print('Chromium OK')
except Exception as e:
    print(f'Chromium issue: {e}')
    print('Run: playwright install chromium')
    raise
" || exit 1

echo "All checks passed"
