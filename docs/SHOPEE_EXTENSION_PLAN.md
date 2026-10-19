# SellerPilot — luồng Chrome Extension kết nối Shopee

Trạng thái: đã có bản kết nối trình duyệt, desktop shell riêng dùng chung chat
và backend inference ngày 19/10/2026; xem [cài đặt và ma trận tính năng thực tế](../extensions/shopee-connector/README.md).
Chưa đạt đủ nghiệp vụ app trên Shopee thật, chưa kiểm thử trên phiên Shopee đăng nhập.
Không coi tỷ lệ thành công 95–100% hoặc thời gian 20 phút trong bản đề xuất đầu vào
là kết quả kiểm chứng.

## Mục tiêu

Giữ app SellerPilot và shop local để phát triển; bổ sung một kết nối độc lập tới
Kênh Người Bán Shopee thật trong Chrome trên máy tính. AI soạn nội dung, chủ shop
kiểm tra, extension hỗ trợ điền form đang mở. Việc lưu/đăng chỉ thành công khi
Shopee xác nhận; điền xong form chưa phải đăng sản phẩm.

Luồng ưu tiên cho bản đầu:

1. Chủ shop tự đăng nhập `https://banhang.shopee.vn/` và mở form thêm sản phẩm.
2. Mở SellerPilot bên cạnh bằng side panel của Chrome.
   Liên kết bằng cách chọn trực tiếp nhãn tài khoản/shop trên thanh đầu trang.
   Đây là mục tiêu do người dùng chọn, chưa phải danh tính shop được API xác thực.
   Chỉ thu trường/bảng được nhận diện; không gửi nguyên văn trang hoặc cột người mua.
3. Gửi ảnh và thông tin sản phẩm cho AI. AI tổng hợp thông tin đã có, chỉ hỏi phần
   còn thiếu; không tự đoán giá, tồn kho hoặc thông số không được xác minh.
4. Xem bản nháp gồm ảnh, tên, mô tả, giá, tồn kho. Danh mục Shopee cần được xác
   minh riêng; ID danh mục shop local không phải ID danh mục Shopee.
5. Bấm “Điền vào Shopee”; xem kết quả từng trường: đã điền, chưa hỗ trợ hoặc cần
   kiểm tra. Nếu không tìm thấy trường chính xác thì không điền nhầm ô khác.
6. Chủ shop kiểm tra thông tin và bấm lưu/đăng trên Shopee. Chỉ hiển thị trạng
   thái đã đăng khi có bằng chứng từ trang kết quả; chưa xác minh thì ghi rõ.

Có thể mở rộng tiếp sang đọc danh sách sản phẩm, phân tích dữ liệu đang hiển thị
và đề xuất chỉnh sửa. Không đưa thao tác gửi tin nhắn khách vào bản đầu.

## Điều chỉnh so với đề xuất ban đầu

- `sidePanel.default_path` phải trỏ tới HTML trong gói extension. Không đặt URL
  Expo/localhost trực tiếp vào trường này. Cần đóng gói giao diện web phù hợp
  CSP hoặc làm vỏ side panel và cầu nối có kiểm tra nguồn nếu nhúng web app.
- Frontend hiện tại là Expo/React Native, backend là FastAPI; có thể tái sử dụng
  logic AI, schema và phần giao diện phù hợp, nhưng không đảm bảo giữ nguyên
  100% code khi chuyển sang extension.
- Content script đọc được DOM của trang được cấp quyền. Danh sách phân trang,
  bảng ảo hóa hoặc thông tin chưa mở không tự biến thành dữ liệu toàn shop.
- Hàm setter trong đề xuất luôn ưu tiên `HTMLInputElement.prototype` nếu có,
  kể cả khi phần tử là textarea. Cần chọn prototype đúng loại phần tử; rich-text
  editor và upload ảnh cần adapter riêng.
- `input`/`change` tổng hợp không phải sự kiện người dùng đáng tin cậy và không
  đảm bảo Shopee nhận state. Phải đọc lại, chờ render lại và kiểm chứng giá trị;
  không tuyên bố vượt mọi framework hoặc kiểm tra của Shopee.
- Sao chép là nút dự phòng do người dùng bấm, có báo lỗi nếu clipboard bị từ
  chối. Sao chép không đồng nghĩa điền form hoặc đăng thành công.

## Kiến trúc dự kiến

```text
SellerPilot side panel
        ↕ dữ liệu có schema / yêu cầu người dùng
Extension service worker
        ↕ message có kiểm tra tab + nguồn + thao tác
Shopee content script → DOM form hiện tại

Side panel → FastAPI → Gemini/Groq
             ↳ dữ liệu Shopee đã đọc, không ghép số liệu local
```

Ranh giới trách nhiệm dự kiến (file hiện có và phần còn cần hoàn thiện xem README extension):

