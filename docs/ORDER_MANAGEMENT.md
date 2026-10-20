# Xử lý đơn trên SellerPilot

Trong app, vào **Đơn hàng → chọn đơn → Quản lý đơn**. Chi tiết được tải lại từ server khi mở, không lấy bản sao cũ của thẻ danh sách để ghi.

Có thể sửa người nhận, điện thoại và địa chỉ khi đơn **chờ xác nhận/chờ lấy hàng**; ghi chú vẫn sửa được sau đó. Chạm một thao tác trạng thái, bấm **Xem thay đổi**, kiểm tra giá trị trước/sau rồi xác nhận lưu. Sau lưu, danh sách và số liệu quản lý được tải mới.

| Trạng thái hiện tại | Thao tác được phép |
| --- | --- |
| Chờ xác nhận | Xác nhận đơn; hủy |
| Chờ lấy hàng | Bàn giao vận chuyển; hủy |
| Đang giao | Đã giao thành công |
| Đã giao, đã hủy, đã hoàn hàng | Không chuyển trạng thái trực tiếp |

Phạm vi là database shop local đang liên kết. Không gửi yêu cầu tới hãng vận chuyển, cổng thanh toán hay Shopee chính thức. Trả hàng/hoàn tiền vẫn qua quy trình yêu cầu hoàn trong Kênh Người Bán; không đưa nút chuyển ngược tùy ý lên app. Không sửa giá mua, dòng hàng, số lượng hoặc tổng tiền của đơn đã đặt.

## API và tính nhất quán

- `GET /api/v1/management/orders/{id}` trả chi tiết, `version`, `allowed_statuses`, `editable_fields`.
- `PATCH` cùng đường dẫn nhận `request_id` UUID, `expected_version` và trường thay đổi. Các trường được hỗ trợ: `shipping_name`, `shipping_phone`, `shipping_address`, `note`, `status` (`paid`, `shipped`, `delivered`, `cancelled`).
- Server kiểm tra shop của đơn và của từng sản phẩm/phân loại. Không tìm thấy trong shop trả 404; dữ liệu nhập sai trả 422; bản cũ hoặc chuyển trạng thái không hợp lệ trả 409.
- `BEGIN IMMEDIATE` giữ việc ghi trạng thái, hoàn kho sản phẩm/phân loại, cập nhật số đã bán, nhật ký và biên nhận trong cùng một transaction. Dòng hàng hỏng/khác shop hoặc tồn kho không hợp lệ thì rollback toàn bộ.
- Hai người cùng sửa từ một version: chỉ lượt đầu được ghi; lượt sau phải tải chi tiết mới. Khi mất phản hồi, app thử lại bằng đúng UUID và payload cũ; biên nhận giúp không hoàn kho hoặc ghi nhật ký hai lần.
- Xác nhận đơn không tự ghi nhận thanh toán. Đã giao cập nhật trạng thái thanh toán theo quy tắc store hiện có. Hủy ghi trạng thái hủy và hoàn kho; không thực hiện hoàn tiền ngoài hệ thống.

Bảng biên nhận `sellerpilot_order_receipt` được tạo tự động trong database shop ở lần lưu đầu. Không cần reset database hoặc nhập lại dữ liệu.

## Kiểm tra

```sh
backend/.venv/bin/python -m pytest backend/tests/test_order_management.py -q
```

Có các ca tenant, dữ liệu sai, chuyển trạng thái, thay đổi đồng thời, mất phản hồi/idempotency, hoàn kho một lần và rollback khi dòng hàng lỗi. Giao diện có bài kiểm tra `frontend/tests/order-editor.cjs`; xem [hướng dẫn QA](../frontend/tests/README.md). Cần kiểm tra bàn phím và safe area trên điện thoại thật trước buổi demo.
