# Trợ lý kế hoạch kinh doanh

SellerPilot dùng dữ liệu shop để chuẩn bị kế hoạch, kịch bản nội dung và cách đo.
Đây là tư vấn để chủ shop duyệt/thực hiện, không tự đăng TikTok, chạy quảng cáo,
thay giá hay đặt lịch nền.

## Cách thử trên app

Khởi động lại demo để nạp backend/prompt mới:

```sh
npm run demo
```

Trong Chat có nút **Lập kế hoạch cho shop**. Có thể nói tự nhiên:

- “Phân tích số liệu 7 ngày qua và lập kế hoạch 7 ngày tới. Mình tự làm một mình,
  chưa có ngân sách quảng cáo. Chọn sản phẩm ưu tiên và nói việc cần làm từng ngày.”
- “Viết kịch bản TikTok 25 giây cho SKU [mã đang có trong shop]: 2 hook A/B,
  cảnh quay, lời thoại, chữ màn hình, CTA và caption. Không thêm thông số chưa có.”
- “Cụ thể hơn cách đo hiệu quả hai video. Chưa đo được nhấp và đơn từ TikTok thì sao?”
- “Dựa trên 7 ngày qua, đổi thành kế hoạch 30 ngày tới.”

Dùng SKU thật thay chỗ `[mã đang có trong shop]`. Có thể tiếp tục cùng hội thoại
để điều chỉnh nguồn lực/khách mục tiêu; dữ kiện được chủ shop xác nhận mới được
lưu vào bộ nhớ theo cơ chế sẵn có.

Khi đang soạn sản phẩm, yêu cầu kế hoạch/video/caption video đi vào luồng tư vấn;
không sửa mô tả, giá hoặc tồn của bản nháp. Nhắc “sản phẩm này/bản nháp” sẽ dùng
thông tin bản nháp sau khi backend đọc được, và ghi rõ sản phẩm chưa đăng.

## Số liệu được bổ sung

`facts.business_analysis` là snapshot chỉ đọc trong một transaction, theo shop
đang liên kết và lịch Việt Nam:

- Đơn hợp lệ, giá trị đơn, giá trị đơn đã giao, giá trị đơn trung bình.
- Số/tỷ lệ đơn hủy và trả hàng, lấy tổng số đơn trong kỳ làm mẫu số.
- So với kỳ trước có cùng thời lượng đã trôi qua; loại đơn tương lai.
- Số lượng và giá trị dòng hàng theo sản phẩm trong kỳ, dùng **giá lúc mua**.
- Hàng cần xem lại tồn, mẫu còn hàng có thể thử làm nội dung; tồn biến thể không
  cộng trùng tồn sản phẩm cha.
- Dòng hàng thiếu sản phẩm/không thuộc shop được đánh dấu chưa quy được, không
  lộ metadata của shop khác.

Số bán lũy kế catalog không dùng thay số bán trong kỳ. Không có dòng hàng thì
chưa xếp hạng được hiệu suất; danh sách hàng còn kho chỉ là ứng viên thử.
Giá trị dòng hàng chưa phân bổ vận chuyển/giảm giá cấp đơn, không phải lãi ròng.
Ước tính số ngày đủ tồn dùng lượng bán/kỳ lịch có phần ngày hôm nay chưa kết thúc;
đó là phép mô tả, không phải dự báo nhu cầu.

`facts.business_advisory` chọn yêu cầu kế hoạch, kịch bản hoặc đo hiệu quả; ghi rõ
ngày kế hoạch tương lai, sản phẩm đang hỏi/đề xuất thử, căn cứ và giới hạn dữ liệu.
Kỳ “7 ngày qua” và lịch “30 ngày tới” được giữ riêng.

## Câu trả lời có gì khác

