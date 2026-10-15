# SellerPilot mobile — 15/10/2026

## Giao diện đã triển khai

- Menu: Quản lý, Sản phẩm, nút AI tròn ở giữa, Đơn hàng, Shop. Các trang giữ trạng thái khi đổi tab.
- Thanh menu nổi trên nội dung, không còn dải nền đặc phía sau. Dùng `expo-glass-effect` kiểu regular mặc định khi iOS hỗ trợ, không phủ màu đặc lên kính native. Thanh menu dạng viên thuốc 72 pt, nền chọn xám và icon/nhãn xanh iOS; icon không chọn màu đen ở giao diện sáng. Nền tảng khác dùng systemMaterial blur 55 và lớp nền nhẹ. Nút AI tròn giữ màu ShipCode. Tôn trọng Reduce Motion và Reduce Transparency.
- Quản lý: thẻ kinh doanh nền trắng, biểu đồ giá trị đơn theo giờ/ngày có trục và chạm chọn mốc; biểu đồ vòng trạng thái đơn trong cùng kỳ hôm nay/7/30 ngày, công việc cần xử lý, sản phẩm nổi bật. Số liệu đọc từ shop được cấu hình, không dùng mảng demo của frontend.
- Sản phẩm: tìm theo tên/SKU, hỗ trợ chữ Việt không dấu, phân trang, giá/tồn kho/trạng thái/ảnh, chuyển câu hỏi sang AI; chỉnh sửa/đăng bán mở đúng trang người bán UTE MALL.
- Đơn hàng: danh sách ảo hóa, bộ lọc đủ chiều cao 44 pt, tìm kiếm có hủy yêu cầu cũ, phân trang, kéo để làm mới và thử lại khi lỗi mạng. Mở thẻ để xem sản phẩm, giá lúc mua, số lượng, phí vận chuyển và thanh toán; nút xử lý mở đúng đơn trong UTE MALL.
- Shop: gian hàng liên kết, giao diện sáng/tối, đánh giá, tin nhắn, mã giảm giá và đồng bộ. Thông tin kỹ thuật nằm trong mục kết nối có thể thu gọn.
- Chat: logo ShipCode, ô nhập nhiều dòng có giới hạn chiều cao, câu hỏi gợi ý, trạng thái chờ/dừng, sao chép hoặc chia sẻ, lịch sử từ nút ba gạch, bản nháp và hội thoại được lưu.
- Bàn phím: menu nằm ngoài KeyboardAvoidingView; tạm ẩn lúc bàn phím mở. Ô nhập thích ứng với bàn phím, không kéo menu lên. Safe-area nằm bên trong KeyboardAvoidingView với offset 0, tránh tính dư khoảng cách phía trên. Chỉ KeyboardAvoidingView điều khiển animation bàn phím. Lời chào thu gọn và gợi ý ẩn khi nhập. Có xử lý visual viewport cho bản web mobile.

## AI và dữ liệu

- Qwen qua Ollama, giữ công cụ nghiệp vụ và dữ liệu shop làm nguồn trả lời.
- Tìm sản phẩm theo tên; hỏi nối tiếp “mẫu đầu tiên”, “mã này”; hoàn thành SKU/giá còn thiếu trong cùng hội thoại.
- Tư vấn và soạn nội dung dùng dữ liệu công cụ và lịch sử có giới hạn. Với yêu cầu tư vấn rõ ràng chỉ gọi model một lượt.
- Giá được lấy nguyên từ yêu cầu, không dùng SKU/giá do model tự đoán. Đề xuất phải bấm xác nhận; lời nhắn “đồng ý” không tự ghi dữ liệu.
- Hội thoại được lưu trong agent DB, lọc theo shop, lấy trạng thái đề xuất mới nhất khi mở lại.
- Thống kê hôm nay không tính đơn đặt trong tương lai, không tính đơn hủy/hoàn vào giá trị hợp lệ. Múi giờ Việt Nam. Giá trị đơn chưa phải tiền đã thu.
- Migration `20261015_04` bổ sung dữ liệu hội thoại; không thay schema catalog của shop.

## Kiểm tra

