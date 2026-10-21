# Xử lý đơn trên SellerPilot

Trong app, vào **Đơn hàng → chọn đơn → Quản lý đơn**. Chi tiết được tải lại từ server khi mở, không lấy bản sao cũ của thẻ danh sách để ghi.

Mỗi thẻ đơn có **Theo dõi** và **Xử lý đơn** ngay trên danh sách, không cần mở
trang mua hàng. Theo dõi hiển thị trạng thái, tiến trình bốn bước, mã vận đơn và
lịch sử cập nhật. Trong tab Theo dõi, chọn thao tác tiếp theo để xem lại trước
khi xác nhận; tab Thông tin & xử lý cho sửa người nhận, ghi chú và vận đơn.

Đơn vị vận chuyển/mã vận đơn được nhập cùng nhau trước khi bàn giao; sau bàn giao
không sửa tùy ý. Mã cho phép chữ/số và `. _ / -`, 3–80 ký tự. Thông tin này là
ghi nhận của shop local; chưa kết nối hãng vận chuyển, không có vị trí xe, ETA
hoặc quét hành trình tự động. Không tự tạo mã hay thời gian cho các mốc chưa có.

App có lựa chọn nhanh SPX Express, GHN, GHTK, Viettel Post, J&T Express và VNPost;
vẫn nhập được hãng khác. Mã đã lưu có nút sao chép. Kênh Người Bán local cũng sửa
được vận đơn trước bàn giao; form cũ bị từ chối nếu vận đơn đã thay đổi ở phiên
khác. Trang người mua đọc cùng thông tin đã lưu. Danh sách hãng là lựa chọn nhập
liệu, không phải xác nhận đã ký hợp đồng hay kết nối API với các hãng đó.

Trong chat, hỏi `đơn #123 sao rồi?` hoặc `mã vận đơn` để tra cứu. Sau một lượt
chọn đơn, có thể hỏi ngắn `còn đơn đó?` hoặc `còn mã vận đơn?`; server đọc lại
trạng thái hiện tại. Nút dưới câu trả lời mở chi tiết ngay trong app. Yêu cầu hủy
bằng lời dẫn tới form để xem lại/xác nhận, không tự thực thi từ câu chat.

Chi tiết sạch tự kiểm tra cập nhật mỗi 8 giây khi app đang hoạt động. Đang sửa,
review hoặc lưu thì tạm dừng, giữ nội dung đang nhập; version vẫn được kiểm tra
khi ghi. Danh sách kiểm tra mỗi 10 giây ở đầu trang; tạm ngừng khi đang đọc phía
dưới hoặc đã tải hơn một trang để không làm nhảy vị trí. Kéo làm mới luôn có thể
cập nhật lại. Bộ lọc có số đơn theo từng trạng thái trong kết quả tìm kiếm.

Có thể sửa người nhận, điện thoại và địa chỉ khi đơn **chờ xác nhận/chờ lấy hàng**; ghi chú vẫn sửa được sau đó. Chạm một thao tác trạng thái, bấm **Xem thay đổi**, kiểm tra giá trị trước/sau rồi xác nhận lưu. Sau lưu, danh sách và số liệu quản lý được tải mới.

| Trạng thái hiện tại | Thao tác được phép |
| --- | --- |
| Chờ xác nhận | Xác nhận đơn; hủy |
| Chờ lấy hàng | Bàn giao vận chuyển; hủy |
| Đang giao | Đã giao thành công |
| Đã giao, đã hủy, đã hoàn hàng | Không chuyển trạng thái trực tiếp |

Phạm vi là database shop local đang liên kết. Không gửi yêu cầu tới hãng vận chuyển, cổng thanh toán hay Shopee chính thức. Trả hàng/hoàn tiền vẫn qua quy trình yêu cầu hoàn trong Kênh Người Bán; không đưa nút chuyển ngược tùy ý lên app. Không sửa giá mua, dòng hàng, số lượng hoặc tổng tiền của đơn đã đặt.

## API và tính nhất quán

