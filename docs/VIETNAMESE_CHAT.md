# Hiểu tiền Việt và hỏi lại theo hội thoại

Bản cập nhật ngày 18/10/2026 dùng một bộ đọc tiền chung cho phân loại lệnh,
đăng sản phẩm, giá vốn và câu hỏi nối tiếp. GLM diễn giải ngữ cảnh, backend xác minh
đơn vị và tham số trước khi tạo bản nháp hoặc proposal.

## Tiền và đơn vị

| Lời người bán | Giá trị được hiểu |
|---|---:|
| `5 xị`, `năm xị`, `5xi` | 500.000đ |
| `2 củ`, `hai củ` | 2.000.000đ |
| `hai củ rưỡi`, `2 củ 5` | 2.500.000đ |
| `1 triệu rưỡi`, `triệu rưỡi` | 1.500.000đ |
| `nửa củ` | 500.000đ |
| `1tr2`, `1tr200k`, `1 triệu 200 nghìn` | 1.200.000đ |
| `một triệu hai trăm nghìn` | 1.200.000đ |
| `1.200k`, `1.200.000đ` | 1.200.000đ |
| `5 rưỡi`, `5 chục`, `5 lít` | Cần hỏi rõ mệnh giá/ngữ cảnh |
| `500–600k`, `5 xị hoặc 6 xị` | Cần chốt một giá, không tự chọn đầu/cuối khoảng |

Không dùng float để nhân đơn vị tiền. Không làm tròn số đồng lẻ thành giá mới.
Model không được đổi `5 xị` thành `50k`; giá/tồn vẫn có thẻ kiểm tra trước xác nhận.

`bán 5 xị, còn 20 cái` có hai vai trò: giá 500.000đ và tồn kho 20. Số model/SKU,
giá vốn, giá cũ và tồn không được lấy làm giá bán mới. Dữ kiện bị phủ định, như
`không phải 5 xị`, không được dùng làm giá/chi phí đã xác nhận.

## Hỏi lại và nhớ câu trả lời

- Đủ tên, giá, tồn, ngành và nội dung: tạo bản nháp ready, không hỏi lại từng ô.
- Đã có giá nhưng thiếu tồn: hỏi số lượng của đúng món hàng, không hỏi lại giá.
- GLM có thể viết `next_question` và khai báo `next_question_fields`; backend chỉ
  dùng nếu các trường đó đang thiếu, không lồng thêm số tiền do model tự đề xuất.
- Khi giá mơ hồ, trạng thái chuyển collecting và lưu trường đang chờ trong facts
  của lượt chat. Giữ giá trước đó, không lưu giá đoán và không cho đăng lúc này.
- Câu trả lời tiếp `5 xị` giải quyết đúng câu hỏi giá, giữ tên/mô tả và các dữ kiện khác.
- Có thể nhắn `giữ giá cũ` để bỏ yêu cầu sửa giá đang mơ hồ. Hủy bản nháp vẫn dọn ảnh chưa đăng.

## Khi chưa biết nên bán giá nào

Nhắn `Mình chưa biết giá nên bán bao nhiêu, tư vấn giúp mình` để chuyển từ soạn
sản phẩm sang tư vấn. Backend gửi tên/mô tả/giá/tồn của bản nháp đang soạn để AI
không hỏi lại đang bán món nào.

Giá vốn có nhãn rõ, như `giá vốn 3 xị`, được đọc trực tiếp từ lời chủ shop.
Khi chuyển từ đăng hàng sang tư vấn, có thể dùng lại giá vốn đã gửi cho **cùng bản
nháp**. Không lấy chi phí từ lời AI, bản nháp khác hoặc một SKU khác; giá vốn hiện
tại được chủ shop sửa sẽ có ưu tiên. Giá đang thử trong tư vấn không tự sửa giá shop.

Tiền lời/hòa vốn/biên lời vẫn tính bằng Decimal. Chi phí chưa cung cấp được giữ là
chưa biết; không tự coi kết quả là lợi nhuận ròng hoặc áp phí mặc định của sàn thật.

## Nội dung sản phẩm

GLM tự soạn từ ảnh và dữ kiện, nhưng không tự thêm tình trạng mới, nguyên tem,
chính hãng hay thời hạn bảo hành chưa được người bán xác nhận. Backend kiểm tra
những tuyên bố này và yêu cầu sửa trong giới hạn thời gian nếu model thêm vào.
Giá/tồn nên nằm ở các trường riêng để mô tả không bị cũ khi người bán sửa số liệu.
Nội dung người bán gửi sẵn được giữ nguyên theo luồng xác minh bằng chứng.

## Kiểm tra

```sh
npm run ai:check
```

Lệnh trên dùng GLM thật và dữ liệu/ảnh tự vẽ, gồm `5 xị`, `1 củ`, phân biệt giá
vốn/giá bán và nội dung từ ảnh. Không đọc shop thật. Test không cần Internet:

```sh
cd backend
.venv/bin/pytest
```

Các ca regression nằm ở `test_vietnamese_money.py`, `test_listing_semantics.py`,
`test_advisor.py` và `test_conversations.py`. Chạy lại `npm run demo` sau khi sửa
backend/prompt. Cách diễn đạt ngoài các dạng đã kiểm chứng hoặc ý định không rõ
vẫn cần hỏi lại; việc sinh được văn bản không bảo đảm mọi suy luận của model đều đúng.
