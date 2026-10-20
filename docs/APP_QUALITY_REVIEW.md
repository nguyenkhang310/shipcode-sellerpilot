# Rà soát app sau khi hợp nhất nhánh Hoàng

## Cập nhật 21/10/2026

- Sửa cảnh báo native SVG `".55" is not a valid number or percentage string`:
  offset của viền kính chuyển sang `{0.55}`; trục gradient và opacity biểu đồ
  dùng giá trị số. Trước đó native đọc offset không hợp lệ thành 0, làm sai
  gradient; không chỉ là log thừa. `npm run test:svg` chạy extractor native thật
  và xác minh không cảnh báo, không dùng LogBox để che lỗi.

- Hiệu quả kinh doanh tách thành `PerformanceOverview`: tổng giá trị có khoảng
  thở riêng, hàng chỉ số chia bằng đường mảnh, biểu đồ và giá trị đã giao/hủy ở
  khung riêng. Bỏ nền navy nguyên khối. Cam logo dùng cho kỳ đang chọn, đường
  biểu đồ, điểm nhấn ưu tiên, lời mời phân tích và tab đang chọn; nền lớn trung tính.
- Thêm khu vực ưu tiên có hành động dẫn đúng danh sách lọc; phân bố đơn dùng
  thanh ngang và số lượng/tỷ lệ. Không bịa tăng trưởng khi thiếu kỳ so sánh.
- Kính dùng recipe sáng/tối riêng: frost 80%, viền trung tính tương phản, backdrop
  blur một lớp. Native dùng GlassView regular với colorScheme rõ; material/mask
  cập nhật theo theme. Lựa chọn theme lưu tuần tự và không bị hydration cũ ghi đè.
- Hệ icon điều hướng/lối tắt dùng chung SVG 24px, nét 1,65, không đổi thành mảng
  tô đậm khi chọn. Bỏ biểu tượng lấp lánh, tia sét và nhịp sóng trang trí. Cùng bộ
  icon được dùng ở extension; các nút thao tác cơ bản vẫn dùng glyph nền tảng.
- Gemini mặc định 60 giây, dùng deadline chung xuyên các bước trong một lượt.
  Quy tắc đọc số liệu Việt không dấu/có dấu bỏ gọi model với câu đơn giản;
  câu tính lời đơn giản chỉ gọi trích dữ kiện, kiểm tra rồi tính bằng Decimal.
- Đo API thật trên shop tạm: năm ca đơn giản 5–30ms không gọi AI, tư vấn 32,9s,
  tính lời 20,5s/một lần gọi, ảnh 16,5s. Cả tám ca qua, không fallback. Provider
  vẫn biến động; đây không phải cam kết hết timeout. Report gitignore tại
  `docs/evaluations/ai-latency/results.json`; chạy lại bằng `npm run ai:benchmark`.
- 600 test backend đã qua. Các mục phía dưới ghi lại lần kiểm tra trước và
  cấu hình 45 giây cũ; cấu hình hiện tại xem `GEMINI_API_SETUP.md`.
- Bản cuối qua typecheck, 12 test transport/message, 21 test extension; browser
  audit năm tab, đổi kỳ chậm/lỗi/phản hồi muộn, readability và 16 lần chuyển
  sáng/tối đều qua. Theme vẫn đúng sau reload, bản nháp chat giữ nguyên. Các test
  browser đo cả bố cục ở 320–520px; ảnh/result nằm trong thư mục evaluations.

Giới hạn: chưa kiểm tra lại trên iPhone thật (bàn phím, safe area, Dynamic Type
và GlassView iOS 26). Browser fixture dùng dữ liệu tạm, không can thiệp tài khoản
Shopee/TikTok hoặc API đang phục vụ người dùng.

Đã lưu các thay đổi trước đó trong `e355cf4`, rồi hợp nhất `origin/hoangbadu`
(commit `46b2c5a`) vào `main` bằng merge `6ca7190`. Không ghi đè `.env` hoặc push lên remote trong lượt này.

## Giao diện

