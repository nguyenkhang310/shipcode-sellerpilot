# Catalog demo

`demo-catalog.json.gz` là snapshot catalog đã chọn từ ABO, Livostyle và nguồn metadata thời trang. Đây là JSON nén, không phải SQLite hoặc bản sao tài khoản của thành viên.

Snapshot chỉ có category, shop, product và product_variant. Không chứa user, mật khẩu, đơn hàng, thông tin khách, chat, token hay ảnh upload. `bootstrap_demo.py` nạp vào database mới và sinh giao dịch mô phỏng.

Snapshot Livostyle upstream đầy đủ và các importer dùng một lần đã được thay bằng bootstrap để nhóm không phải tải archive lớn hoặc phụ thuộc đường dẫn HDD của máy phát triển. License Livostyle được giữ tại `LIVOSTYLE_LICENSE.txt`; xem [attribution](../../THIRD_PARTY_NOTICES.md) cho các nguồn còn lại.
