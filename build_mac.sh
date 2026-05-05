#!/bin/bash
set -e

echo "🔧 Build TTS Studio cho Mac..."

# Activate venv
source "$(dirname "$0")/venv/bin/activate"

# Cài PyInstaller nếu chưa có
pip install -q pyinstaller

# Đọc version
VERSION=$(python3 -c "from version import VERSION; print(VERSION)")
echo "📦 Version: $VERSION"

# Build app
echo "⚙️  PyInstaller đang build..."
pyinstaller TTS.spec --clean --noconfirm

# Kiểm tra build xong chưa
if [ ! -d "dist/TTS Studio.app" ]; then
    echo "❌ Build thất bại — không tìm thấy dist/TTS Studio.app"
    exit 1
fi

# Cài create-dmg nếu chưa có
if ! command -v create-dmg &> /dev/null; then
    echo "📥 Cài create-dmg..."
    brew install create-dmg
fi

# Tạo DMG
DMG_NAME="TTS-Studio-${VERSION}-mac.dmg"
echo "💿 Tạo $DMG_NAME..."

# Xóa file cũ nếu có
[ -f "$DMG_NAME" ] && rm "$DMG_NAME"

create-dmg \
    --volname "TTS Studio" \
    --window-pos 200 120 \
    --window-size 550 380 \
    --icon-size 100 \
    --icon "TTS Studio.app" 150 180 \
    --hide-extension "TTS Studio.app" \
    --app-drop-link 400 180 \
    "$DMG_NAME" \
    "dist/TTS Studio.app"

echo ""
echo "✅ Xong! File: $DMG_NAME"
open .