- Căn phần biểu tượng tròn trong ảnh HCMUTE, loại khoảng trắng/chữ bên dưới khỏi khung avatar bằng layout, giữ nguyên file gốc.
- Thanh dưới có đường khoét cong thật theo kích thước màn hình, nút SellerPilot 72px nhô lên 28px; vùng chọn cũng theo mask để không đè lên đường cong. Khoảng đệm nội dung/composer dùng chung một công thức, giữ vùng chạm phần nhô lên. Native dùng mask + material, web dùng CSS clip-path, đặt backdrop blur ngay trên phần tử mask và bỏ filter ở cha để kính không xuyên chữ sắc nét; hỗ trợ Giảm độ trong suốt.
- Tăng chữ nội dung và chữ phụ, độ tương phản; giữ nhãn điều hướng ở 12px, vùng bấm rõ, icon outline khi chưa chọn và navy khi chọn.
- Thẻ sản phẩm/đơn có thứ bậc rõ hơn, trạng thái màu nhẹ, nút thêm sản phẩm nổi bật, hành động phụ gọn hơn. Ảnh không bị co ngang vì tiêu đề dài.
- Thẻ bản nháp có gallery bấm đổi ảnh, ảnh chính contain và mở rộng mô tả; thêm hủy bản nháp đang thu thập. Không hiện tồn `null` hoặc tải URL ảnh rỗng.
- Chặn phản hồi tải lịch sử sau thao tác đăng/điền form ghi đè lên hội thoại mới.
- Các bài kiểm tra bố cục dùng dữ liệu giả; không gọi shop đang sử dụng hoặc gửi ảnh cá nhân lên AI.

## AI và dữ liệu

- Khi sửa lựa chọn sản phẩm bằng câu như “không, xe đó”, cập nhật ngành hàng cùng tiêu đề/mô tả thay vì giữ ngành cũ.
- Đọc số tồn viết bằng chữ, số có phân cách hàng nghìn, “hết hàng”; không đọc tiền, số lẻ hoặc khoảng số thành tồn kho.
- Luồng local và browser dùng chung kiểm tra vai trò số tiền, chặn giá vốn bị dùng làm giá bán.
- Tin nhắn thuộc tính trên TikTok chỉ cập nhật bản nháp; không ghi form khi chat. Bỏ các số mặc định và thuộc tính tự chọn; giữ tồn 0, không thêm tuyên bố chính hãng.
- Kiểm tra giá trị thực sự được giữ trong ô trước khi báo điền xong; giữ nhãn “chưa đăng”.
- Khi Groq đang trong cooldown do 429, không rút ngắn deadline Gemini để chuyển sang một backup đã biết không sẵn sàng.

## Phạm vi xác minh

Các bài backend, transport, fixture Chrome và build web/iOS được ghi kết quả ở terminal.
Ảnh/JSON QA nằm trong `docs/evaluations/` và được gitignore. Hướng dẫn chạy nằm ở
`frontend/tests/README.md` và `extensions/shopee-connector/README.md`.

Kiểm tra AI thật ban đầu gặp timeout Gemini rồi Groq trả 429. Phép đo độc lập cho
thấy TLS khoảng 0,23s, một yêu cầu rất ngắn nhận HTTP 200 sau 16,52s; một lượt prompt
chat đầy đủ chạm 45s. Sửa cutoff cứng 15s thành phần ngân sách còn lại sau khi dành
tối đa 20s cho backup; giữ tổng deadline bằng timeout wall-clock cho cả primary/backup, connect/pool 5s, write 10s. Log tách pha
network timeout và ghi stage/elapsed khi fallback, không ghi key/prompt.

Lần `npm run ai:check` sau sửa **đã qua toàn bộ** trong 115,0s cho nhiều yêu cầu:
trích giá 5 xị, chat Việt, chi phí/phí/giá bán, đọc ảnh bàn phím tự vẽ và câu ngắn
“bàn phím đó”. Có lượt Gemini chạm read timeout khoảng 25s rồi **Groq trả lời thành
công**; đây là kiểm chứng tích hợp Gemini + backup, không phải bằng chứng mọi lượt
Gemini đều nhanh hoặc hết timeout/quota. Không tạo project ID giả hoặc xoay key
cùng project để vượt quota.

560 test backend, 12 test transport/message, 21 test extension đã qua. Bố cục
320–520px, lịch sử, input dài/cuộn, đổi kỳ và lỗi mạng được kiểm tra bằng fixture;
build web/iOS đã qua. Ảnh thật/tài khoản Shopee/TikTok đăng nhập và bàn phím/safe
area/Dynamic Type trên iPhone thật chưa được xác minh lại trong lượt này.
