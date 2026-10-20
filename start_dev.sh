#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "=================================================="
echo "🚀 Đang khởi động hệ thống ShipCode SellerPilot..."
echo "=================================================="

# Dừng tất cả tiến trình con khi nhấn Ctrl+C
cleanup() {
    echo ""
    echo "🛑 Đang dừng toàn bộ các tiến trình..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Khởi động UTE MALL (Flask - 5011)
echo "📦 [1/3] Khởi động UTE MALL (http://127.0.0.1:5011)..."
(cd "$ROOT_DIR/UTE MALL" && HOST=0.0.0.0 ./run_store.sh) &

sleep 2

# 2. Khởi động Backend API (FastAPI - 8000)
echo "⚙️  [2/3] Khởi động Backend API (http://127.0.0.1:8000)..."
(cd "$ROOT_DIR/backend" && HOST=0.0.0.0 ./run_api.sh) &

sleep 2

# 3. Khởi động Frontend Web (Expo Web - 5173)
echo "💻 [3/3] Khởi động Frontend Web (http://localhost:5173)..."
npm run web &

echo ""
echo "=================================================="
echo "✅ Hệ thống đã sẵn sàng:"
echo "   - 🛍️  UTE MALL:      http://localhost:5011"
echo "   - 🧑‍💼 Kênh Người Bán: http://localhost:5011/seller"
echo "   - 📄 Swagger API:   http://localhost:8000/docs"
echo "   - 📱 Frontend Web:  http://localhost:5173"
echo "=================================================="
echo "Nhấn Ctrl+C bất cứ lúc nào để tắt toàn bộ dịch vụ."
echo ""

wait