Kế hoạch có nhận xét số liệu → việc theo ngày/giai đoạn → đầu ra cần làm → chỉ số
xem lại → giữ/sửa/dừng. Gợi ý nội dung có hook A/B, cảnh theo giây, thoại và chữ
màn hình, CTA về UTE MALL và caption. Không mặc định mặt hàng nào cũng là đồ công nghệ.

Prompt chi tiết chỉ gắn khi có yêu cầu phù hợp; chat thông thường giữ ngân sách
ngắn. Gemini dùng `GEMINI_ADVICE_MAX_OUTPUT_TOKENS=4096` mặc định cho phần này,
tách khỏi `GEMINI_MAX_OUTPUT_TOKENS=2048` của chat thường. Không cần đổi key/model.

Backend yêu cầu viết lại một lần khi phát hiện các lỗi đã được kiểm tra như
bịa đặc tính cụ thể, nhầm số mẫu sắp hết với số chiếc tồn, kịch bản thiếu thoại,
gán đơn theo cùng ngày cho video hoặc khẳng định nguyên nhân marketing khi chưa đo.
Các kiểm tra này có phạm vi xác định, không bảo đảm phát hiện mọi sai sót của model.
Nếu vẫn lỗi/mất AI, trả khung hành động từ số liệu backend và ghi `mode=fallback`.

## Đo TikTok và giới hạn thực tế

Chưa có tích hợp TikTok Analytics, tracking link hay attribution đơn TikTok.
Chủ shop cần lấy số Analytics và thiết lập cách ghi nguồn trước. Mẫu ghi:

| Mã video | Ngày đăng | Cửa sổ đo | Lượt xem | Nhấp đã đo | Đơn có nguồn | Chi ads |
| --- | --- | --- | --- | --- | --- | --- |
| A | Điền khi đăng | Cùng cửa sổ với B | Chủ shop ghi | Chưa đo được | Chưa đo được | Chưa khai báo |
| B | Điền khi đăng | Cùng cửa sổ với A | Chủ shop ghi | Chưa đo được | Chưa đo được | Chưa khai báo |

“Chưa đo được” khác 0. Tổng đơn shop cùng ngày không chứng minh đơn đến từ video.
Phản hồi khách về nguồn là tự khai, chưa phải đo tự động. Không đủ mẫu thì không
tuyên bố phiên bản nào thắng hay video chắc chắn mang lại đơn. Mục tiêu là đề xuất
thử nghiệm, không phải cam kết doanh số. Không tự chọn giá giảm khi thiếu giá vốn/phí.

Cấu trúc mở đầu → demo → CTA và cách thử một biến được tham khảo từ nguồn chính thức:
[TikTok creative guidance](https://ads.tiktok.com/resources/help/article/creative-best-practices),
[video guide](https://ads.tiktok.com/business/en/guides/video-advertising-guide),
[testing guide](https://ads.tiktok.com/business/en/guides/ad-testing-guide).
Các hướng dẫn quảng cáo là điểm xuất phát để thử, không chứng minh hiệu quả organic
cho shop này hoặc quyền đặt link của mọi tài khoản.

## Kiểm thử

Test tự động dùng database tạm, bao gồm ranh giới ngày, cùng thời lượng, đơn hủy/hoàn/
tương lai, giá mua, biến thể, cách ly shop, dữ liệu thiếu, chuyển chủ đề và lỗi provider.

Chạy model thật với ba tình huống và shop tự tạo, không mở database shop đã cấu hình:

```sh
cd backend
.venv/bin/python -m app.scripts.evaluate_business
```

Script xuất câu trả lời từ dữ liệu giả để nhóm đọc đánh giá. Đây là bài đánh giá thủ
công, không phải chứng nhận mọi câu trả lời đều đúng. Lần thử Gemini 3.5 Flash-Lite
ngày 19/10/2026 đã trả kế hoạch 7 ngày, kịch bản 25 giây và cách đo nối tiếp; từng
lượt khoảng 2–10 giây, gồm lượt phải yêu cầu sửa. Độ trễ/quota thay đổi theo dịch vụ.
