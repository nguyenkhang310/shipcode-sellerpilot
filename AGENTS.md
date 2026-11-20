# SellerPilot

SellerPilot là trợ lý vận hành cho người bán Việt Nam. App quản lý sản phẩm,
đơn hàng và số liệu của shop nội bộ, tư vấn qua chat và trò chuyện Live. Chrome
extension đọc dữ liệu từ Kênh Người Bán đã liên kết và hỗ trợ điền bản nháp.

## Cấu trúc

- `frontend/` là Expo SDK 58, React Native và bản web. Màn shop nằm ở
  `frontend/src/features/dashboard/`, chat và Live ở `features/assistant/`.
- `backend/app/` là FastAPI. Endpoint điều phối luồng, service xử lý nghiệp vụ,
  integration đọc/ghi cơ sở dữ liệu của shop. Alembic quản lý schema backend.
- `UTE MALL/` là Flask và SQLite của shop nội bộ. Giữ liên kết sản phẩm với đơn cũ.
- `extensions/shopee-connector/` là Chrome MV3. Kiểm tra đúng tab và shop trước
  khi dùng dữ liệu. Tôn trọng phạm vi đọc và điền form hiện có.

## Phát triển

- Dùng Node 22 từ 22.13 trở lên và chạy `npm ci`, `npm run doctor`, `npm run demo`.
- Chạy `npm run typecheck`, `npm run test:api`, `npm run test:auth` và
  `npm run test:extension`. Với backend, chạy
  `PYTHONPATH=backend backend/.venv/bin/pytest backend/tests`.
- Dùng `npm run extension:build` để xuất Chrome side panel. Kiểm thử sửa giao diện
  ở nhiều độ rộng. Với Live, thử quyền mic, tắt/bật mic, ngắt lời và mở lại phiên.
- Cấu hình Gemini và Groq ở backend qua `.env`. Dùng `.env.example` để hướng dẫn
  nhóm. Giữ khóa, token, cơ sở dữ liệu, ảnh riêng và tài liệu tham chiếu ngoài Git.

## Quy tắc nghiệp vụ

- Mỗi yêu cầu dùng shop và cuộc trò chuyện đã xác thực. Dữ liệu extension và
  shop nội bộ có nguồn riêng. Thiếu số liệu thì nói rõ giới hạn.
- Chat và Live dùng cùng quy tắc nghiệp vụ. Sửa, đăng và xóa sản phẩm cần bước
  xem trước và xác nhận. Khi xóa khỏi gian hàng, lưu trạng thái lưu trữ để các
  đơn cũ vẫn truy cập được. Các thao tác thử lại phải giữ mã yêu cầu ban đầu.
- Live dùng Gemini để nghe và nói. Các công cụ soạn nội dung có thể dùng Groq
  dự phòng. Ưu tiên dữ liệu shop hiện tại và dùng lịch sử để xác định tham chiếu.
- Dùng dữ liệu mẫu khi kiểm thử các thao tác ghi. Kiểm tra diff và test liên quan
  trước khi commit, dùng tiếng Việt cho commit khi nhóm yêu cầu.
