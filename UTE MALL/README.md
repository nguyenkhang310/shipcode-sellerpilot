# Shopee Demo

Website mô phỏng Shopee nhiều shop, dùng chung dữ liệu với SellerPilot. Gian hàng được quản lý bởi app là **UTech Official** (`utech-official`). Đây không phải website hoặc API Shopee chính thức. Thư mục `UTE MALL/` được giữ để tương thích các lệnh chạy và vị trí database.

Xem [README của repository](../README.md) để cài đầy đủ trên macOS/Linux/Windows, khởi tạo tài khoản và kết nối iPhone. Hai ứng dụng Python có virtualenv riêng.

## Khởi tạo trên máy mới

Từ root repository:

```sh
python3.11 -m venv "UTE MALL/.venv"
"UTE MALL/.venv/bin/python" -m pip install -r "UTE MALL/requirements.txt"
"UTE MALL/.venv/bin/python" "UTE MALL/bootstrap_demo.py"
```

Tự đặt mật khẩu `utech` ở prompt. Bootstrap tạo `.env` với khóa session riêng, nạp catalog và sinh giao dịch mô phỏng. Không nhận dữ liệu đăng nhập hoặc ảnh chat từ máy phát triển. Từ chối ghi đè database đã có sản phẩm.

## Chạy

```sh
cd "UTE MALL"
HOST=0.0.0.0 ./run_store.sh
```

Mở <http://127.0.0.1:5011>. Kênh Người Bán nằm tại `/seller`, gian hàng tại `/shop/utech-official`. Đăng ký trên website tạo tài khoản người mua; không tự nhận quyền bán hàng.

## Dữ liệu và phạm vi

Catalog có provenance theo sản phẩm, nhiều ngành hàng và shop. Giá VND, tồn kho, gán shop và giao dịch demo được mô phỏng. Ảnh nguồn dataset được ghi attribution tại [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Ảnh tải lên lưu trong `static/uploads/` và không được commit.

`bootstrap_demo.py` dùng khi tạo máy mới. `seed_utech_operations.py` dành cho chủ động tái tạo **các đơn có marker mô phỏng**; không chạy trên dữ liệu đang chỉnh sửa nếu chưa sao lưu.

COD, trạng thái vận chuyển, hoàn tiền và mailbox khôi phục hoạt động trong hệ thống local. Chưa gửi tiền, vận đơn hoặc email ra dịch vụ thực tế.

### Đánh giá và bình luận mô phỏng

Khi mở store, schema được nâng cấp thêm `review.is_demo` và bảng `demo_review_seed`.
Mỗi sản phẩm đang bán được bổ sung một lần 16–32 nhận xét, tên hiển thị, số sao,
ngày đánh giá và một phần phản hồi shop. Nội dung chọn theo ngành hàng, không
dùng bình luận bàn phím cho thời trang hay đồ thú cưng. Tổng số và điểm trung bình
trên thẻ sản phẩm, trang chi tiết và Kênh Người Bán lấy từ cùng bảng `review`.

Sản phẩm mới đăng qua SellerPilot hoặc Kênh Người Bán được bổ sung khi mở trang
catalog/chi tiết. Chạy lại không nhân đôi; xóa bình luận không khiến nó tự tạo lại.
Các bình luận cũ và tài khoản thật của demo được giữ nguyên. Tài khoản người đánh
giá mô phỏng không thể đăng nhập. Không sinh đơn mua, thay đổi giá, tồn kho hay
số đã bán để tạo lượt đánh giá.

Mặc định `ENABLE_DEMO_REVIEWS=1`. Đặt `ENABLE_DEMO_REVIEWS=0` trong `.env` của store
rồi khởi động lại để ngừng tự bổ sung; tùy chọn này không xóa dữ liệu đã tạo.
Logo/favicons là asset local; nguồn được ghi trong `THIRD_PARTY_NOTICES.md` ở root.

### Nhận diện và đăng nhập

Trang đăng nhập/đăng ký dùng bố cục riêng: header trắng, logo Shopee vector,
khối cam, form tài khoản và footer năm cột. Các nhãn demo không nằm trên giao
diện; phạm vi mô phỏng được ghi trong tài liệu này và nguồn dữ liệu được giữ
trong database. Mật khẩu mặc định được che, nút mắt chỉ bật theo thao tác người dùng.

Đăng nhập bằng email/tên tài khoản, ghi nhớ phiên, đăng ký và khôi phục mật khẩu
dùng hệ thống local. QR/Facebook/Google hiện có giao diện và thông báo chưa kết
nối khi bấm, chưa cung cấp xác thực bằng Shopee hoặc OAuth. QR ở footer trỏ tới
URL Shopee công khai, không phải mã xác thực tài khoản local.

Sau khi cập nhật source, khởi động lại Flask hoặc lệnh `npm run demo` để nạp
Python và template mới; tải lại cứng trình duyệt nếu đang mở một phiên cũ.

## Kiểm thử

Từ root:

```sh
"UTE MALL/.venv/bin/python" -W ignore "UTE MALL/tests/commerce_test.py"
"UTE MALL/.venv/bin/python" -W ignore "UTE MALL/tests/demo_reviews_test.py"
```

Test dùng SQLite tạm. Các script browser nhận `PLAYWRIGHT_MODULE`, `CHROME_EXECUTABLE` và `QA_SELLER_PASSWORD` qua môi trường; chỉ chạy quy trình tạo/sửa đơn trên một database QA riêng.
