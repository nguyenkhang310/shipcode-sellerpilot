# Trợ lý kinh doanh cá nhân hóa

SellerPilot tiếp tục dùng GLM 5.3 Flash miễn phí qua OpenCode. Phần trả lời được mở rộng
với ngữ cảnh shop, bộ nhớ có nguồn và bộ tính giá riêng trong backend.

## Hội thoại

- Hỏi tự nhiên về doanh thu, cách cải thiện bán hàng, nội dung, khách hàng hoặc giá bán;
  không cần nhớ tên lệnh. Câu hỏi nối tiếp dùng lịch sử và dữ liệu liên quan.
- Tư vấn nhận số liệu ngày/kỳ, so sánh cùng thời lượng, đơn chờ, tồn kho, mặt hàng thực tế.
  Số bán trong catalog được ghi rõ là lũy kế, không giả làm số bán của 7 ngày.
- Đang soạn sản phẩm vẫn có thể hỏi số liệu/tư vấn rồi tiếp tục bản nháp.
- Hỏi “có nên hạ giá” chỉ tạo tư vấn; việc đổi giá vẫn qua đề xuất và xác nhận.

## Bộ nhớ

Khách mục tiêu, mục tiêu kinh doanh, cách trả lời, giọng nội dung và giới hạn nguồn lực
được lưu theo shop khi chính người bán nói rõ. Giá vốn/chi phí được lưu riêng theo SKU;
kịch bản chưa gắn SKU được giữ trong cuộc chat đó. Giá đang thử và % giảm không lan sang chat mới.

Mỗi cập nhật có nguyên văn bằng chứng. Backend kiểm tra con số/đơn vị có trong tin nhắn,
không ghi nhớ số do model tự thêm hoặc thông tin giả định thành sở thích thật.

Nhắn “Xóa bộ nhớ cá nhân hóa” để xóa. API kiểm tra/xóa:

- `GET /api/v1/assistant/memory`
- `POST /api/v1/assistant/memory/reset`

Lịch sử chat vẫn được giữ để xem lại; mốc reset khiến phần tư vấn không dùng các lượt chat
cũ để khôi phục dữ kiện đã quên. Bộ nhớ được tách theo shop và có thể sửa qua hội thoại mới.

## Giá và lợi nhuận

Phí theo phần trăm tính trên giá bán. Giá vốn tính mỗi sản phẩm; đóng gói, hỗ trợ ship,
quảng cáo và chi phí khác tính mỗi đơn rồi chia cho số sản phẩm trong đơn.

`lời mỗi sản phẩm = giá bán × (1 − tỷ lệ phí) − giá vốn − chi phí mỗi đơn / số sản phẩm trong đơn`

Backend dùng Decimal để tính hòa vốn, tiền lời, biên lời, mục tiêu lời bằng tiền hoặc
% trên giá bán/% trên giá vốn, và kịch bản giảm giá. Giá đề xuất làm tròn lên 1.000đ.
Chi phí chưa cung cấp được liệt kê, không được coi là phí sàn thật hay lợi nhuận ròng đã xác minh.
“Lời 20%” chưa rõ mẫu số sẽ được hỏi lại. Ngân sách quảng cáo theo tháng không tự đổi thành phí mỗi đơn.

## Kiểm chứng

- Toàn bộ test backend: `.venv/bin/pytest -o addopts='' -q` từ `backend/`.
- Test GLM thật: `.venv/bin/python -m app.scripts.evaluate_advisor`.
- Script GLM chỉ tạo shop giả lập trong thư mục tạm, không đọc/copy database shop thật.
- Báo cáo: [ADVISOR_LIVE_EVALUATION.json](ADVISOR_LIVE_EVALUATION.json).
- Đã xác minh: nhớ khách sinh viên/cách trả lời sang chat mới; vốn 100k + đóng gói 5k +
  phí 10%, bán 150k lời 30k, giảm 10% còn lời 16,5k; gợi ý chiến lược bám dữ liệu và mục tiêu.

Model vẫn có thể nhận định chưa tốt; đây là công cụ hỗ trợ quyết định. Giá đối thủ,
traffic, tỷ lệ chuyển đổi và chi phí chưa khai báo không được hệ thống tự coi là đã có.
