# UTE MALL

Website thương mại điện tử nhiều shop, dùng chung dữ liệu với SellerPilot. Gian hàng được quản lý bởi app là **UTech Official** (`utech-official`).

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

## Kiểm thử

Từ root:

```sh
"UTE MALL/.venv/bin/python" -W ignore "UTE MALL/tests/commerce_test.py"
```

Test dùng SQLite tạm. Các script browser nhận `PLAYWRIGHT_MODULE`, `CHROME_EXECUTABLE` và `QA_SELLER_PASSWORD` qua môi trường; chỉ chạy quy trình tạo/sửa đơn trên một database QA riêng.
