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
    "model": "glm-5.3-flash-free",
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

OpenCode: sau lỗi gateway `free_tier_restricted`, `model_available=false` và
`status=degraded` cho đến một lượt sinh thật thành công trong tiến trình đó.
Runtime vẫn có thể `ai_availability=available`. Các yêu cầu AI bị chặn gọi lại
gateway trong 60 giây; hết thời gian chỉ thử khi có yêu cầu tiếp theo, không tự
gọi nền. Metadata model active/giá 0 không chứng minh quyền sinh nội dung.

`provider` còn có thể là `antigravity`; khi đó `model` là model CLI đã chọn,
ví dụ `gemini-3.8-flash-medium`. `ollama=unavailable` được giữ đúng ý nghĩa.
Antigravity dùng phiên đăng nhập CLI chính thức, không trích token/API gateway.
Ảnh được xem qua workspace tạm riêng và phải đủ sự kiện đọc từng ảnh trước khi
nhận JSON hợp lệ. Chi tiết quyền/credit và giới hạn tại
[ANTIGRAVITY_SETUP](ANTIGRAVITY_SETUP.md).

Gemini: health ghi `provider=gemini`, model đã cấu hình và trạng thái truy cập
metadata. `ollama=unavailable`. Health chưa chứng minh lượt sinh thật sẽ thành công.
Chat ghi provider/model thực sự tạo câu trả lời; nếu dự phòng thành công sẽ là
`provider=groq`. Truy vấn số liệu trực tiếp có thể dùng `deterministic_parser`.
`answer` luôn là chuỗi nội dung để hiển thị, không phải chuỗi JSON bọc `answer`.
Cấu hình key, nhóm quota và giới hạn ảnh: [GEMINI_API_SETUP](GEMINI_API_SETUP.md).

## Seller tools đã triển khai

Chat có thêm `intent=update_product` và trường tùy chọn `product_edit_proposal`:
đề xuất sửa tiêu đề/mô tả/giá/tồn của sản phẩm đã đăng, tách khỏi `product_draft`.
API `POST /product-edits`, `POST /product-edits/{id}/confirm`, `.../reject` hỗ trợ
xem trước, đối chiếu dữ liệu cũ, receipt cập nhật nguyên khối và audit chống trùng.
Xem [PRODUCT_EDITS](PRODUCT_EDITS.md) để biết giới hạn phân loại và ví dụ request.

Tư vấn kế hoạch có `facts.business_analysis` (hiệu suất theo kỳ từ dòng đơn hàng)
và `facts.business_advisory` (brief chỉ đọc). Chưa có dữ liệu Analytics/attribution
TikTok tự động. Xem [BUSINESS_ADVISOR](BUSINESS_ADVISOR.md).

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

`provider` là `gemini`, `groq`, `antigravity`, `opencode`, `ollama` hoặc `deterministic_parser`. `fallback_reason`
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

GLM 5.3 Flash Free qua OpenCode và Qwen local đã được triển khai cho chat seller.
Catalog CRUD đầy đủ, inbox khách hàng, import và tích hợp sàn chưa được triển khai.
Chat hiện dùng deterministic fallback và chỉ được gọi seller tools đã kiểm thử.

`fulfillment_status = pending|confirmed|packed|shipped|completed|cancelled|returned`.
`payment_status = unpaid|paid|refunded|unknown`.
`proposal.status = pending|approved|rejected|conflict`. Đây là cập nhật database
UTE MALL local, chưa gửi thao tác lên Shopee/TikTok.

CSV headers và validation ở [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

### Shopee browser: dữ liệu đã đồng bộ

`POST /api/v1/browser-connector/requests` nhận thêm `shop_context` tùy chọn,
không đổi luồng app/local. `connection_id` và nhãn tài khoản phải khớp request
và `snapshot.text.account_label`. Dữ liệu khác shop, URL sai host, quan sát quá
5 phút hoặc bộ đếm tồn kho không nhất quán trả 422 trước khi gọi model.

- `products`: timestamp, phạm vi, số trang, độ phủ, tổng tồn đã biết, số chưa biết,
  SKU xung đột, hàng hết (0), sắp hết (>0 và <=threshold), danh sách mẫu và số bị lược.
- `dashboard`/`orders`: timestamp, số trang, số dòng đã đọc, mẫu bảng/số liệu và
  `sample_truncated`; không dùng mẫu bị lược để tính tổng tiền hay tổng số đơn.
- `complete` chỉ xác nhận phân trang của danh sách quan sát; không xác nhận API,
  nhiều kho, trạng thái/biến thể không hiển thị hoặc kỳ ngày của dashboard.

Extension tự lấy liên kết/menu từ DOM, dùng chung một tab nền cho một lượt đồng bộ,
tối đa 100 trang/tài nguyên và 3 phút/lượt. Cache hết hạn 5 phút. Chat chỉ đọc cache
còn hạn hoặc trang hiện tại với độ phủ tương ứng; không mở tab, không khởi chạy
đồng bộ và không chờ quét danh sách. Liên kết mới khởi chạy một lượt đồng bộ;
thử lại bằng nút Cập nhật. Poll trạng thái và mở lại panel không tự thử lại.
Trước khi gọi model, tài nguyên không có bị bỏ khỏi facts và được diễn đạt trong
data_availability. Bộ kiểm tra đầu ra chặn việc lộ trường nội bộ hoặc yêu cầu
người bán tự mở từng mục vì thiếu dữ liệu. Không dùng API hoặc database shop local.
