# ShipCode SellerPilot + UTE MALL — Demo v0.2

**Ngày cập nhật:** 15/10/2026\
**Trạng thái:** chạy được end-to-end trên máy local.

## Kịch bản trình diễn

1. Mở `http://127.0.0.1:5011` để giới thiệu UTE MALL như một marketplace đa ngành.
2. Mở `/shop/utech-official` để chỉ ra shop công nghệ mà chủ shop đang vận hành.
3. Mở app SellerPilot hoặc Swagger `http://127.0.0.1:8000/docs`.
4. Hỏi: `Shop hôm nay có bao nhiêu đơn và doanh thu bao nhiêu?`
5. Hỏi tồn kho bằng một SKU thật của UTech, ví dụ `UT-B0853X2F4M`.
6. Nhấn dấu `+` trong chat, chọn ảnh và điền các trường SellerPilot hỏi; xác nhận
   đăng rồi mở lại gian hàng UTech Official để thấy sản phẩm vừa đồng bộ.
7. Yêu cầu đổi giá SKU; kiểm tra thẻ `Chờ xác nhận`, sau đó xác nhận hoặc hủy.
8. Thử SKU của shop khác để chứng minh agent không truy cập chéo tenant.

## Kiến trúc chạy

```text
UTE MALL / SQLite
  ├─ 16 ngành, 24 shop, 5.898 sản phẩm
  └─ UTech Official: 270 SKU + 1.500 order synthetic
                  │ shop_id scope
                  ▼
FastAPI seller tools + kho ảnh local → OpenCode/GLM 5.3 Flash Free (hoặc Ollama/Qwen) → Expo chat
```

Model chỉ phân loại/diễn đạt từ facts được cấp. Backend đọc SQL, tính số liệu và thực
thi proposal. Mọi đổi giá vẫn cần xác nhận và audit; model không được gọi công cụ
OpenCode hoặc tự ghi dữ liệu.

## Lệnh chạy

Terminal 1:

```bash
cd "UTE MALL"
./run_store.sh
```

Terminal 2:

```bash
cd backend
HOST=0.0.0.0 ./run_api.sh
```

Terminal 3:

```bash
npx expo start -c
```

Website: `http://127.0.0.1:5011`\
API docs: `http://127.0.0.1:8000/docs`

## Dữ liệu và giới hạn

Catalog lấy từ ABO, Hugging Face fashion data và Livostyle. Giá VND, tồn kho, lượt bán, buyer và order là dữ liệu mô phỏng có seed cố định; không có dữ liệu Shopee thật hoặc PII thật. Checkout hiện tách một order theo mỗi shop, liên kết qua `checkout_reference`. UTE MALL có Kênh Người Bán riêng tại `/seller`; hoàn thiện website trước khi nối thêm chức năng app SellerPilot.
