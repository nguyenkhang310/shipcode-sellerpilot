# Kiểm chứng soạn nội dung sản phẩm qua Muse

Luồng hiện tại: chọn 1–6 ảnh → bấm Gửi → Muse nhận ảnh và soạn tên/mô tả →
hỏi giá, tồn kho hoặc thông tin còn thiếu → duyệt bản nháp → xác nhận đăng.
Chọn ảnh vào ô soạn không tự gửi. Gửi ảnh không kèm chữ vẫn yêu cầu AI soạn bản nháp.

Các lỗi đã sửa:

- Câu “đăng sản phẩm này lên cho tôi được không” không trở thành tên sản phẩm.
- Chữ “cho” trong câu lệnh không bị phân loại thành ngành thú cưng.
- Ảnh được gửi qua file part dạng data URL cho Muse trong OpenCode; không giao công cụ đọc file.
- Agent soạn sản phẩm có prompt JSON riêng, không dùng prompt chat vốn yêu cầu trả văn bản.
- Tự viết nội dung khi đã biết sản phẩm, lưu yêu cầu soạn qua các lượt hỏi giá/tồn kho.
- Có thể yêu cầu viết lại khi bản nháp đã sẵn sàng.
- Khi AI không phản hồi hoặc trả nội dung sai định dạng, giữ bản nháp và báo lỗi;
  không dùng câu mẫu rồi đánh dấu nội dung đã hoàn tất.
- Chặn đăng bản nháp cũ lấy câu lệnh làm tên; chat tiếp sẽ bỏ nội dung sai và soạn lại.

Đã gọi Muse thật qua OpenCode, model `muse-spark-1.3-contributor-free`:

| Ca thử | Kết quả |
|---|---|
| Tên bàn phím Nova K75 đã xác nhận | Tạo tiêu đề và mô tả JSON bằng model |
| Ảnh bàn phím + câu lệnh đăng sản phẩm | Nhận ra bàn phím, tạo tên/mô tả, chọn ngành Máy Tính & Laptop |
| Bổ sung 990.000đ và tồn kho 20 | Bản nháp ready, giữ nguyên nội dung đã tạo |
| Ảnh bàn phím và hộp PS Vita | Hỏi “Ảnh có bàn phím và hộp PS Vita, bạn muốn bán mặt hàng nào?”, giữ collecting |
| Health backend cổng 8000 | OpenCode available, model_available=true, hai database ok |

Các ca đọc ảnh/soạn nội dung dùng ảnh catalog công khai và agent database tạm.
Không đăng sản phẩm hay chỉnh catalog chính để kiểm thử. Model vẫn có thể mô tả
ảnh chưa chính xác; chủ shop cần kiểm tra nội dung trên bản nháp trước khi xác nhận.

Kiểm tra tự động: `cd backend && .venv/bin/pytest -o addopts='' -q`.
TypeScript và Expo iOS export đã qua. Revision schema: `20261015_07`.
Qwen dùng prompt JSON riêng ở chế độ văn bản, không tuyên bố đã đọc ảnh.
