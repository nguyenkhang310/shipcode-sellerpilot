# SellerPilot Chrome Extension

SellerPilot mở trong Chrome Side Panel, dùng lại chat, lịch sử, xử lý ảnh và
backend AI của app. Luồng Shopee có **bố cục desktop riêng**, không dùng thanh
điều hướng nổi hoặc khoảng trống bàn phím của app iOS.

Đây là **kết nối qua trình duyệt**, chưa phải tích hợp Shopee Open Platform.
Không cần Partner ID/Partner Key để dùng luồng này. Chỉ có tài khoản người bán
không tự cấp quyền API cho SellerPilot. Đồng bộ toàn shop và thao tác độc lập
với trang đang mở vẫn cần ứng dụng được Shopee cấp quyền và adapter riêng.

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
5. Sau khi tên xuất hiện trên SellerPilot, bấm **Cập nhật** để đọc các trường
   được hỗ trợ của trang hiện tại. Chat sẽ tự đọc lại khi gửi tin.

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

- Không đọc mật khẩu, cookie, hidden state, script hay API nội bộ Shopee.
- Không gửi nguyên văn trang. Chỉ chuyển số liệu có nhãn nhận diện được, các
  cột sản phẩm/giá/tồn/đã bán/mã đơn/trạng thái/tổng tiền và nhãn form đã hỗ trợ.
  Loại cột người mua, điện thoại, địa chỉ; không lấy giá trị input.
- URL gửi AI bỏ query/hash; token ngữ cảnh trang là mã ngẫu nhiên nội bộ.
  Tham số URL thay đổi sẽ làm vô hiệu bản đọc để tránh điền nhầm sản phẩm.
- Nhận diện nhãn tài khoản phải duy nhất, hiển thị ngoài nội dung main/form/bảng.
  Không xác nhận được nhãn thì chặn đọc/điền; không tự chọn một kết quả khác.
- Số liệu chỉ là trang hiện tại. Không tự đọc trang tiếp, kỳ báo cáo hay toàn bộ
  shop. Không suy kỳ “hôm nay/7 ngày” nếu chưa có bằng chứng. Dữ liệu không rõ
  không được tự đổi thành 0. Bảng cần có header nhận diện được.
- Nội dung cột sản phẩm/ảnh do người dùng chọn vẫn là dữ liệu gửi nhà cung cấp AI
  cấu hình trong backend. Giảm dữ liệu không đồng nghĩa đã loại mọi PII nếu
  người dùng đặt thông tin cá nhân ngay trong tên sản phẩm hay ảnh.
- Kiểm tra trạng thái nhãn/trang giúp bỏ dữ liệu cũ khi chuyển trang. Không đảm
  bảo phát hiện mọi thay đổi state nội bộ của Shopee khi nhãn và URL giữ nguyên.

## Chức năng thực tế

| Chức năng | Shopee qua trình duyệt | Shop local |
| --- | --- | --- |
| Chat, lịch sử, ghim/xóa, tối đa 6 ảnh | Có, riêng từng kết nối | Nghiệp vụ app hiện có |
| Tổng quan | Số liệu nhận diện được trên trang; chưa xác minh kỳ tự động | Dashboard từ database |
| Sản phẩm/đơn hàng | Các dòng/cột nhận diện được trên trang đang mở | Danh sách và thao tác của app |
| Soạn tên/mô tả từ ảnh, hỏi phần thiếu | Có, backend AI riêng | Có |
| Điền tên/mô tả/giá/tồn | Có trên form phù hợp, có kiểm tra giá trị còn giữ | Luồng đăng vào shop local |
| Upload ảnh/ngành hàng/biến thể lên Shopee | Chọn thủ công trên Shopee | Nghiệp vụ local |
| Lưu/đăng, đổi giá thật, xử lý đơn thật | Chưa có xác minh lưu/đăng; chủ shop tự thao tác | Có theo API local |
| Bộ nhớ chi phí/công thức lợi nhuận của app | Chưa nối đầy đủ; không coi tư vấn văn bản là phép tính đã kiểm toán | Có |

Không lấy dữ liệu `UTE MALL` để lấp số liệu thiếu của Shopee. Trong menu kết nối
có **Chuyển sang shop local** nếu muốn dùng hệ thống local; khi đó giao diện app
và API local hoạt động như trước.

## Điền form

1. Mở form thêm/sửa sản phẩm Shopee, chọn ngành hàng phù hợp.
2. Trong chat, chọn ảnh rồi nhập thông tin đã biết, ví dụ:
   `Bàn phím trắng, giá 5 xị, còn 12 cái. Viết tên và mô tả giúp mình.`
3. Nếu chưa nhận diện được ô, menu tên tài khoản → **Gán ô trên form sản phẩm**,
   chọn từng trường rồi bấm đúng ô trên Shopee trong 30 giây.
4. Duyệt bản nháp → **Điền vào Shopee**. Không tự bấm Save/Publish/submit.
5. Tự chọn ảnh, ngành hàng, thuộc tính, biến thể; kiểm tra form rồi lưu/đăng
   trên Shopee. **Đã điền không phải đã đăng.**

Giá trị bị khóa, nhãn trùng, vượt độ dài, trang đổi hoặc bị framework reset sẽ
báo lỗi. Rich text/iframe/biến thể cần kiểm thử riêng trên Shopee thật.
Ảnh và lịch sử lưu trong Chrome storage, không vào database shop local. Xóa
cuộc trò chuyện sẽ xóa ảnh/bản nháp liên quan. Gỡ extension sẽ mất lịch sử.

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
