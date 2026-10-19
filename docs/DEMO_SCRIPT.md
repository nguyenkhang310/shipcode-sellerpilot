# Kiểm tra seller tools hiện tại

1. Chạy `cd backend && ./run_api.sh`.
2. Mở `/docs`; gọi `/api/v1/health`. Với cấu hình hiện tại cần thấy
   `provider=opencode`, `model=glm-5.3-flash-free`,
   `model_available=true`, `shop_database=ok` và `integration_mode=local_store`.
3. Gọi `/api/v1/shop/summary?date=2026-04-18`: dữ liệu hiện tại trả 3 đơn,
   1.050.000đ và 3 đơn pending.
4. Gọi `/api/v1/inventory/UT-B06W568Y6C-1c15df9` để xem đúng tên, giá và tồn kho
   sản phẩm của UTech Official.
5. Gọi `/api/v1/inventory/low-stock?threshold=5` để xem danh sách cần xử lý.
6. Gọi `/api/v1/chat` với câu `Kiểm tra tồn kho SKU UT-B06W568Y6C-1c15df9` và kiểm
   tra `mode=ai`, `provider=opencode`, `tool=get_inventory` cùng facts từ database.
7. Gọi `/api/v1/chat` với câu đổi giá; kiểm tra proposal `pending` và giá chưa đổi.
8. Nhấn endpoint confirm để cập nhật database local, hoặc reject để giữ giá. Chỉ thử
   confirm trên SKU mà nhóm chủ động chọn vì đây là dữ liệu UTE MALL đang chạy thật.

Chat đã chạy end-to-end: câu tiếng Việt → intent có cấu trúc → seller tool → facts
→ GLM 5.3 Flash diễn đạt/proposal. Model lỗi hoặc model Free không còn sẵn sàng thì
backend tự quay về parser fallback.
