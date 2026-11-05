#!/usr/bin/env bash
# KoliBri-Assets für den Eigenbetrieb bereitstellen (kein CDN im Betrieb).
# Nach `npm ci --prefix assets` ausführen.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source_dir="$root/assets/node_modules/@public-ui"
target="$root/assets/kolibri"

test -d "$source_dir/components/dist" || {
  echo "Fehlt: $source_dir/components/dist - zuerst 'npm ci --prefix assets' ausführen." >&2
  exit 1
}

rm -rf "$target"
mkdir -p "$target"
cp -r "$source_dir/components/dist" "$target/components"
cp "$source_dir/theme-default/dist/index.mjs" "$target/theme-default.mjs"
if [ -f "$source_dir/theme-bwst/dist/index.mjs" ]; then
  cp "$source_dir/theme-bwst/dist/index.mjs" "$target/theme-bwst.mjs"
fi

echo "KoliBri bereitgestellt unter $target ($(du -sh "$target" | cut -f1))"
