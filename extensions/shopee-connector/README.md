# SellerPilot Chrome Extension

SellerPilot mở trong Chrome Side Panel, dùng lại chat, lịch sử, xử lý ảnh và
backend AI của app. Luồng Shopee có **bố cục desktop riêng**, không dùng thanh
điều hướng nổi hoặc khoảng trống bàn phím của app iOS.

Đây là **kết nối qua trình duyệt**, chưa phải tích hợp Shopee Open Platform.
Không cần Partner ID/Partner Key để dùng luồng này. Chỉ có tài khoản người bán
không tự cấp quyền API cho SellerPilot. Đọc qua giao diện phụ thuộc phiên đăng
nhập, phân trang và bố cục trang. Đồng bộ khi trình duyệt đóng hoặc thao tác
không phụ thuộc giao diện cần nguồn tích hợp khác; extension hiện tại chưa bảo
đảm các khả năng đó.

## Hướng kết nối không cần Shopee Open Platform

Đối chiếu mã nguồn và tài liệu ngày **07/11/2026**: **browser companion** là một
phương án hỗ trợ cho tài khoản người bán hiện có. Chủ shop tự đăng nhập Kênh Người
Bán trong Chrome, ghép nối SellerPilot rồi đồng bộ. Content script đọc các
trường đã nhận diện trên giao diện; việc xác thực tài khoản vẫn do Shopee thực
hiện trong trình duyệt. Luồng này không cần Partner ID/Partner Key và không
yêu cầu Mall ở phía mã SellerPilot. Chưa nghiệm thu DOM shop thật thì chưa kết
luận đọc đủ được mọi sản phẩm, biến thể hoặc trạng thái đơn.

