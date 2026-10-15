# UTE MALL — các luồng đã kiểm tra

Cập nhật 15/10/2026. Website chạy tại `http://127.0.0.1:5011`.

## Vào đúng shop của chủ cửa hàng

1. Mở trang chủ, bấm **Kênh Người Bán**.
2. Đăng nhập bằng thông tin chủ shop được quản lý trong môi trường local; giao diện không công khai mật khẩu.
3. Tới dashboard UTech, có sidebar quản lý ngay trong cùng website.
4. Bấm **Xem Shop** để mở gian hàng công khai; ở gian hàng bấm **Quản lý Shop** để quay lại.

Tài khoản mới đăng ký được đăng nhập tự động và chuyển tới gian hàng UTech với vai trò người mua. Quyền quản lý chỉ cấp qua `shop_member`; người mua không được cấp quyền của UTech khi tự đăng ký.

## Menu được triển khai

| Mục | URL | Thao tác có dữ liệu lưu |
|---|---|---|
| Trang chủ người bán | `/seller` | 8 ô việc cần làm, thống kê hôm nay/7/30 ngày, biểu đồ xem từng điểm và bảng số liệu, nhật ký |
| Sản phẩm | `/seller/products` | Tìm SKU, lọc ngành hàng/trạng thái, sắp xếp giá/kho/lượt bán, sửa, ẩn/hiện hàng loạt, CSV |
| Đăng sản phẩm | `/seller/products/new` | SKU, ảnh, mô tả, giá và stock |
| Tồn kho | `/seller/inventory` | Cập nhật từng SKU |
| Đơn hàng | `/seller/orders` | Thẻ đơn có ảnh/phân loại, lọc trạng thái và khoảng ngày theo giờ VN, xử lý hàng loạt |
| Vận chuyển | `/seller/shipping` | Phiếu giao hàng có thể in |
| Trả hàng | `/seller/returns` | Đồng ý/từ chối, hoàn kho |
| Voucher | `/seller/marketing` | Tạo, bật/tắt, sao chép mã, phân biệt đang chạy/tạm dừng/hết hạn/hết lượt |
| Doanh thu | `/seller/finance` | Order ledger và CSV |
| Phân tích | `/seller/analytics` | 7/30/90 ngày, top sản phẩm |
| Đánh giá | `/seller/reviews` | Lọc 1–5 sao kết hợp chưa phản hồi, gửi/sửa phản hồi công khai |
| Tin nhắn | `/seller/inbox` | Trả lời chat người mua |
| Hồ sơ shop | `/seller/settings` | Lưu tên/ảnh/địa chỉ/tạm nghỉ |
| Nhật ký | `/seller/activity` | Các thay đổi vận hành |

## Bất biến nghiệp vụ

- Mỗi order thuộc đúng một shop; các item cùng shop với order.
- Nhiều order cùng checkout có chung reference; tổng tiền và chiết khấu được phân bổ đúng.
- Trừ tồn kho bằng cập nhật có điều kiện; không bán âm SKU cuối cùng.
- Chuyển trạng thái chỉ theo lifecycle cho phép.
- Hủy/hoàn hàng không hoàn kho lặp lại.
- Chỉ người mua có đơn delivered được đánh giá.
- Voucher riêng shop chỉ giảm phần hàng thuộc shop đó.
- Product/order/review/conversation luôn kiểm tra shop trước khi người bán truy cập.
- POST có CSRF token; các form nhập dữ liệu được kiểm tra phía server.
- Số rating/count công khai khớp review database; số lượt mua UTech tính từ order item đã giao.

## Phạm vi trình diễn

Đây là hệ thống local có dữ liệu giao dịch mô phỏng. Chưa có thanh toán online, trả tiền thật, đặt vận chuyển thật hoặc gửi thư SMTP. Các mục đó không được trình bày như dịch vụ đang kết nối trên giao diện. Hộp thư khôi phục local nằm trong `UTE MALL/instance/mailbox/` và không được phục vụ công khai.