- Backend: 75 kiểm thử đã qua, gồm nghiệp vụ hiện có cùng các ca mới về hội thoại, truy vấn sản phẩm, phạm vi shop, thống kê, ngữ cảnh và phản hồi model.
- TypeScript, xuất bundle web và bundle iOS.
- Trình duyệt: 375×667, 390×844, 430×932; sáng/tối; các tab; tìm kiếm/bộ lọc; bản nháp; lịch sử; đề xuất/xác nhận; nhập nhiều dòng; đổi tab lúc chờ AI; trạng thái bàn phím qua visual viewport.
- Thử Qwen thật với bản sao database: tìm bàn phím → chọn mẫu đầu tiên → đề xuất giá → xác nhận → đọc lại giá → viết nội dung → xem tổng quan → tư vấn. Các bước thử đổi giá không sửa database shop đang dùng.
- Lượt thử gần nhất: đọc công cụ khoảng 7–8 giây; tư vấn khoảng 17 giây khi model đã nóng. Thời gian thay đổi theo tài nguyên máy và việc nạp model từ HDD.

Chưa kiểm tra bàn phím hay hiệu ứng kính trên iPhone thật. Máy hiện không có `simctl` để chạy iOS Simulator. `build:ios` là kiểm tra xuất JavaScript/Hermes bundle, không phải build/sign IPA. Qwen 4B vẫn có giới hạn suy luận và diễn đạt; không xem kết quả soạn nội dung như thông số sản phẩm đã được kiểm chứng.

Đây vẫn là tích hợp local một shop; API demo chưa có xác thực người bán nhiều tài khoản. Các màn hình UTE MALL cần phiên đăng nhập trình duyệt của chủ shop.

## Chạy

Từ thư mục gốc dự án, mở ba terminal riêng:

```sh
cd "UTE MALL"
HOST=0.0.0.0 ./run_store.sh
```

```sh
cd backend
HOST=0.0.0.0 ./run_api.sh
```

```sh
npm run dev
```

Web: http://localhost:5173. iPhone dùng Expo Go và máy cùng Wi-Fi; mở địa chỉ Expo LAN đang hiện trong terminal. `frontend/.env` cần `EXPO_PUBLIC_API_URL=http://<IP-máy>:8000/api/v1`; có thể đặt thêm `EXPO_PUBLIC_STORE_URL=http://<IP-máy>:5011`. Nếu xem bản web qua IP LAN, thêm origin tương ứng vào `CORS_ORIGINS` của backend.

## Kiểm tra lại giao diện bằng database tạm

Terminal backend:

```sh
cd backend
.venv/bin/python -m app.scripts.mobile_qa_server
```

QA server dùng bản sao SQLite, port 8001 và chế độ AI dự phòng. Chạy các file trong `frontend/tests/` từ thư mục gốc với Playwright có sẵn; xem `frontend/tests/README.md`. Dừng QA server sẽ xóa database tạm.

Tham khảo: [React Native — KeyboardAvoidingView](https://reactnative.dev/docs/keyboardavoidingview), [Apple — Writing](https://developer.apple.com/design/human-interface-guidelines/writing), [Expo GlassEffect](https://docs.expo.dev/versions/latest/sdk/glass-effect/).

## Sửa theo ảnh iPhone

- Giữ kích thước layout các tab khi chuyển, chuyển bằng opacity native; không gọi lại toàn bộ API ở mỗi lần bấm tab. Danh sách đơn chỉ tải khi tab được mở và dữ liệu cần cập nhật.
- Bộ lọc có vùng riêng không bị flex co lại; hàng đơn có ảnh, thời gian Việt Nam, trạng thái có màu, tổng tiền và chi tiết mở rộng.
- Giá trị đơn hợp lệ loại đơn hủy/hoàn; biểu đồ trạng thái gồm cả hủy/hoàn. Công việc cần xử lý là toàn bộ shop, không bị lọc theo kỳ doanh số.
- `management-layout.cjs` kiểm tra chạm biểu đồ, kích thước bộ lọc, liên kết xử lý đơn, kết quả tìm kiếm đến sai thứ tự, lỗi mạng/thử lại, phân trang, ô nhập khi bàn phím mở và biểu đồ tối.
- Đã sửa nguyên nhân tính dư safe-area theo mã native React Native và ảnh người dùng. Các phép đo bằng trình duyệt không chứng minh độ mượt Liquid Glass/bàn phím trên iPhone thật; cần kiểm lại bằng Expo Go.
