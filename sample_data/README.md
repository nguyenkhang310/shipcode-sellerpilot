# CSV mẫu · Phase 1

Bộ mẫu nhỏ để chốt schema theo Phụ lục A của master plan: 2 products, 3 variants,
2 orders, 2 order items, 2 incoming messages và 4 policies. Chưa được import vào DB.
Dữ liệu này độc lập với fixtures UI cũ trong `frontend/src/data/demo.ts`.

Ba SKU minh họa stock thấp, stock bằng 0 và stock bằng threshold. Đơn `DEMO-O002`
bị hủy nên giá trị đơn đủ điều kiện của bộ mẫu là **300000 VND**, không phải 390000.

UTF-8, dấu phẩy, header bắt buộc. Tiền và tồn kho là integer; quantity > 0;
timestamp có timezone. `external_*` ổn định để import idempotent.
Thứ tự nhập dự kiến: catalog → orders/items → messages → policies.

Phase 2 sẽ mở rộng fixture đến tối thiểu 20 products, 30 variants, 50 orders,
12 incoming messages, thêm validate/upsert và seed/reset.
