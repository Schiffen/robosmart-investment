#!/usr/bin/env bash
# Build docs/summary_document.pdf from summary_document.md.
#
# Pipeline: pandoc (markdown -> standalone HTML with images inlined as base64)
#           -> headless Chrome (HTML -> PDF, honouring print.css @page rules).
#
# We use Chrome rather than a LaTeX engine because none is installed, and because
# CSS gives direct control over the page geometry the 5-page limit depends on.
#
# Requires: pandoc, Google Chrome. Run from anywhere.
set -euo pipefail

DOCS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HTML="$DOCS/.summary_build.html"
PDF="$DOCS/summary_document.pdf"

[ -x "$CHROME" ] || { echo "Google Chrome not found at $CHROME" >&2; exit 1; }
command -v pandoc >/dev/null || { echo "pandoc not installed (brew install pandoc)" >&2; exit 1; }

pandoc "$DOCS/summary_document.md" \
  --standalone \
  --embed-resources \
  --resource-path="$DOCS" \
  --css="$DOCS/print.css" \
  --metadata title="RoboSmart Investment — Project Summary" \
  -o "$HTML"

"$CHROME" --headless --disable-gpu --no-pdf-header-footer \
  --virtual-time-budget=10000 \
  --print-to-pdf="$PDF" "file://$HTML" 2>/dev/null

rm -f "$HTML"

python3 - "$PDF" <<'PY'
import re, sys
d = open(sys.argv[1], 'rb').read()
n = max([int(m.group(1)) for m in
         re.finditer(rb'/Type\s*/Pages.*?/Count\s+(\d+)', d, re.S)] or [0])
print(f"built {sys.argv[1]}  —  {n} pages, {len(d)/1e6:.2f} MB", end="  ")
print("OK (within 5-page limit)" if n <= 5 else f"** OVER the 5-page limit by {n-5} **")
PY
