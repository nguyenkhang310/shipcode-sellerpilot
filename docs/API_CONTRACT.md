# API V1 · Seller tools nền

Base URL local: `http://127.0.0.1:8000/api/v1`. Swagger: `/docs`.
Success `{data, meta?}`; lỗi HTTP/validation theo FastAPI `{detail}`;
lỗi không dự kiến `{detail: "Internal server error", code: "internal_error"}`.

## Health

`GET /health` trả 200 nếu DB truy cập được, kể cả khi AI provider chưa sẵn sàng:

```json
{
  "data": {
    "status": "ok",
    "database": "ok",
    "shop_database": "ok",
    "provider": "opencode",
    "ai_availability": "available",
    "ollama": "unavailable",
    "model": "muse-spark-1.3-contributor-free",
    "model_available": true,
    "demo_mode": true,
    "integration_mode": "local_store"
  }
}
```

DB lỗi: 503, `database=unavailable`. Hai database, provider và model cùng sẵn sàng:
`status=ok`. `status=ok` chỉ biểu thị dependencies sẵn sàng. Provider lỗi thì API
nghiệp vụ vẫn chạy bằng parser dự phòng và health ở trạng thái `degraded`.
Trường `ollama` được giữ để tương thích client cũ; khi `provider=opencode` nó là
`unavailable`. Client mới dùng `provider` và `ai_availability`.

## Seller tools đã triển khai

`POST /chat` nhận câu lệnh tiếng Việt của chủ shop. Response gồm `run_id`, câu trả
lời, intent, mode, tool đã gọi, facts lấy từ UTE MALL và proposal nếu là thao tác ghi:

```json
{
  "data": {
    "run_id": 3,
    "answer": "Mình tìm thấy SKU ... Proposal #1 đang chờ xác nhận.",
    "intent": "change_price",
    "mode": "fallback",
    "tool": "create_price_proposal",
    "facts": {
      "sku": "100600680251407",
      "current_price_vnd": 1270000,
      "new_price_vnd": 1200000
    },
    "proposal": {"id": 1, "status": "pending"},
    "integration_mode": "local_store"
  }
}
```

Fallback hiểu ngày trong câu hỏi nghiệp vụ qua `hôm nay`, `hôm qua`, `YYYY-MM-DD`,
`DD/MM/YYYY`; SKU chữ-số hoặc
SKU số dài; giá dạng số thường, phân cách nghìn, `k`, `triệu` và `tỷ`. Câu ngoài
phạm vi trả hướng dẫn, không tự tạo facts.

`provider` là `opencode`, `ollama` hoặc `deterministic_parser`. `fallback_reason`
có thể là lỗi kết nối/timeout/JSON, provider từ chối, model Free không còn sẵn sàng,
hoặc model yêu cầu gọi công cụ. Backend không tự chuyển sang model trả phí.

`GET /shop/summary?date=YYYY-MM-DD` trả số đơn không bị hủy, tổng giá trị đơn theo
VND, số đơn chờ và phân bố trạng thái. Ngày được hiểu theo `Asia/Ho_Chi_Minh`; timestamp
trong UTE MALL được xem là UTC.

`GET /inventory/{sku}` tra SKU sản phẩm hoặc SKU biến thể, không phân biệt hoa thường.

`GET /inventory/low-stock?threshold=5&limit=50` trả biến thể/sản phẩm active có tồn
kho nhỏ hơn hoặc bằng ngưỡng.

`POST /proposals/price-change` chỉ tạo proposal, chưa sửa database shop:

```json
{"sku": "100600680251407", "new_price_vnd": 1200000}
```

`POST /proposals/{id}/confirm` đọc lại giá hiện tại rồi mới cập nhật. Nếu giá đã đổi
sau lúc tạo proposal, API trả 409 và không ghi đè. Confirm lại proposal đã approved
trả kết quả cũ với `idempotent=true`; audit chỉ có một bản ghi.

`POST /proposals/{id}/reject` giữ nguyên giá. Reject lại trả `idempotent=true`; thao
tác trái với trạng thái cuối trả 409.

## Chưa triển khai

Muse Spark Free qua OpenCode và Qwen local đã được triển khai cho chat seller.
Catalog CRUD đầy đủ, inbox khách hàng, import và tích hợp sàn chưa được triển khai.
Chat hiện dùng deterministic fallback và chỉ được gọi seller tools đã kiểm thử.

`fulfillment_status = pending|confirmed|packed|shipped|completed|cancelled|returned`.
`payment_status = unpaid|paid|refunded|unknown`.
`proposal.status = pending|approved|rejected|conflict`. Đây là cập nhật database
UTE MALL local, chưa gửi thao tác lên Shopee/TikTok.

CSV headers và validation ở [DATA_DICTIONARY.md](DATA_DICTIONARY.md).