Nguồn thiết kế tham khảo cấu trúc Shopee Seller Centre: https://banhang.shopee.vn/. Thương hiệu, biểu tượng và nội dung giao diện sử dụng tên UTE MALL.

## Giao diện quản trị được thay lại

- Một bộ CSS riêng cho seller; không còn chồng CSS của trang mua hàng.
- Bỏ giới hạn chiều rộng 1.650 px, nội dung giãn theo màn hình; dashboard có cột thông tin shop riêng.
- Chữ nội dung 15–16 px, tiêu đề trang 24–27 px; nút/ô nhập chính cao ít nhất 44 px.
- Menu có nhóm thu gọn; điện thoại dùng menu trượt với lớp nền, phím Escape và quản lý focus.
- Thanh đầu trang có tìm kiếm SKU, việc cần xử lý từ database và menu tài khoản.
- Form sản phẩm chia nhóm thông tin, xem trước ảnh, hướng dẫn phân loại. Sản phẩm nhiều phân loại hiển thị tổng kho/giá thấp nhất chỉ đọc để tránh nhập giá trị bị ghi đè khi lưu.
- CSS/JS có phiên bản trong URL để trình duyệt lấy bản giao diện mới.

## Kết quả kiểm tra

- 17 integration tests của commerce chạy qua trên bản sao database, gồm cả quyền thao tác hàng loạt, rollback trạng thái đơn không hợp lệ và ranh giới ngày Việt Nam.
- 192 liên kết trong khu người bán được kiểm tra, không có lỗi HTTP.
- 42 lượt kiểm tra màn hình quản trị: 14 mục ở chiều rộng 1.920, 1.440 và 390 px; không tràn ngang, không có ô nhập/nút thấp hơn 44 px (sai số đo dưới 1 px), không có chữ thường dưới 12 px.
- 24 lượt kiểm tra trang công khai: 12 trang ở chiều rộng 1.440 và 390 px; không tràn ngang. Tiêu đề Gợi ý hôm nay có nền đặc và không đè ảnh khi cuộn.
- Kiểm tra tương tác trình duyệt: chọn khoảng thống kê, điểm biểu đồ, bảng số liệu, menu thông báo, thu gọn nhóm, chọn tất cả, tìm SKU, lọc đánh giá, đơn vị voucher và menu điện thoại.
- 1.065 đánh giá mua hàng mô phỏng của UTech được gắn với các đơn đã giao; rating và số lượng đánh giá được đối chiếu lại từ database.
- 14 mục sidebar mở thành công bằng trình duyệt.
- Trình duyệt chạy qua đăng sản phẩm → đăng ký buyer → checkout → seller giao hàng → buyer nhận hàng → đánh giá → shop phản hồi → theo dõi và chat hai chiều.
- Không có lỗi JavaScript hoặc HTTP 5xx trong luồng trình duyệt đã kiểm tra.
- Đã xem ảnh chụp desktop 1.920/1.440 px và điện thoại 390 px.
- Đối chiếu SQL: lượt bán hiển thị UTech bằng tổng số lượng từ đơn delivered; rating count khớp các review đã lưu; giá và kho sản phẩm khớp SKU.
- SQLite integrity check: `ok`.

Ảnh kiểm tra lưu trong `docs/screenshots/`. `UTE MALL/tests/seller_ui.cjs` kiểm tra giao diện chỉ đọc ở cổng 5011. Kịch bản `UTE MALL/tests/browser_workflow.cjs` chạy luồng mua–bán, bao gồm ẩn/hiện sản phẩm hàng loạt, chỉ dùng server với database tạm (mặc định cổng 5012).

Trang quản trị Shopee chính thức yêu cầu đăng nhập; chưa đối chiếu đầy đủ mọi màn hình và không khẳng định tương đương 100% chức năng của Shopee.