| Thành phần | Trách nhiệm |
| --- | --- |
| `extensions/shopee-connector/manifest.json` | Manifest V3, side panel, quyền tối thiểu |
| `service-worker.js` | Kiểm tra tab, điều phối message, gọi backend theo endpoint cố định |
| `sidepanel.html` + JS/CSS đóng gói | Chat, bản nháp và trạng thái từng trường |
| `content/shopee.js` | Nhận diện trang/form, đọc và điền trường đã hỗ trợ |
| `content/fields.js` | Tìm trường theo label/thuộc tính có nghĩa, tránh phụ thuộc class sinh ngẫu nhiên |
| API connector riêng trong backend | AI và bản nháp dành cho kết nối Shopee; tách khỏi luồng publish local |

Không nhúng khóa Gemini/Groq vào extension. Khóa tiếp tục nằm trong `.env` của
backend. Quyền truy cập Shopee giới hạn đúng host cần dùng; không xin toàn bộ
website, cookie hoặc lịch sử duyệt web. Backend dùng ghép nối/token cho connector,
kiểm tra Origin khi thích hợp; không biến localhost thành proxy nhận URL tùy ý.

## Tách nguồn dữ liệu là yêu cầu bắt buộc

Code hiện tại khởi tạo `UTEMallRepository` trong `backend/app/main.py`.
`chat_dispatch.py`, `advisor.py`, `business_advisor.py` và luồng bản nháp dùng
repository này. `/product-drafts/{id}/publish` đăng vào database local.

Vì vậy không được chỉ nhúng app rồi đổi chữ nút thành “Đăng Shopee”. Cần:

- Connection riêng: loại `local` hoặc `shopee_browser`, ID kết nối, danh tính
  shop được xác minh, tab nguồn, thời điểm đọc và phạm vi đọc.
- Lịch sử/bản nháp gắn với connection; chuyển shop không mang số liệu và đề
  xuất ghi của shop cũ sang shop mới.
- Dữ liệu đọc trang có độ phủ rõ ràng: trang hiện tại, bộ lọc, kỳ thời gian,
  số dòng đã đọc. Thiếu số liệu toàn shop thì AI nói thiếu, không thay bằng DB local.
- Các nút publish local không xuất hiện trong luồng Shopee thật. ID sản phẩm,
  biến thể, ngành hàng của hai nguồn không dùng thay thế cho nhau.
- Đầu vào lấy từ DOM và phản hồi AI đều được xác thực schema; nội dung trang
  là dữ liệu, không phải chỉ dẫn cho AI thực hiện thao tác ngoài phạm vi.

## Thứ tự triển khai

1. **Kết nối:** load unpacked extension; mở side panel; ghép nối FastAPI; nhận
   diện đúng tab Shopee và báo chưa đăng nhập/chưa mở form.
2. **Bản nháp:** AI soạn tên/mô tả từ ảnh và thông tin đã cho, hỏi thiếu chính xác;
   tách trạng thái và lịch sử khỏi shop local.
3. **Điền form:** tên, mô tả, giá, tồn kho của form không có biến thể trước.
   Bổ sung ảnh, ngành hàng, thuộc tính/biến thể sau khi kiểm tra DOM thực tế.
4. **Đọc và tư vấn:** đọc sản phẩm/số liệu có phạm vi, AI dùng đúng snapshot;
   không suy diễn doanh thu toàn shop từ một bảng sản phẩm.
5. **Kiểm thử phiên thật:** chủ shop đăng nhập; hiệu chỉnh adapter với form thật;
   kiểm tra từng trường và xác nhận kết quả lưu/đăng.

## Tiêu chí nghiệm thu

- Tách biệt tuyệt đối dữ liệu/ghi local với phiên Shopee.
- Tìm đúng một trường mới điền; trường trùng/ẩn/disabled báo rõ, không chọn bừa.
- Tiếng Việt, tiền VND, textarea, rich text và render lại được kiểm thử riêng.
- Đổi tab, đổi shop, điều hướng, hết phiên, mất backend và request lặp không
  áp dụng dữ liệu vào nhầm trang hoặc làm lặp thao tác ghi.
- Không tự submit form, không vượt CAPTCHA/kiểm tra đăng nhập.
- Bảng kết quả phân biệt đã điền, cần xử lý thủ công, lưu chưa xác minh và đã đăng.
- Fixture local giúp kiểm thử lặp lại; chỉ kiểm thử DOM thật trong phiên đăng
  nhập mới chứng minh được hỗ trợ Shopee hiện tại.

## Tài liệu gốc

- [Chrome Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel)
- [Content scripts và isolated world](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
- [Extension CSP](https://developer.chrome.com/docs/extensions/reference/manifest/content-security-policy)
- [Cross-origin requests và host permissions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests)
- [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)
