# Độ ổn định của chat SellerPilot

Mỗi tin nhắn mới từ app có UUID `request_id` và `conversation_id` được lưu trên
thiết bị **trước khi gửi**. Backend lưu kết quả theo cặp shop + request ID trong
bảng `chat_request`. Mã này cũng áp dụng cho gallery tải lên từ app.

## Gửi và khôi phục

- `POST /api/v1/chat`: nhận thêm `request_id` tùy chọn để tương thích client cũ.
  Client mới luôn gửi mã này; cùng mã và cùng nội dung trả cùng kết quả, hoặc chờ
  cùng tác vụ đang chạy. Đổi nội dung/hội thoại nhưng giữ mã trả HTTP 409.
- `GET /api/v1/chat/requests/{uuid}`: trả `queued`, `running`, `completed`,
  `cancelled` hoặc `failed`. Kết quả hoàn tất nằm trong `response.data`.
- `POST /api/v1/chat/requests/{uuid}/cancel`: hủy tác vụ, đợi rollback và hủy
  session OpenCode tương ứng. Hủy lặp lại giữ nguyên trạng thái kết thúc.
- Mất kết nối HTTP không tự hủy tác vụ. Thử lại kiểm tra kết quả đã lưu trước;
  chưa hoàn tất thì gửi cùng mã để chờ tác vụ đó. Mở lại app cũng khôi phục mã cũ.
- Nếu lệnh Dừng đến trước POST ban đầu, backend lưu dấu hủy để POST đến muộn
  không tạo tác vụ mới. Nếu tác vụ đã commit, Dừng trả kết quả hoàn tất thực tế.
- Tải ảnh dùng `request_id` riêng cho `POST /product-drafts/images-data`.
  Mất phản hồi không tạo lại file hoặc bản nháp. Tác vụ AI soạn nội dung dùng
  một mã tin nhắn khác. Hủy lúc đang tải ảnh giữ lại bản nháp nếu upload đã xong.

App giữ mã đang chờ trên AsyncStorage; không tự gửi một tin mới khi kết quả tin
trước chưa rõ. Nếu không xác nhận được việc hủy do mất mạng, app giữ yêu cầu hủy
để thử lại, không báo rằng máy chủ đã dừng.

## Transaction và giới hạn triển khai

Chat history, proposal mới, chỉnh sửa bản nháp, bộ nhớ và kết quả yêu cầu được
commit chung trong database agent. Các lệnh commit nội bộ trong service được
hoãn đến cuối lượt. Hủy trong khi chờ AI rollback các thay đổi chưa hoàn tất.
Các ghi nhớ cá nhân hóa được xếp tạm trong bộ nhớ đến khi model trả lời xong,
tránh giữ SQLite write lock trong lúc chờ mạng.

Nếu backend khởi động lại giữa lượt, yêu cầu dở được đánh dấu `failed` với mã
`chat_interrupted`. Backend không tự chạy lại hành động có thể đã tác động shop.
Thao tác ghi sang database UTE MALL có cơ chế riêng; không tuyên bố transaction
atomic xuyên hai database hoặc giữa database và filesystem. Khi crash đúng lúc
đăng hàng, kiểm tra bản nháp/gian hàng trước khi gửi lệnh mới; publish có khóa
định danh theo draft để tránh tạo lại cùng sản phẩm.

Bản local chạy **một tiến trình Uvicorn, một worker**, tối đa 16 tác vụ chờ/chạy,
mỗi hội thoại chỉ một tin đang xử lý; hàng đợi có thời hạn tổng cộng 300 giây.
Không dùng `--workers` nhiều hơn 1 hoặc nhiều backend chung agent DB. Muốn mở
rộng cần worker queue và khóa phân tán. Đăng nhập/phân quyền nhiều chủ shop vẫn
là công việc riêng trước khi đưa API ra Internet.

## Kết nối app

`EXPO_PUBLIC_API_URL` được khai báo sẽ được ưu tiên. Nếu bỏ trống, Expo Go tự lấy
IP LAN từ Metro. Tunnel Expo chỉ chuyển tiếp Metro, không chuyển cổng API 8000;
khi dùng tunnel cần khai báo địa chỉ API mà điện thoại truy cập được.
`API_ORIGIN` dùng URL origin; đường dẫn ảnh `/static/` đi qua backend
`/store-static/`. `EXPO_PUBLIC_STORE_URL` có thể cấu hình riêng.

Chạy backend cho iPhone cùng Wi-Fi, từ thư mục backend:

```sh
HOST=0.0.0.0 ./run_api.sh
```

Script tự chạy migration `20261016_09`. Thay `.env` cần khởi động lại Expo.

## Kiểm chứng

```sh
cd backend
.venv/bin/python -m pytest
```

Tại thư mục gốc:

```sh
npm run typecheck
npm run test:api
npm run build:ios
```

Kiểm thử UI dùng shop hoàn toàn giả lập và AI giả lập có độ trễ, không đọc shop
đang liên kết hoặc gọi Muse. Xem [hướng dẫn frontend](../frontend/tests/README.md).
Kết quả browser lưu ở `docs/evaluations/chat-reliability/`.
Test web không thay thế kiểm tra bàn phím và vòng đời ứng dụng trên iPhone thật.
