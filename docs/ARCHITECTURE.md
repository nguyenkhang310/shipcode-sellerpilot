# Kiến trúc SellerPilot

Ứng dụng Expo gọi FastAPI; FastAPI đọc shop qua `integrations/ute_mall.py`, điều phối AI và ghi agent metadata vào SQLite riêng. Website Flask và SellerPilot cùng nhìn vào `UTE MALL/instance/ecommerce.db` để thay đổi được phản ánh trên gian hàng.

## Ranh giới trách nhiệm

| Lớp | Trách nhiệm |
| --- | --- |
| App | Gửi yêu cầu có mã định danh, hiển thị số liệu và xác nhận thay đổi |
| API routes | Kiểm tra schema, trả HTTP status và giới hạn truy cập theo shop cấu hình |
| Services | Điều phối hội thoại, bản nháp, proposal, memory và tính giá |
| AI adapters | Gọi OpenCode/Ollama; kiểm tra contract và dọn session |
| UTE MALL gateway | Truy vấn có tham số, giới hạn tenant và ghi catalog có kiểm tra |
| UTE MALL web | Mua hàng, Kênh Người Bán và quy tắc giao dịch |

Model chỉ nhận facts có cấu trúc. Không cấp model quyền shell, filesystem hoặc SQL. Đổi giá và đăng sản phẩm có bước xác nhận trước khi ghi shop. Backend tính tài chính từ chi phí đã khai; model diễn giải và tư vấn.

## Dữ liệu

- Agent DB: migrations Alembic cho proposal, audit, runs, drafts, memory và request outcomes.
- Shop DB: models/schema của Flask, được bootstrap từ catalog và dữ liệu giao dịch mô phỏng.
- Ảnh public dataset: `UTE MALL/static/catalog/`.
- Ảnh người dùng tải: `UTE MALL/static/uploads/sellerpilot/`; không commit.
- Định danh shop mặc định: `utech-official`; không truy vấn doanh số toàn sàn như doanh số của chủ shop.
- Lưu thời gian UTC; báo cáo theo `Asia/Ho_Chi_Minh`.

Một runner local xử lý hàng đợi chat, ngăn nhiều lượt đang chạy trong cùng hội thoại. Kết quả hoàn tất được lưu để thử lại không gọi AI lần nữa. Hủy rollback phần chưa hoàn tất và dọn session OpenCode. Xem [CHAT_RELIABILITY.md](CHAT_RELIABILITY.md).

## Giới hạn triển khai

Chạy một Uvicorn worker. Chưa có hệ thống xác thực app cho nhiều chủ shop hoặc worker queue phân tán. Không có transaction atomic xuyên database shop, agent DB và filesystem. API không nên được mở trực tiếp ra Internet chỉ với cấu hình demo.

Tài liệu kế hoạch và các acceptance report cũ trong `docs/` ghi lại quá trình phát triển; README root và các contract đang thực thi trong code là nguồn vận hành hiện tại.
