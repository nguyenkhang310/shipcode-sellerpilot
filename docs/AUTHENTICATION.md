# Đăng nhập và mở khóa bằng Face ID

## Tài khoản đang dùng

SellerPilot dùng cùng tài khoản và mật khẩu với **Kênh Người Bán local** của repo.
Shop mặc định là `utech-official`; chủ shop là `utech`. Mật khẩu được người cài
đặt lúc bootstrap, không có mật khẩu mặc định trong source. Email cũng dùng để
đăng nhập được. Tài khoản người mua hoặc tài khoản đánh giá catalog không có
quyền vào app. Đây không phải đăng nhập tài khoản Shopee thật.

Quên mật khẩu: tại thư mục gốc chạy:

```sh
npm run auth:reset
```

Nhập tên đăng nhập (Enter để chọn `utech`), mật khẩu mới 12–256 ký tự và nhập
lại. Ký tự không hiện khi gõ. Lệnh chỉ đổi hash của tài khoản **chủ shop local
đang liên kết**, không tạo lại database, không đổi sản phẩm/đơn hay quyền thành
viên. Không truyền mật khẩu vào tham số lệnh. Phiên API có mật khẩu cũ bị từ
chối ở lượt truy cập kế tiếp. Chỉ người có quyền truy cập terminal/database máy
chủ mới được dùng lệnh này; đây không phải API khôi phục mật khẩu công khai.

Sau khi cập nhật code, cài dependency backend/frontend theo README rồi khởi động
lại `npm run demo`. Script tự chạy migration `20261021_12` trước API. Không chạy
lại bootstrap trên dữ liệu đang dùng.

## Bật Face ID trên iPhone

1. Cài bản native lên iPhone đã thiết lập Face ID và mật mã thiết bị.
2. Đăng nhập bằng mật khẩu lần đầu.
3. Vào **Shop → Tài khoản & bảo mật → Mở khóa bằng Face ID**.
4. Đưa app xuống nền rồi quay lại; chạm **Mở khóa bằng Face ID**. Có thể chọn
   **Dùng mật khẩu tài khoản** khi hủy xác thực, đổi sinh trắc học hoặc phiên hết hạn.

Phiên được lưu trong iOS Keychain với `requireAuthentication` và
`WHEN_UNLOCKED_THIS_DEVICE_ONLY`. Đọc phiên yêu cầu sinh trắc học do iOS quản
lý; app không nhận/lưu ảnh khuôn mặt. Khi bật bảo vệ, bản phiên không yêu cầu
sinh trắc học được xóa. Đổi bộ khuôn mặt/vân tay có thể làm khóa đã lưu mất hiệu
lực, khi đó đăng nhập lại bằng mật khẩu. Tắt bảo vệ cũng yêu cầu đọc Keychain
qua sinh trắc học. App dùng màn che riêng tư khi không hoạt động và khóa khi
xuống nền; các tab dữ liệu bị tháo khỏi cây UI khi khóa.

**Face ID không hoạt động trong Expo Go hoặc bản web.** Expo Go vẫn đăng nhập
bằng mật khẩu; mục sinh trắc học giải thích cần bản cài riêng. iPhone có Touch
ID hiện đúng nhãn Touch ID. Android hỗ trợ sinh trắc học nếu thiết bị đáp ứng
khả năng SecureStore, không mang nhãn Face ID.

Trên Mac đã có **Xcode đầy đủ**, Command Line Tools trỏ đến Xcode, iPhone nối
máy và bật Developer Mode, chạy từ root:

```sh
npm run ios:native
```

Expo tạo project iOS và yêu cầu cấu hình ký ứng dụng/Apple development team.
Địa chỉ API phải tới được từ iPhone (cùng LAN khi phát triển); dải dependency
và plugin Face ID đã có trong `frontend/app.json`. Lệnh `npm run build:ios`
chỉ xuất JavaScript, **không phải** tạo/cài ứng dụng có Face ID. Nếu chỉ có
Command Line Tools, cần cài Xcode trước khi chạy `ios:native`.

Tham khảo [Expo LocalAuthentication SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/local-authentication/)
và mã native `expo-secure-store` đang khóa trong package-lock.

## Phiên và quyền truy cập API

Sàn và API phải dùng Python 3.11+ với `hashlib.scrypt`, như hướng dẫn README.
`npm run demo` kiểm tra điều kiện này trước khi mở dịch vụ. Lệnh `auth:reset`
tạo PBKDF2-SHA256 với 600.000 vòng, tương thích cả hai phía; các hash scrypt đã
lưu vẫn được xác minh bình thường trên môi trường đúng. Không chuyển đổi hash
cũ khi chưa có mật khẩu gốc và không đặt lại mật khẩu tự động.

