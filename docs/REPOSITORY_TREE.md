# Source layout

Cấu trúc và lệnh chạy hiện tại được duy trì ở [README](../README.md#cấu-trúc-source).

- `frontend/src/App.tsx` là entry app; `app/AppShell.tsx` điều phối năm tab đang dùng.
- `features/dashboard/` chứa màn hình quản lý, sản phẩm, đơn và shop dùng dữ liệu API.
- `features/assistant/` chứa chat và các thao tác có xác nhận.
- `backend/app/integrations/ute_mall.py` là gateway tới SQLite của UTE MALL.
- `UTE MALL/bootstrap_demo.py` nạp catalog và tạo dữ liệu vận hành trên database mới.

Các màn hình mock cũ, modal minh họa, theme cũ và placeholder cho phase tương lai đã được loại khỏi source. Không có bản UI dự phòng chứa nút báo thành công giả.
