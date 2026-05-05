#!/bin/bash
cd "$(dirname "$0")"

# Activate venv
source venv/bin/activate

# Install web dependencies nếu chưa có
pip install -q -r web/requirements.txt

# Tạo .env nếu chưa có
if [ ! -f web/.env ]; then
  cp web/.env.example web/.env
  echo ""
  echo "⚠️  Chưa có file web/.env"
  echo "Mở file web/.env và điền Supabase keys vào trước khi dùng."
  echo ""
  open -e web/.env
  read -p "Nhấn Enter sau khi đã điền keys..."
fi

echo ""
echo "🚀 Đang khởi động TTS Web App..."
echo "   URL: http://localhost:8000"
echo "   Ctrl+C để tắt"
echo ""

# Mở browser
sleep 1.5 && open "http://localhost:8000" &

# Chạy server
cd web && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
