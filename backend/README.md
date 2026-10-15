# SellerPilot backend

FastAPI này là lớp điều khiển dành cho **chủ shop**. Dữ liệu sản phẩm, biến thể và
đơn hàng được đọc trực tiếp từ `../UTE MALL/instance/ecommerce.db`. Database
`data/sellerpilot.db` lưu proposal, bản nháp đăng sản phẩm, audit, trace từng
lượt chat và bộ nhớ cá nhân hóa theo shop/SKU. File ảnh không nằm trong SQLite.

## Chạy local

```bash
cd backend
./run_api.sh
```

Mở Swagger tại <http://127.0.0.1:8000/docs>. Backend hỗ trợ hai provider:

- `AI_PROVIDER=opencode`: khởi động một OpenCode server riêng trên localhost và
  chỉ cho phép `muse-spark-1.3-contributor-free`.
- `AI_PROVIDER=ollama`: dùng Qwen local như trước.

Nếu provider không sẵn sàng, chat chuyển sang parser fallback; các seller tools
đọc dữ liệu shop vẫn hoạt động.

Script demo không bật file watcher để chạy ổn định trên macOS. Khi phát triển có thể
chạy `.venv/bin/uvicorn app.main:app --reload` sau khi migration đã hoàn tất.
Với Ollama, `run_api.sh` nạp nóng model trước khi mở API để câu đầu tiên không phải
chờ HDD. Với OpenCode, bước nạp Qwen được bỏ qua. Dùng
`SKIP_OLLAMA_WARMUP=1 ./run_api.sh` khi muốn khởi động Ollama nhanh hơn.

Các API nền hiện có:

- `POST /api/v1/chat`
- `GET /api/v1/chat/requests/{request_id}`
- `POST /api/v1/chat/requests/{request_id}/cancel`
- `GET /api/v1/shop/summary?date=2026-04-18`
- `GET /api/v1/inventory/{sku}`
- `GET /api/v1/inventory/low-stock?threshold=5`
- `POST /api/v1/proposals/price-change`
- `POST /api/v1/proposals/{id}/confirm`
- `POST /api/v1/proposals/{id}/reject`
- `POST /api/v1/product-drafts` (multipart field `image`)
- `POST /api/v1/product-drafts/{id}/publish`
- `POST /api/v1/product-drafts/{id}/cancel`
- `GET /api/v1/assistant/memory`
- `POST /api/v1/assistant/memory/reset`

Ví dụ chat:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Kiểm tra tồn kho SKU 100600680251407"}'
```

Response ghi `mode=ai` khi provider trả contract hợp lệ, hoặc `mode=fallback` kèm
`fallback_reason` khi mất kết nối, timeout, model Free không còn sẵn sàng hoặc JSON
sai. Model không được truy cập database hay công cụ OpenCode. Backend chỉ gửi facts
đã lọc, đối chiếu lại SKU/giá từ câu gốc và mọi yêu cầu đổi giá luôn trả proposal
`pending`; chỉ endpoint confirm mới được cập nhật UTE MALL.

Client mới gửi `request_id` UUID cho mỗi tin để chống xử lý trùng và khôi phục
khi mất mạng. Dừng chat hủy tác vụ trên backend/OpenCode; kết quả đã commit được
giữ nguyên. Chạy một Uvicorn worker; chi tiết transaction, API và giới hạn tại
[độ ổn định chat](../docs/CHAT_RELIABILITY.md).

Ảnh được chọn trong chat được kiểm tra định dạng và giới hạn 8 MB, sau đó lưu tại
`../UTE MALL/static/uploads/sellerpilot/`. Bản nháp hỏi lần lượt tên, giá, tồn kho,
ngành hàng còn thiếu. Muse nhận ảnh và tự soạn tên/mô tả; ảnh khác mặt hàng thì hỏi
người bán chọn sản phẩm. Khi người bán bấm **Đăng sản phẩm** hoặc nhắn chính xác
`đăng sản phẩm`, backend mới tạo sản phẩm cùng biến thể tiêu chuẩn trong shop
`utech-official`. Qwen đang cài là model văn bản, nên chỉ soạn từ thông tin người bán
đã cung cấp. Chi tiết: [luồng soạn nội dung](../docs/PRODUCT_COPY_VERIFICATION.md).

Tư vấn tự nhiên nhận ngữ cảnh kinh doanh, nhớ khách mục tiêu/mục tiêu/giọng trả lời
do người bán xác nhận và lưu chi phí riêng theo SKU. Bộ tính Decimal xử lý hòa vốn,
biên lời, lời trên giá vốn và giảm giá; hỏi ý kiến về giá không tự tạo lệnh đổi giá.
Nhắn “Xóa bộ nhớ cá nhân hóa” để xóa. Xem [tài liệu trợ lý](../docs/PERSONAL_ADVISOR.md).

Qwen nằm trên HDD nên lượt đầu có thể mất gần hai phút. Muse Spark chạy qua Internet
trong OpenCode; timeout mặc định là 90 giây.

Chạy test:

```bash
.venv/bin/pytest
```

Mỗi test dùng database tạm, không sửa dữ liệu UTE MALL thật.

Chạy bộ đánh giá 17 câu với model thật mà không gọi tool hoặc sửa database:

```bash
.venv/bin/python -m app.scripts.evaluate_intent_model
```

Đánh giá riêng Muse Spark qua OpenCode với dữ liệu giả lập:

```bash
.venv/bin/python -m app.scripts.evaluate_muse_opencode
.venv/bin/python -m app.scripts.evaluate_advisor
```

Bài đánh giá này không chạy công cụ bán hàng. Xem
[kết quả và giới hạn của thử nghiệm](../docs/MUSE_SPARK_TRIAL.md).

OpenCode server do backend tạo chỉ lắng nghe ở `127.0.0.1`, có mật khẩu ngẫu nhiên,
chạy trong thư mục tạm và bị tắt cùng backend. Backend kiểm tra model vẫn có giá
input/output/cache bằng 0 trước mỗi lượt, không chuyển sang model trả phí. Bản
Contributor có thể dùng prompt và completion để cải thiện model; không gửi dữ liệu
khách hàng nhạy cảm vào bản demo này.

Nếu OpenCode không cài được hoặc không khởi động, FastAPI vẫn chạy ở trạng thái
`degraded` và dùng parser deterministic. Cài đặt hiện tại cần `opencode` có trong
`PATH`; kiểm tra bằng `opencode --version`.
