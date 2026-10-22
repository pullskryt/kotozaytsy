#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${HOME}/.local/share/kotozaytsy"
BIN_DIR="${HOME}/.local/bin"
HYPR_CONF="${HOME}/.config/hypr/hyprland.conf"
CAELESTIA_USER="${HOME}/.config/caelestia/hypr-user.lua"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v pacman >/dev/null 2>&1; then
  echo "Этот установщик предназначен для Arch Linux." >&2
  exit 1
fi

sudo pacman -S --needed python python-gobject python-cairo gtk4 gtk4-layer-shell gdk-pixbuf2

mkdir -p "$APP_DIR" "$BIN_DIR"
install -m 755 "$SOURCE_DIR/kotozaytsy.py" "$APP_DIR/kotozaytsy.py"
install -m 644 "$SOURCE_DIR/kotobunny.png" "$APP_DIR/kotobunny.png"
install -m 644 "$SOURCE_DIR/meow.wav" "$APP_DIR/meow.wav"
install -m 644 "$SOURCE_DIR/land.wav" "$APP_DIR/land.wav"
install -m 755 "$SOURCE_DIR/run.sh" "$APP_DIR/run.sh"
cat > "$BIN_DIR/kotozaytsy" <<EOF
#!/bin/sh
exec /usr/bin/sh "$APP_DIR/run.sh" "\$@"
EOF
chmod 755 "$BIN_DIR/kotozaytsy"

if [[ -f "$CAELESTIA_USER" ]]; then
  if ! grep -q 'kotozaytsy' "$CAELESTIA_USER"; then
    python - "$CAELESTIA_USER" "$BIN_DIR/kotozaytsy" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
launcher = json.dumps(sys.argv[2])
with path.open("a") as f:
    f.write("\n-- Котозайцы: desktop pet\nhl.on(\"hyprland.start\", function()\n    hl.exec_cmd(" + launcher + ")\nend)\n")
PY
  fi
elif [[ -f "$HYPR_CONF" ]]; then
  if ! grep -q 'kotozaytsy' "$HYPR_CONF"; then
    printf '\n# Котозайцы: desktop pet\nexec-once = %s\n' "$BIN_DIR/kotozaytsy" >> "$HYPR_CONF"
  fi
else
  echo "Не нашёл конфиг Hyprland; добавь запуск $BIN_DIR/kotozaytsy вручную." >&2
fi

echo "Установлено. Перезапусти Hyprland, чтобы включить автозапуск."
