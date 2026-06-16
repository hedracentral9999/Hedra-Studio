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

echo "🛡️  Security audit source..."
"$PYTHON" scripts/security_audit_release.py --source "$ROOT_DIR"

# Build app
echo "⚙️  PyInstaller đang build..."
"$PYTHON" -m PyInstaller TTS.spec --clean --noconfirm

# Kiểm tra build xong chưa
if [ ! -d "dist/Hedra Studio.app" ]; then
    echo "❌ Build thất bại — không tìm thấy dist/Hedra Studio.app"
    exit 1
fi

echo "🔎 Verify one-shot runtime assets..."
APP_CONTENTS="dist/Hedra Studio.app/Contents"
for tool in ffmpeg ffprobe; do
    if ! find "$APP_CONTENTS" -type f -name "$tool" -perm -111 | grep -q .; then
        echo "❌ Build thiếu $tool trong app bundle"
        exit 1
    fi
done
for required in \
    "faster_whisper/assets/silero_vad_v6.onnx" \
    "luts/DJI OSMO Osmo Nano D-Log M to Rec.709 V1.cube" \
    "assets/fonts/DTPhudu-Black.otf"; do
    if ! find "$APP_CONTENTS" -path "*/$required" -type f | grep -q .; then
        echo "❌ Build thiếu asset one-shot: $required"
        exit 1
    fi
done

# Stable local app alias for quick testing/opening.
LASTED_APP_NAME="Hedra Studio Lasted.app"
echo "🔁 Cập nhật local lasted app..."
rm -rf "$LASTED_APP_NAME"
ditto "dist/Hedra Studio.app" "$LASTED_APP_NAME"

echo "🔁 Cập nhật /Applications/Hedra Studio.app..."
rm -rf "/Applications/Hedra Studio.app"
ditto "dist/Hedra Studio.app" "/Applications/Hedra Studio.app"

echo "🛡️  Security audit app bundle..."
"$PYTHON" scripts/security_audit_release.py \
    --artifact "dist/Hedra Studio.app" \
    --exact-local

# Cài create-dmg nếu chưa có
if ! command -v create-dmg &> /dev/null; then
    echo "📥 Cài create-dmg..."
    brew install create-dmg
fi

# Tạo DMG
DMG_NAME="Hedra-Studio-${VERSION}-mac.dmg"
LASTED_DMG_NAME="Hedra-Studio-lasted-mac.dmg"
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

# Stable aliases for the newest local build.
rm -f "$LASTED_DMG_NAME"
cp "$DMG_NAME" "$LASTED_DMG_NAME"
shasum -a 256 "$LASTED_DMG_NAME" > SHA256SUMS-macOS-lasted.txt

echo "🛡️  Security audit DMG..."
"$PYTHON" scripts/security_audit_release.py \
    --artifact "$DMG_NAME" \
    --exact-local

echo ""
echo "✅ Xong! File: $DMG_NAME"
echo "✅ Lasted: $LASTED_DMG_NAME"
echo "✅ Checksum: SHA256SUMS-macOS.txt"
