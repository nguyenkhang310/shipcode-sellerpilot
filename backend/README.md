# SellerPilot backend

FastAPI này là lớp điều khiển dành cho **chủ shop**. Dữ liệu sản phẩm, biến thể và
đơn hàng được đọc trực tiếp từ `../UTE MALL/instance/ecommerce.db`. Database
`data/sellerpilot.db` lưu proposal, bản nháp đăng sản phẩm, audit, trace từng
lượt chat và bộ nhớ cá nhân hóa theo shop/SKU. File ảnh không nằm trong SQLite.

Các route dữ liệu local yêu cầu phiên đăng nhập của thành viên shop. Dùng
`POST /api/v1/auth/login` với tài khoản Kênh Người Bán local, gửi token trả về
trong header `Authorization: Bearer ...`. `/auth/me` kiểm tra phiên, `/auth/logout`
thu hồi phiên. Swagger có **Authorize → SellerSession**. Không dùng tài khoản
Shopee thật hoặc token connector để truy cập API local. [Đăng nhập, quên mật
khẩu và Face ID](../docs/AUTHENTICATION.md).

Luồng `/api/v1/browser-connector/*` là ngoại lệ tách riêng cho Chrome Extension:
chỉ nhận snapshot trang Shopee và thực hiện inference; không dùng repository
shop local, không ghi sản phẩm/đơn thật. Cần `BROWSER_CONNECTOR_TOKEN` do
`npm run extension:setup` tạo. Xem [cài extension và phạm vi hiện có](../extensions/shopee-connector/README.md).

## Chạy local

```bash
cd backend
./run_api.sh
```

Mở Swagger tại <http://127.0.0.1:8000/docs>. Backend hỗ trợ bốn provider:

- `AI_PROVIDER=gemini`: Gemini API trực tiếp, mặc định `gemini-3.5-flash-lite`,
  nhận 1–6 ảnh; hỗ trợ ba key theo project và Groq dự phòng tùy chọn.
  Xem [cài đặt Gemini/Groq](../docs/GEMINI_API_SETUP.md).
- `AI_PROVIDER=antigravity`: headless CLI chính thức, dùng Gemini 3.8 Flash qua
  tài khoản đã đăng nhập, nhận 1–6 ảnh bằng `view_file` trong workspace tạm.
  Xem mục Chọn AI provider trong [README gốc](../README.md#chọn-ai-provider).
- `AI_PROVIDER=opencode`: khởi động một OpenCode server riêng trên localhost và
  chỉ cho phép `glm-5.3-flash-free`.
- `AI_PROVIDER=ollama`: dùng Qwen local như trước.

Nếu provider không sẵn sàng, chat chuyển sang parser fallback; các seller tools
đọc dữ liệu shop vẫn hoạt động.

`npm run demo` tự nạp lại Python khi phát triển; `npm run demo -- --no-reload`
giữ phiên cố định khi trình diễn. `run_api.sh` chạy một worker không watcher.
Với Ollama, `run_api.sh` nạp nóng model trước khi mở API để câu đầu tiên không phải
chờ HDD. Với Gemini, OpenCode hoặc Antigravity, bước nạp Qwen được bỏ qua. Dùng
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
  -H "Authorization: Bearer $SELLERPILOT_SESSION" \
  -d '{"message":"Kiểm tra tồn kho SKU 100600680251407"}'
```

Ví dụ trên giả định `SELLERPILOT_SESSION` đã được nhập riêng vào shell. Không
đặt token hoặc mật khẩu vào source, lịch sử lệnh hay báo cáo kiểm thử.

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
`../UTE MALL/static/uploads/sellerpilot/`. Bản nháp đọc toàn bộ tin nhắn, chỉ hỏi tên,
giá, tồn kho hoặc ngành hàng thực sự còn thiếu. Provider hỗ trợ ảnh nhận gallery và tự soạn tên/mô tả; ảnh khác mặt hàng thì hỏi
người bán chọn sản phẩm. Khi người bán bấm **Đăng sản phẩm** hoặc nhắn chính xác
`đăng sản phẩm`, backend mới tạo sản phẩm cùng biến thể tiêu chuẩn trong shop
`utech-official`. Qwen đang cài là model văn bản, nên chỉ soạn từ thông tin người bán
đã cung cấp. Chi tiết: [ngữ cảnh ảnh và bản nháp](../docs/CHAT_RELIABILITY.md).

Tư vấn tự nhiên nhận ngữ cảnh kinh doanh, nhớ khách mục tiêu/mục tiêu/giọng trả lời
do người bán xác nhận và lưu chi phí riêng theo SKU. Bộ tính Decimal xử lý hòa vốn,
biên lời, lời trên giá vốn và giảm giá; hỏi ý kiến về giá không tự tạo lệnh đổi giá.
Nhắn “Xóa bộ nhớ cá nhân hóa” để xóa. Xem [hội thoại và bộ nhớ](../docs/CHAT_RELIABILITY.md).

Qwen nằm trên HDD nên lượt đầu có thể mất gần hai phút. GLM 5.3 Flash chạy qua Internet
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

Kiểm tra provider Gemini, Antigravity hoặc OpenCode đã cấu hình, bằng dữ liệu và ảnh tự vẽ:

```bash
.venv/bin/python -m app.scripts.check_ai
.venv/bin/python -m app.scripts.evaluate_advisor
```

Các bài thử không đọc database shop thật. Bộ phân loại dùng dữ liệu trong
`tests/fixtures/intent_cases.json`; không phải catalog hoặc CSV để import vào shop.

OpenCode server do backend tạo chỉ lắng nghe ở `127.0.0.1`, có mật khẩu ngẫu nhiên,
chạy trong thư mục tạm và bị tắt cùng backend. Backend kiểm tra model vẫn có giá
input/output/cache bằng 0 trước mỗi lượt, không chuyển sang model trả phí.
GLM Free có thể bị giới hạn hoặc kết thúc ưu đãi theo OpenCode; không có cam kết miễn phí vĩnh viễn.

Nếu OpenCode không cài được hoặc không khởi động, FastAPI vẫn chạy ở trạng thái
`degraded` và dùng parser deterministic. Cài đặt hiện tại cần `opencode` có trong
`PATH` hoặc đường dẫn `OPENCODE_BINARY`; kiểm tra bằng `opencode --version`.
Backend dùng server API 1.x (đã kiểm chứng 1.18.30); v2 bị phát hiện trước khi khởi động
để tránh gọi nhầm endpoint. Lệnh `npm run ai:check` tại root kiểm tra cả quyền gọi model,
khác với `/health` vốn chỉ kiểm tra server và metadata model.
