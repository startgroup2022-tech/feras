#!/usr/bin/env bash
# Render a .pptx deck to one PNG per slide.
#
# The deck is not carried on every branch; read it out of git history when the
# working tree has no copy:
#
#   git show 8f7dc23:"Platform Interface Design v3.pptx" > /tmp/deck.pptx
#   scripts/audit/render_pptx.sh /tmp/deck.pptx artifacts/deck/png
#
# Requires libreoffice-impress + poppler-utils. Fails cleanly when absent.
set -u
DECK="${1:-}"
OUT="${2:-artifacts/deck/png}"
DPI="${DPI:-90}"

if [ -z "$DECK" ] || [ ! -f "$DECK" ]; then
  echo "usage: $0 <deck.pptx> [out_dir]   (deck file not found: '$DECK')" >&2
  exit 2
fi
for bin in soffice pdftoppm; do
  command -v "$bin" >/dev/null 2>&1 || {
    echo "missing '$bin' — install with: apt-get install -y libreoffice-impress poppler-utils" >&2
    exit 3
  }
done

mkdir -p "$OUT"
TMP="$(mktemp -d)"
export HOME="${HOME:-/tmp}"
# soffice.bin needs its own program dir on the loader path in slim images.
if [ -d /usr/lib/libreoffice/program ]; then
  export LD_LIBRARY_PATH="/usr/lib/libreoffice/program:${LD_LIBRARY_PATH:-}"
fi
soffice --headless --norestore -env:UserInstallation="file://$TMP/lo" \
  --convert-to pdf --outdir "$TMP" "$DECK" >/dev/null 2>&1 || {
    echo "LibreOffice conversion failed" >&2; exit 4; }
PDF="$TMP/$(basename "${DECK%.*}").pdf"
[ -f "$PDF" ] || PDF="$(ls "$TMP"/*.pdf 2>/dev/null | head -1)"
pdftoppm -png -r "$DPI" "$PDF" "$OUT/slide"
n=$(ls "$OUT"/slide-*.png 2>/dev/null | wc -l)
echo "rendered $n slides -> $OUT (${DPI} dpi)"
rm -rf "$TMP"
