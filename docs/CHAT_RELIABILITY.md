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

## Ảnh bổ sung và ngữ cảnh bản nháp

- Gửi ảnh trong hội thoại đang soạn sẽ thêm vào chính bản nháp đó, giữ giá,
  tồn, tiêu đề và mô tả đã xác nhận. Không phải hủy bản nháp chỉ để thêm ảnh.
- SHA-256 của **nội dung file đã giải mã** ngăn cùng file chiếm nhiều vị trí,
  kể cả gửi bằng request ID mới. Đây không phải nhận diện ảnh giống nhau về
  thị giác: ảnh chụp lại hoặc được nén lại có thể có nội dung byte khác.
  Giới hạn sáu ảnh tính theo file riêng, ảnh trùng vẫn gửi lại được khi đã đủ sáu.
- `facts.image_indices` lưu vị trí ảnh của từng lượt upload, để mở lại lịch sử
  vẫn đặt đúng ảnh dưới lời nhắn của người bán. `new_image_count` chỉ đếm file
  mới; không dùng nó để quyết định ảnh nào người bán vừa nhắc đến.
- Khi AI cần đọc ảnh mới, gallery thực tế được đính kèm vào yêu cầu model.
  `ai_image_count` chỉ ghi số ảnh đã gửi trong một lượt AI thành công; lượt lỗi
  không đánh dấu ảnh là đã hiểu. Các lượt sửa giá/tồn đơn giản vẫn có thể chạy
  bằng bộ phân tích tiếng Việt, không gọi model chỉ để điền số.
- Thông báo upload là sự kiện nội bộ. Nó không thay `last_question`, không
  chiếm chỗ lịch sử hội thoại gửi cho AI và không xóa `pending_fields`. Ví dụ
  sau câu giá “500–600k”, thêm ảnh rồi nói “đây nha” vẫn phải chốt lại giá trước
  khi đăng, không âm thầm lấy giá cũ làm giá đã được người bán đồng ý.
- Khi ảnh chưa rõ món bán, trợ lý hỏi một câu phân biệt và giữ dữ kiện thương
  mại đã xác nhận. Câu “đây nha” không được dùng làm tiêu đề sản phẩm.
- Lỗi `active_product_draft` từ backend cũ là từ chối trước khi nhận upload.
  App bỏ mã yêu cầu bị từ chối, giữ ảnh và lời nhắn, tránh vòng Thử lại vô hạn.

`npm run demo` tự nạp lại Python trong `backend/app`. `--no-reload` giữ tiến
trình cố định khi trình diễn; sau cập nhật code phải khởi động lại. Prompt `.md`
và `.env` vẫn cần khởi động lại. Đừng sửa code trong lúc đang gọi AI vì reload
có thể làm gián đoạn yêu cầu. Kiểm tra `GET /api/v1/health` có
`draft_image_context_v2` trong `data.capabilities` để biết tiến trình đã nạp
luồng mới; chỉ sửa file trên đĩa không cập nhật một backend đang chạy cố định.

## Tiếng Việt, bộ nhớ và tính giá

Câu đọc ngắn như “Hôm nay được bao nhiêu đơn vậy?”, “Có món nào sắp hết không?”
được xử lý trực tiếp. “Tuần này” bắt đầu từ thứ Hai, “tháng này” từ ngày 1,
đến hiện tại theo giờ Việt Nam; không đồng nhất với 7/30 ngày gần nhất. Câu trả
lời ghi rõ khoảng ngày. Đang soạn hàng vẫn có thể hỏi số liệu rồi quay lại bản
nháp. “Khoan đã”, “lưu lại bản nháp” giữ nguyên nội dung; “hủy nháp” mới hủy.

`5 xị` = 500.000đ, `hai củ rưỡi` = 2.500.000đ, `1tr2` = 1.200.000đ. Câu
`bán 5 xị, còn 20 cái` chứa giá và tồn riêng; giá vốn, giá cũ, SKU và số model
không được lấy làm giá bán. `5 rưỡi`, `500–600k` cần chốt rõ, không tự chọn
mệnh giá hay một đầu khoảng. Có thể trả lời `5 xị` hoặc `giữ giá cũ` cho câu
hỏi giá đang chờ. Câu ngắn `xe đó`, `đây nha` dùng ảnh và câu hỏi trước, không
trở thành tiêu đề. Nội dung soạn sẵn của người bán được giữ nguyên.

Khách mục tiêu, mục tiêu kinh doanh và giọng trả lời được ghi nhớ theo shop khi
người bán xác nhận. Giá vốn/chi phí tách theo SKU hoặc bản nháp đang bàn, không
lan sang món khác; không ghi số do AI tự thêm thành dữ kiện đã xác nhận. Nhắn
`Xóa bộ nhớ cá nhân hóa` hoặc dùng `POST /api/v1/assistant/memory/reset` để xóa;
`GET /api/v1/assistant/memory` kiểm tra. Reset không xóa lịch sử nhưng ngăn tư vấn
dùng các lượt cũ để khôi phục dữ kiện đã quên.

Backend tính bằng Decimal: lời mỗi sản phẩm = giá bán × (1 − tỷ lệ phí) − giá
vốn − chi phí mỗi đơn / số sản phẩm trong đơn. Chi phí chưa khai được giữ là
chưa biết, không mặc định phí sàn thật hay lợi nhuận ròng. “Lời 20%” chưa rõ
trên giá vốn hay giá bán phải hỏi lại. Tư vấn giá không tự sửa giá shop; mọi
thay đổi vẫn qua bước duyệt. Xem [kế hoạch kinh doanh](BUSINESS_ADVISOR.md).

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
rộng cần worker queue và khóa phân tán. Xác thực hiện tại dành cho shop local
đang cấu hình; phân quyền nhiều chủ shop/Internet cần triển khai riêng.

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

Script tự chạy migration tới `head`. Thay `.env` backend cần khởi động lại API;
thay biến `EXPO_PUBLIC_*` cần khởi động lại Expo.

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
đang liên kết hoặc gọi GLM. Xem [hướng dẫn frontend](../frontend/tests/README.md).
Kết quả browser lưu ở `docs/evaluations/chat-reliability/`.
Test web không thay thế kiểm tra bàn phím và vòng đời ứng dụng trên iPhone thật.

Đợt sửa ảnh bổ sung 21/10/2026: 755 kiểm thử backend, 16 kiểm thử transport/chat
và 11 kiểm thử xác thực đạt; TypeScript và export web/iOS đạt. Sau khi người dùng
khởi động lại, API xác nhận có `draft_image_context_v2`; 15 tình huống browser
với shop tạm và 16 ca AI/NLP (tám lượt gọi Gemini thật) đạt, không fallback hay
timeout trong lượt đo. Benchmark chỉ dùng dữ liệu tổng hợp, có kiểm tra đường
dẫn database/static/uploads thuộc thư mục tạm trước khi gọi provider. Đây không
phải cam kết model luôn đúng hoặc provider không bao giờ bị giới hạn/quá hạn.
