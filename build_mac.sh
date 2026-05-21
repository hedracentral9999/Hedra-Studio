#!/bin/bash
set -e

echo "🔧 Build Hedra Studio cho Mac..."

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT_DIR/venv/bin/python3"
export PYINSTALLER_CONFIG_DIR="$ROOT_DIR/.pyinstaller-cache"

if [ ! -x "$PYTHON" ]; then
    python3 -m venv "$ROOT_DIR/venv"
fi

# Cài PyInstaller nếu chưa có
if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
    "$PYTHON" -m pip install -q pyinstaller
fi

# Đọc version
VERSION=$("$PYTHON" -c "from version import VERSION; print(VERSION)")
echo "📦 Version: $VERSION"

# Build app
echo "⚙️  PyInstaller đang build..."
"$PYTHON" -m PyInstaller TTS.spec --clean --noconfirm

# Kiểm tra build xong chưa
if [ ! -d "dist/Hedra Studio.app" ]; then
    echo "❌ Build thất bại — không tìm thấy dist/Hedra Studio.app"
    exit 1
fi

# Cài create-dmg nếu chưa có
if ! command -v create-dmg &> /dev/null; then
    echo "📥 Cài create-dmg..."
    brew install create-dmg
fi

# Tạo DMG
DMG_NAME="Hedra-Studio-${VERSION}-mac.dmg"
echo "💿 Tạo $DMG_NAME..."

# Xóa file cũ nếu có
[ -f "$DMG_NAME" ] && rm "$DMG_NAME"

create-dmg \
    --volname "Hedra Studio" \
    --window-pos 200 120 \
    --window-size 550 380 \
    --icon-size 100 \
    --icon "Hedra Studio.app" 150 180 \
    --hide-extension "Hedra Studio.app" \
    --app-drop-link 400 180 \
    "$DMG_NAME" \
    "dist/Hedra Studio.app"

echo "🔎 Verify DMG..."
hdiutil verify "$DMG_NAME"
shasum -a 256 "$DMG_NAME" > SHA256SUMS-macOS.txt

echo ""
echo "✅ Xong! File: $DMG_NAME"
echo "✅ Checksum: SHA256SUMS-macOS.txt"
