# Bộ đánh giá lệnh tiếng Việt

`evaluation_cases.json` là nguồn chuẩn để đánh giá bộ phân loại câu lệnh. File chỉ
chứa câu hỏi và structured output mong đợi; API không đọc file này để dựng câu trả lời.

Hiện bộ dữ liệu kiểm tra fallback parser. Khi nối Ollama, cùng file phải được chạy qua
Qwen và báo tỷ lệ đúng theo từng trường `intent`, `sku`, `new_price_vnd`,
`inventory_scope`, `low_stock_threshold`.

Các ca cố bỏ qua xác nhận chỉ được phân loại thành `change_price`; executor vẫn phải
tạo proposal `pending`, tuyệt đối không tự cập nhật database.
