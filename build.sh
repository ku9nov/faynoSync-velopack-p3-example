#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VERSION="$(.venv/bin/python -c 'import app_version; print(app_version.version)')"
PACK_ID="HelloVelopack"
# channel is baked into the package; it must match the faynoSync channel so the client
# requests releases.{CHANNEL}.json from the right feed.
CHANNEL="${CHANNEL:-nightly}"

export PATH="$HOME/.dotnet/tools:$PATH"

rm -rf build dist "$PACK_ID.spec"

.venv/bin/pyinstaller --noconfirm --windowed --name "$PACK_ID" app.py

vpk pack \
  --packId "$PACK_ID" \
  --packVersion "$VERSION" \
  --packDir "dist/$PACK_ID.app" \
  --mainExe "$PACK_ID" \
  --channel "$CHANNEL" \
  --outputDir releases

echo "Packed $PACK_ID $VERSION (channel=$CHANNEL) -> releases/"