- `GET /api/v1/management/orders/{id}` trả chi tiết, `version`, `allowed_statuses`, `editable_fields`, `shipping_carrier`, `tracking_number`, `events`, `unrecorded_status_change`.
- `PATCH` cùng đường dẫn nhận `request_id` UUID, `expected_version` và trường thay đổi. Các trường được hỗ trợ: `shipping_name`, `shipping_phone`, `shipping_address`, `shipping_carrier`, `tracking_number`, `note`, `status` (`paid`, `shipped`, `delivered`, `cancelled`).
- Server kiểm tra shop của đơn và của từng sản phẩm/phân loại. Không tìm thấy trong shop trả 404; dữ liệu nhập sai trả 422; bản cũ hoặc chuyển trạng thái không hợp lệ trả 409.
- `BEGIN IMMEDIATE` giữ việc ghi trạng thái, hoàn kho sản phẩm/phân loại, cập nhật số đã bán, nhật ký và biên nhận trong cùng một transaction. Dòng hàng hỏng/khác shop hoặc tồn kho không hợp lệ thì rollback toàn bộ.
- Hai người cùng sửa từ một version: chỉ lượt đầu được ghi; lượt sau phải tải chi tiết mới. Khi mất phản hồi, app thử lại bằng đúng UUID và payload cũ; biên nhận giúp không hoàn kho hoặc ghi nhật ký hai lần.
- Xác nhận đơn không tự ghi nhận thanh toán. Đã giao cập nhật trạng thái thanh toán theo quy tắc store hiện có. Hủy ghi trạng thái hủy và hoàn kho; không thực hiện hoàn tiền ngoài hệ thống.

Bảng biên nhận `sellerpilot_order_receipt` được tạo tự động trong database shop ở lần lưu đầu. Không cần reset database hoặc nhập lại dữ liệu.

`sellerpilot_order_shipping` lưu thông tin vận đơn theo shop/đơn;
`sellerpilot_order_event` lưu trạng thái trước/sau và tên trường đã đổi trong cùng
transaction với đơn và receipt. Lưu lặp không tạo mốc thứ hai. Schema dùng chung
ở `backend/app/integrations/order_history.sql`, được cài khi API/web/script mô phỏng
khởi động. SQLite trigger ghi đổi trạng thái từ mọi nguồn trong cùng transaction;
app gắn operation ID lên sự kiện đã có để không ghi trùng. Xóa đơn dọn các bảng
phụ để một ID được tái sử dụng không mang vận đơn/lịch sử của đơn trước.

GET không dựng mốc mới. Đơn cũ thiếu nhật ký hiển thị trạng thái hiện tại cùng
ghi chú chưa có thời điểm cập nhật. Đơn nhập vào ở trạng thái đã xử lý có mốc
**Ghi nhận ban đầu**, không giả giờ xác nhận/bàn giao/giao hàng. Ngày ở header
được ghi rõ là ngày đặt. Không cần reset database.

`npm run demo` kiểm tra API và web trỏ chung database trước khi mở dịch vụ. Nếu
dùng đường dẫn riêng, cấu hình `SHOP_DATABASE_PATH` của API và `STORE_DATABASE_PATH`
của web thành cùng đường dẫn tuyệt đối. Kiểm tra riêng bằng
`cd backend && .venv/bin/python -m app.scripts.check_store`.

Hiệu ứng chỉ dùng fade/translate ngắn cho phần theo dõi và thông báo thành công;
không báo thành công trước khi API xác nhận. Hỗ trợ Giảm chuyển động, không animate
chiều cao cả danh sách hoặc di chuyển footer khi bàn phím mở.

## Kiểm tra

```sh
backend/.venv/bin/python -m pytest backend/tests/test_order_management.py -q
```

Có các ca tenant, dữ liệu sai, chuyển trạng thái, thay đổi đồng thời, mất phản hồi/idempotency, hoàn kho một lần và rollback khi dòng hàng lỗi. Giao diện có bài kiểm tra `frontend/tests/order-editor.cjs`; xem [hướng dẫn QA](../frontend/tests/README.md). Cần kiểm tra bàn phím và safe area trên điện thoại thật trước buổi demo.