- `POST /api/v1/auth/login`: JSON `login_id`, `password`; trả `data.token`,
  thông tin user/shop và `expires_at`. Token ngẫu nhiên 32 byte, thời hạn 7 ngày;
  database chỉ giữ SHA-256, không lưu token gốc hay mật khẩu mới.
- `GET /api/v1/auth/me`: kiểm tra phiên. API kiểm tra lại mật khẩu hiện tại,
  thành viên và trạng thái shop ở mỗi lượt truy cập. Đổi mật khẩu, xóa quyền
  hoặc ngừng shop làm phiên cũ bị từ chối.
- `POST /api/v1/auth/logout`: thu hồi phiên hiện tại, xóa thông tin trên thiết
  bị. Nếu mất mạng, UI nói rõ chưa xác nhận thu hồi ở server.
- Gửi `Authorization: Bearer <token>` cho chat, lịch sử, số liệu, sửa sản phẩm,
  xử lý đơn, proposal và ảnh bản nháp. `401` đưa app về đăng nhập; phản hồi cũ
  của tài khoản trước không được xóa phiên mới. Swagger có nút **Authorize**
  cho `SellerSession`; dán token ở đó, không đưa token lên Git hoặc ảnh báo cáo.
- Web chỉ giữ token trong bộ nhớ: tải lại/đóng trang cần đăng nhập lại; không
  lưu trong localStorage/sessionStorage. Native dùng SecureStore. Bản nháp
  hội thoại trên thiết bị tách theo API, shop và tài khoản.
- Khi không có token đã lưu, app mở đăng nhập mà không gọi `/auth/me`. Nếu
  token đã lưu bị trả `401`, app xóa phiên khỏi SecureStore để reload không
  gửi lại token bị từ chối. Lỗi mạng/5xx không xóa phiên đã lưu.
- API trả `Cache-Control: no-store`. Ảnh chat chưa đăng không truy cập được
  qua static công khai; ảnh được gắn vào sản phẩm đã đăng vẫn là ảnh catalog.
- Đăng nhập giới hạn bền vững trong SQLite: 10 lượt/tài khoản và 60 lượt/IP
  trong 15 phút. `429` trả `Retry-After`. Tên đăng nhập/IP trong bộ đếm được băm.
- Extension local chuyển Bearer qua RPC; extension Shopee thật giữ luồng token
  connector và ràng buộc tab/tài khoản riêng, không nhận quyền shop local.

App hiện phục vụ **một shop do server cấu hình**; các thành viên quản lý hợp lệ
của shop làm việc trên dữ liệu/hội thoại chung của shop. Chưa có cấp quyền chi
tiết theo từng chức danh hoặc cổng đăng ký nhiều shop. Khi triển khai Internet
cần HTTPS cho API/web, CORS đúng origin, bảo vệ máy chủ/database và proxy rate
limit. Không coi CORS hay Face ID là thay thế cho xác thực server.

Khi khởi động, app vẽ viền logo gồm cả SHIP và CODE, chuyển sang ảnh logo gốc,
giữ ảnh đầy đủ một nhịp rồi mở form. Chỉ phần nét SVG dùng cập nhật JS; phần
hiện ảnh và phóng/mờ dùng native driver trên iOS/Android. Không chạy intro lại
khi đăng xuất. Tùy chọn Giảm chuyển động bỏ qua vẽ/phóng logo và chuyển cảnh.
Đăng nhập thành công mới hiện dấu tích và chuyển vào Quản lý; hết hạn hoặc
đăng xuất gỡ nội dung shop ngay, không giữ màn hình riêng tư để chạy hiệu ứng.

## Kiểm thử

`npm run test:auth` kiểm tra lưu Keychain, lỗi/hủy sinh trắc học, chuyển trạng
thái bảo vệ, đăng xuất, đua ghi và Bearer/401. Đây là mô phỏng API hệ điều hành,
không giả vờ đã chạy camera Face ID. Backend dùng shop tạm để kiểm tra quyền,
băm phiên, thu hồi, hết hạn, đổi mật khẩu, giới hạn đăng nhập và ảnh riêng tư.

Browser thật chạy với server `backend/tests/auth_ui_server.py` ở cổng 8124 và
`frontend/tests/auth-login.cjs`, `auth-transition.cjs`: xem hướng dẫn frontend/tests/README.md.
Trước khi demo trên iPhone thật cần kiểm tra: cho phép/từ chối Face ID, xác thực
sai/hủy, chuyển nền, khởi động lại app, mất mạng, đăng xuất và đổi sinh trắc học.