**Cập nhật 10/11/2026:** mục tiêu chính là quản lý shop thật trực tiếp trong app,
theo luồng cấp quyền như BigSeller. Phương án extension dưới đây không thay thế
tích hợp đó. Xem [thiết kế chuyển sang shop thật](../../README.md#chuyển-sang-shop-shopee-thật-trên-app)
và điều kiện quyền truy cập trước khi triển khai.

Chrome cung cấp Side Panel và content scripts cho kiểu tích hợp này:
[Side Panel API](https://developer.chrome.com/docs/extensions/reference/api/sidePanel),
[Content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts).
Khả năng của Chrome không đồng nghĩa Shopee xác nhận hoặc bảo đảm tương thích.
Chưa có nguồn chính thức được xác minh trong lần rà soát này để kết luận rằng
mọi Open API tại Việt Nam chỉ dành riêng Shopee Mall; điều kiện cấp quyền vẫn
cần kiểm tra theo loại ứng dụng và tài khoản thực tế.

| Nhu cầu | Hướng thực hiện | Trạng thái |
| --- | --- | --- |
| Xem dữ liệu và hỏi AI cạnh Kênh Người Bán | Extension đọc danh sách, kiểm tra phân trang và cache theo shop | Đã có, cần kiểm chứng trên giao diện tài khoản thật |
| Soạn/sửa nội dung sản phẩm | Tạo bản nháp, duyệt rồi điền form trên Shopee | Đã có; người bán tự hoàn tất lưu/đăng |
| Đọc lịch sử dài theo kỳ, đối chiếu đầy đủ dòng hàng | Nhập file báo cáo CSV/XLSX do người bán chủ động xuất | Đề xuất; chưa có parser hoặc nút nhập file trong app |
| Xem dữ liệu Shopee trên app iPhone | Extension đồng bộ dữ liệu có phạm vi lên backend rồi app đọc nguồn này | Đề xuất; chưa có cầu nối dữ liệu này |
| Đồng bộ mới khi Chrome tắt hoặc phiên Shopee hết hạn | Cần nguồn dữ liệu khác được cấp quyền hoặc file mới | Extension không đáp ứng |

Luồng đang chạy:

```text
Chủ shop đăng nhập Shopee trên Chrome
  → Content script đọc trường được nhận diện
  → Service worker tổng hợp, kiểm tra nhãn shop, độ phủ và hạn dữ liệu
  → Side Panel hiển thị và gửi ngữ cảnh tới backend AI
```

Để đưa dữ liệu lên app iPhone, phần cần xây dựng tiếp là:

```text
Browser companion / file do người bán chọn
  → API đồng bộ có xác thực người bán và quyền nguồn dữ liệu
  → Kho dữ liệu riêng theo shop/nguồn, kiểm tra trùng và cập nhật đồng thời
  → API thống kê theo nguồn Shopee
  → Dashboard, biểu đồ và trợ lý trên app
```

Không nối trực tiếp bảng DOM vào database shop local. Cầu nối mới phải giữ nguồn,
thời điểm đọc, kỳ báo cáo, độ phủ và các trường chưa biết; dùng ID sản phẩm/SKU/
biến thể/mã đơn có kiểm chứng để đối soát, không dùng riêng tên shop làm khóa
bảo mật. App phải hiển thị thời điểm đồng bộ cuối; mất kết nối Chrome thì dùng
dữ liệu đã lưu với trạng thái cũ, không báo đang đồng bộ trực tiếp.

File xuất phù hợp để bổ sung lịch sử và đối soát khi bộ đọc giao diện không
đủ dữ liệu. Cần file mẫu thực tế để kiểm tra cột, múi giờ, mã đơn nhiều dòng,
giảm giá/phí và các trạng thái trước khi viết parser. Chọn trường cần dùng,
xem trước lỗi/dòng trùng và xác nhận nhập; nhập lại cùng file không tạo thêm
đơn. Báo cáo là dữ liệu tại thời điểm xuất, không thay việc ghi trạng thái trực
tiếp lên Shopee.

Phương án này giữ mật khẩu, OTP và cookie trong trình duyệt. Bridge mới thử các
GET cùng origin trong phiên Shopee hiện có; mã CSRF chỉ dùng trong trang, không
trả cookie/token qua extension hoặc backend. Không giải CAPTCHA hay dùng proxy né chặn. Nếu Shopee yêu
cầu xác minh/đăng nhập hoặc cấu trúc trang không rõ, dừng và để người bán xử lý.
Chrome extension chạy trên máy tính; Expo Go trên iPhone không chạy extension.

Tiêu chí trước khi chuyển từ thử nghiệm sang dùng thật: đối chiếu từng SKU/
biến thể, đơn trùng nhiều dòng, đổi shop trong cùng tài khoản, lọc thời gian,
đăng xuất/phiên hết hạn, mất mạng và dữ liệu chưa đọc đủ. Chưa có kết quả các
kiểm tra đó thì chỉ mô tả đúng phạm vi đọc được, không tuyên bố thay thế hoàn
toàn Shopee Seller Centre.

## Cài đặt

Từ thư mục gốc repo:

```sh
npm run extension:setup
npm run extension:build
npm run demo
```

`setup` tạo khóa ghép nối backend riêng trong `.env` và
`connection.local.json`, không in khóa. Mỗi máy tự setup/build. Không upload hay
chia sẻ thư mục `dist` chứa khóa. Nếu backend đã chạy trước lần setup đầu tiên,
chủ động dừng terminal đó rồi chạy lại `npm run demo` để nạp cấu hình mới.

1. Chrome → `chrome://extensions` → **Developer mode** → **Load unpacked**.
2. Chọn `extensions/shopee-connector/dist`, không chọn `frontend/dist/web`.
3. Mở `https://banhang.shopee.vn/`, tự đăng nhập Shopee.
4. Mở SellerPilot → **Liên kết**, rồi bấm **tên tài khoản/shop trên thanh đầu
   trang Shopee** trong 30 giây. Esc hủy chọn. Chỉ click trực tiếp được chấp nhận.
5. Sau khi tên xuất hiện, SellerPilot tự đọc mục Sản phẩm/Tổng quan/Đơn hàng
   trên tab đã liên kết. Không mở tab nền; mỗi nguồn có phạm vi và thời gian cập nhật riêng.
   Không cần tự mở lần lượt các mục. Nút **Cập nhật**
   bắt đầu lượt thu thập mới; có tiến trình số trang/dòng và nút **Dừng đồng bộ**.
6. Hỏi `Sản phẩm nào gần hết hàng?` ngay từ trang Tổng quan. Chat dùng dữ liệu đã
   đồng bộ hoặc dữ liệu đọc được trên trang hiện tại, không tạo tab và không chờ
   quét hết đơn hàng. Nếu dữ liệu chưa có, AI báo trạng thái đồng bộ thay vì đoán số.
   Lỗi đọc, dữ liệu hết hạn hoặc mở lại panel không tự khởi chạy lượt đồng bộ mới;
   bấm **Cập nhật** để chủ động thử lại. Dữ liệu quá 5 phút không dùng làm số liệu hiện tại.

Đổi tài khoản được chọn sẽ tạo phiên mới và lưu riêng lịch sử phiên trước.
Có thể mở lại phiên trong menu tên tài khoản khi mục tiêu đó còn khớp trang.
Tên được chọn là **nhãn trên trình duyệt do người dùng xác nhận**, không phải
Shop ID đã được API xác thực. Nếu cùng một tài khoản quản lý nhiều gian hàng,
chọn nhãn riêng của gian hàng; nếu trang không có nhãn riêng thì chưa thể phân
biệt tự động. Không coi cơ chế này là xác thực bảo mật của Shopee.

Khi sửa code, chạy `npm run extension:build`, bấm **Reload** trên thẻ extension
ở `chrome://extensions`, rồi mở lại side panel. Không cần đổi API key hay dừng
các dịch vụ hiện có chỉ để cập nhật frontend/content script.

## Dữ liệu và giới hạn

- Không gửi mật khẩu, OTP, cookie hoặc CSRF token tới backend. Content script đọc các trường đã nhận diện; bridge đọc cùng phiên được kiểm tra tài khoản trước/sau và chỉ trả các cột được cho phép.
- Không gửi nguyên văn trang. Chỉ chuyển số liệu có nhãn nhận diện được, các
  cột sản phẩm/giá/tồn/đã bán/mã đơn/trạng thái/tổng tiền và nhãn form đã hỗ trợ.
  Loại cột người mua, điện thoại, địa chỉ; không lấy giá trị input.
- URL gửi AI bỏ query/hash; token ngữ cảnh trang là mã ngẫu nhiên nội bộ.
  Tham số URL thay đổi sẽ làm vô hiệu bản đọc để tránh điền nhầm sản phẩm.
- Nhận diện nhãn tài khoản phải duy nhất, hiển thị ngoài nội dung main/form/bảng.
  Không xác nhận được nhãn thì chặn đọc/điền; không tự chọn một kết quả khác.
- Bộ đọc lấy dữ liệu đang nhận diện trên tab liên kết và có thể thử bridge đọc cùng phiên trên Shopee; không mở hoặc điều hướng tab khi người dùng chỉ hỏi chat/đồng bộ.
- Bridge hiện đọc một trang; không tuyên bố đã đọc toàn bộ shop. Không có số tồn thì giữ không xác định, không chuyển thành 0. Dữ liệu chỉ được lưu sau khi kiểm tra lại đúng tài khoản và ngữ cảnh trang.
- Cache có hạn 5 phút và tách theo kết nối/shop. Lỗi tài nguyên giữ dữ liệu cũ với thời điểm thật; không cập nhật giả thành vừa đồng bộ.
- Cần kiểm chứng bridge và bố cục trên tài khoản thật. Endpoint nội bộ có thể thay đổi; kết quả fixture không chứng minh hỗ trợ đầy đủ mọi shop.
- Kỳ thời gian báo cáo chưa được đổi tự động. Không suy kỳ “7 ngày” từ dashboard
  hôm nay. Bảng mẫu đơn hàng gửi AI có cờ sample_truncated; không dùng mẫu để
  cộng doanh thu hoặc đếm toàn bộ đơn.
- Nội dung cột sản phẩm/ảnh do người dùng chọn vẫn là dữ liệu gửi nhà cung cấp AI
  cấu hình trong backend. Giảm dữ liệu không đồng nghĩa đã loại mọi PII nếu
  người dùng đặt thông tin cá nhân ngay trong tên sản phẩm hay ảnh.
- Kiểm tra trạng thái nhãn/trang giúp bỏ dữ liệu cũ khi chuyển trang. Không đảm
  bảo phát hiện mọi thay đổi state nội bộ của Shopee khi nhãn và URL giữ nguyên.

## Chức năng thực tế

| Chức năng | Shopee qua trình duyệt | Shop local |
| --- | --- | --- |
| Chat, lịch sử, ghim/xóa, tối đa 6 ảnh | Có, riêng từng kết nối | Nghiệp vụ app hiện có |
| Tổng quan | Số liệu dashboard và tổng tồn đã đồng bộ; chưa xác minh kỳ tự động | Dashboard từ database |
| Sản phẩm/đơn hàng | Đọc danh sách qua các trang khi nhận diện được phân trang; có độ phủ/giới hạn | Danh sách và thao tác của app |
| Soạn tên/mô tả từ ảnh, hỏi phần thiếu | Có, backend AI riêng | Có |
| Điền tên/mô tả/giá/tồn | Có trên form phù hợp, có kiểm tra giá trị còn giữ | Luồng đăng vào shop local |
| Upload ảnh/ngành hàng/biến thể lên Shopee | Chọn thủ công trên Shopee | Nghiệp vụ local |
| Lưu/đăng, đổi giá thật, xử lý đơn thật | Chưa có xác minh lưu/đăng; chủ shop tự thao tác | Có theo API local |
| Bộ nhớ chi phí/công thức lợi nhuận của app | Chưa nối đầy đủ; không coi tư vấn văn bản là phép tính đã kiểm toán | Có |

Không lấy dữ liệu `UTE MALL` để lấp số liệu thiếu của Shopee. Trong menu kết nối
có **Chuyển sang shop local** nếu muốn dùng hệ thống local; khi đó giao diện app
và API local hoạt động như trước.

## Điền form vào Shopee

Gửi ảnh và thông tin sản phẩm trong chat, duyệt bản nháp rồi bấm **Điền vào form**.
Nếu chưa mở form, extension điều hướng đúng tab liên kết sang trang thêm sản phẩm.
Bản nháp vẫn ở trạng thái sẵn sàng cho tới khi các ô chính được xác minh giữ dữ liệu.
Form nhiều bước được tiếp tục trong tối đa 5 phút, trên cùng shop/tab, sau khi người bán chọn ngành hàng và chuyển bước.

Không có tác vụ tự sửa chạy trên mọi trang sản phẩm. Không tự gán giá/tồn, chia tồn cho biến thể, viết thêm công dụng, chọn No brand/xuất xứ hoặc bật vận chuyển khi chưa có thông tin xác nhận.
Ảnh chỉ được chuyển một lần cho bộ tải ảnh của Shopee trong lượt tiếp tục; người bán cần kiểm tra ảnh đã được nhận.
Người bán tự duyệt và bấm Lưu/Hiển thị. Extension không tự gửi duyệt hoặc tuyên bố đã đăng bán.

Kiểm tra local trước khi tích hợp: unit test đồng bộ/điền form, fixture DOM và build.
Luồng shop thật cần nghiệm thu riêng với chính giao diện đang dùng.

## Chẩn đoán

- Backend mặc định: `http://127.0.0.1:8000` trên cùng máy Chrome.
- Menu tài khoản → **Kiểm tra backend AI** chỉ kiểm tra endpoint ghép nối;
  không chứng minh model/quota hoạt động hay dữ liệu toàn shop đã đồng bộ.
- `404` tại `/api/v1/browser-connector/health`: backend đang chạy bản cũ;
  chủ động khởi động lại `npm run demo`. Reload extension không nạp lại Python.
- Không chọn được tài khoản: bấm trực tiếp chữ tên trên thanh đầu trang, không
  bấm avatar hoặc tên trong bảng. Nếu nhiều nhãn giống nhau, adapter sẽ từ chối.
- Không thấy số liệu/bảng: bố cục đó chưa được nhận diện; không phải lỗi đăng
  nhập và không được dùng số liệu local thay thế. Cần kiểm chứng DOM trang thật.

## Kiểm thử

```sh
npm run typecheck
npm run test:api
npm run test:extension
npm run test:extension:dom
npm run test:extension:ui
```

Hai bài DOM/UI cần Playwright và Chrome; có thể đặt `PLAYWRIGHT_MODULE` và
`CHROME_EXECUTABLE` như các bài QA frontend. UI test cần `extension:build` trước.
Test dùng fixture và RPC giả lập, chặn mạng thật; chỉ thay predicate origin trong
bundle được **phục vụ cho test**, không sửa gói production trên đĩa.

Fixture kiểm tra click thật/giả, target sai, nonce hết hạn/replay, tách lịch sử,
lọc dữ liệu riêng tư, tiền/tiếng Việt nhiều dòng, setter, trường trùng, trang đổi,
framework reset, không submit; UI test kiểm tra 320/380/520px, tab, chat composer,
autoscroll, lịch sử và kết nối. Kết quả fixture không chứng minh tương thích mọi
màn hình Shopee. Load unpacked/CSP, chọn ảnh và form thật phải được kiểm tra trên
Chrome của thành viên trước thuyết trình.

## Nghiệm thu luồng hỏi tồn kho từ trang Tổng quan

1. Giữ trang Tổng quan Shopee, chọn nhãn tài khoản một lần.
2. Chờ tiến trình sản phẩm. Gửi câu hỏi ngay khi đang đồng bộ không tạo tab mới;
   nếu chưa có dữ liệu, câu trả lời nêu đang đồng bộ và không bịa tồn kho.
3. So số trang/SKU và số tồn với danh sách Shopee thực tế. Kiểm tra món tồn 0,
   tồn 1–5, món >5 và dòng không đọc được; không gộp 0 với chưa biết.
4. Đổi tài khoản trong tab đang liên kết: không sử dụng cache của tài khoản cũ.
5. Bấm dừng hoặc đóng panel khi đang đọc: không hiển thị đồng bộ xong giả.

Đã kiểm thử trên fixture, chưa xác minh bộ đọc với tất cả DOM Shopee đăng nhập.
Không mô tả tỷ lệ thành công hoặc độ phủ toàn shop khi chưa nghiệm thu thực tế.

## Kiểm tra tích hợp TikTok

Nhánh TikTok dùng các host được khai báo trong manifest; nhãn kết nối dựa trên
nền tảng của tab đang liên kết. Tin nhắn thuộc tính chỉ cập nhật bản nháp; phải
bấm điền form lại sau khi xem xét. Không tự gán giá/tồn/trọng lượng, xuất xứ,
thương hiệu hoặc chọn thuộc tính đầu tiên. Không tự thêm “chính hãng” vào tên.
Điền đủ bốn ô tên/mô tả/giá/tồn mới được đánh dấu đã điền; không coi đó là đã đăng.

```sh
node extensions/shopee-connector/tests/tiktok-fixture.cjs
```

Dùng cùng `PLAYWRIGHT_MODULE`/`CHROME_EXECUTABLE` như fixture Shopee nếu cần.
Bài này chỉ mở HTML giả lập, kiểm tra giữ tồn 0, không tự đoán vận chuyển,
không submit, ô bị framework trả về giá trị cũ và nhiều ô giá gây mơ hồ.
Chưa nghiệm thu trên DOM của tài khoản TikTok thật. Biến thể, ảnh và các trường
ngành hàng/thuộc tính cần kiểm tra lại trên trang người bán trước khi gửi duyệt.
