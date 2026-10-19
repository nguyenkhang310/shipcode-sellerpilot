# Kết quả kiểm tra SellerPilot local

> Các kết quả Muse bên dưới là bản ghi lịch sử. Cấu hình và kiểm chứng GLM hiện tại nằm tại [GLM_SETUP.md](GLM_SETUP.md).

Đã chạy local trên macOS, Node 22.22.2 và Python 3.11.13:

| Kiểm tra | Kết quả |
|---|---|
| TypeScript (`npm run typecheck`) | Pass |
| Expo web export (`npm run build`) | Pass, 444 modules |
| Expo iOS export (`npm run build:ios`) | Pass, 813 modules, Hermes bundle |
| Backend `python -m pytest` | 87 passed |
| `alembic upgrade head`, `alembic current` | Pass; revision `20261015_02` |
| `pip check` | Không có dependency lỗi |
| Khởi động `backend/run_api.sh` | Pass |
| `GET /api/v1/health` | 200; `provider=opencode`, Muse Spark Free available, hai DB ok |
| Tổng quan shop thật ngày 18/04/2026 | 3 đơn, 1.050.000đ, 3 pending |
| Tra SKU biến thể Livostyle | 200; đúng tên, giá, tồn kho |
| Low stock | 200; trả đúng các biến thể tồn 0–5 |
| Proposal/confirm/reject/conflict/idempotency | Pass trên database test tạm |
| Qwen evaluation | 17/17 câu tiếng Việt pass |
| `POST /chat` qua HTTP | `mode=ai`, provider `opencode`, model Muse Spark Free, facts đúng |
| Hội thoại “hôm nay mình hơi mệt” | `intent=unknown`, trả lời tự nhiên trong 11,5 giây |
| Tổng quan shop qua Muse Spark | 12 đơn, 13.805.000đ, 3 pending; 11,6 giây |
| Inventory → proposal → confirm → đọc lại | Pass trên bản sao DB: 400.000đ → 410.000đ |
| Free-model guard | Pass: từ chối model khác, cost khác 0 và OpenCode tool call |
| Expo AssistantChat → API | Đã nối chat, trạng thái chờ, lỗi, AI/fallback và proposal |
| Proposal từ chat → reject | Pass; giá trước/sau vẫn là 1.270.000đ |
| Prompt “bỏ qua xác nhận” | Chỉ tạo proposal pending; đã reject, giá không đổi |
| Phục hồi confirm bị ngắt giữa hai database | Pass; hoàn tất đúng một audit |
| `GET /docs` | 200 |
| Khởi động Expo dev port 5173, HTTP GET | 200 |
| CSV/JSON mẫu | Khóa tham chiếu, tổng đơn, timestamp timezone hợp lệ |
| Tài liệu plan/prompt gốc | Bản sao docs khớp byte với bản UTE |
| Frontend dependency versions | Không thay phiên bản dependency cũ |

Giới hạn: kết nối Browser của phiên làm việc không khả dụng nên chưa xác nhận trực
quan bằng tự động hóa. Máy hiện chỉ có Xcode Command Line Tools, chưa có Xcode đầy đủ
nên chưa chạy iOS Simulator/thiết bị thật; iOS export không phải IPA hay native build.
CI mới được cấu hình, chưa có lần chạy trên GitHub.

Pytest có một cảnh báo deprecation từ Starlette TestClient về HTTPX, không làm test
fail. Expo có cảnh báo biến màu terminal và log tự phát hiện `src/app`; app vẫn dùng
entry `index.ts` và navigation React Native hiện có, chưa cài Expo Router.

Phạm vi đã kiểm thử gồm Muse Spark qua OpenCode, Qwen + fallback, seller tools,
frontend API client, trace và approval đổi giá local. Lượt confirm Muse Spark được
chạy trên bản sao database; dữ liệu shop chính không bị đổi. Chưa có inbox khách hàng
hoặc kết nối Shopee/TikTok.
## Kiểm chứng bổ sung ngày 19/10/2026

- Backend: `413 passed` sau bổ sung kế hoạch kinh doanh và sửa sản phẩm có xác nhận.
- TypeScript: `npm run typecheck` thành công; web export thành công; `npm run test:api`: 11 bài đạt.
- Gemini thật trên DB tạm: kế hoạch 7 ngày, kịch bản TikTok 25 giây, đo hiệu quả nối tiếp;
  viết lại nội dung → đề xuất → xác nhận → xác nhận lặp. Không sửa dữ liệu shop thật.
- Chrome riêng, API giả lập: viewport 390/320 px, không tràn ngang, Hôm nay/7/30 ngày
  hiển thị đúng số tương ứng; dark mode; mở toàn bộ mô tả dài và xác nhận thẻ sửa.
  Không có lỗi JavaScript trong các luồng này. Không thay thế kiểm thử native iOS/Android.
- Migration mới được thử nâng từ revision trước và hạ lại trên DB tạm, giữ lịch sử cũ.

### Sửa giật khi đổi Hôm nay / 7 ngày / 30 ngày

- Tách trạng thái kéo làm mới khỏi tải kỳ thống kê và đồng bộ chương trình;
  áp dụng cùng cách cho danh sách đơn hàng khi trở lại tab.
- Giữ khung biểu đồ, trạng thái đơn, dòng so sánh và chiều cao số liệu trong lúc
  chờ. Không hiển thị số liệu kỳ cũ dưới nhãn kỳ mới. Không chèn banner lỗi phía
  trên bộ chọn kỳ khi đã có dữ liệu.
- Hook React: 3 bài đạt, bao gồm hủy yêu cầu, phản hồi muộn/sai kỳ, cache,
  phục hồi lỗi và polling. Test API/lịch sử chat: 11 bài đạt.
- Chrome với API giả: `dashboard-periods`, `dashboard-live`, `app-audit`,
  `chat-scroll`, `chat-motion` đạt; không có lỗi JavaScript trong các luồng này.
  Ở 390 px, khi chờ/lỗi/hồi phục: chiều cao trang giữ 1723 px, thẻ doanh thu
  483 px, trạng thái đơn 199 px; vị trí cuộn giữ 180 px và 947 px trong hai
  tình huống kiểm tra. Đây là kích thước của dữ liệu QA, không cố định chiều cao
  toàn trang trên các thiết bị khác.
- Rà năm tab ở 320/375/430 px; ảnh sản phẩm tải được; lọc/tìm/mở đơn; ô chat
  55 dòng giữ con trỏ cuối; tự cuộn câu trả lời dài; lịch sử; giao diện tối và
  Giảm chuyển động. Bàn phím trong bài browser là viewport giả lập.
- TypeScript, web export và iOS Hermes export đạt. Chưa chạy trực tiếp trên
  iPhone/Android; export iOS không thay thế kiểm thử RefreshControl native.

### Nhận diện Shopee và đánh giá toàn catalog

- Thay nhận diện web bằng Shopee vector, favicon lưu local; đồng bộ tên nền tảng
  trong app và lời nhắc AI. Giữ nguyên đường dẫn thư mục/database `UTE MALL/`.
- Trang đăng nhập/đăng ký có header và footer riêng, nền cam, logo xếp dọc,
  nút hiện/ẩn mật khẩu, duy trì đăng nhập và lỗi xác thực trong form. Không còn
  nhãn demo trên giao diện; tài liệu và cột `review.is_demo` giữ nguồn dữ liệu.
- Bổ sung một lần 16–32 đánh giá theo ngành hàng cho mỗi sản phẩm active;
  đồng bộ tổng số và điểm trung bình. Không tạo đơn hoặc sửa giá/tồn/số đã bán.
  Sản phẩm mới được bổ sung trước khi catalog hiển thị; seed có receipt chống trùng.
- Database local ghi nhận 5.900 sản phẩm active, 142.627 đánh giá, trong đó 141.254
  đánh giá mới có `is_demo=1`; không có sản phẩm active thiếu bình luận và không có
  tổng số đánh giá lệch với bảng review tại thời điểm kiểm tra.
- Store: 18 bài nghiệp vụ đạt, rà 181 liên kết điều hướng; 6 bài cho đánh giá đạt
  trên DB tạm. Backend: 413 bài đạt; TypeScript đạt; API/lịch sử chat: 11 bài đạt.
- Chrome trên store QA riêng: 24 màn công khai và 28 màn Kênh Người Bán ở desktop/
  mobile đạt; kiểm tra auth ở 320/390/768/1440 px, logo, hiện/ẩn mật khẩu, lỗi sai
  mật khẩu, đăng nhập local, phản hồi shop, danh sách và lọc sao. Không có lỗi JS.
- QR/Facebook/Google chưa có xác thực thật; nút hiển thị thông báo khi bấm.
  Các tên thanh toán/vận chuyển trên footer là phần nhận diện giao diện, không
  mở thêm tích hợp giao dịch. Kết quả/ảnh QA ở `docs/evaluations/shopee-branding/`.

### Ổn định trang đăng nhập và căn logo footer

- Bỏ hiệu ứng dịch chuyển trang ở auth; font Roboto Latin/Vietnamese lưu local,
  preload và `font-display: optional` để tránh đổi font muộn làm nhảy chữ.
- Căn nội dung từng ô thanh toán/vận chuyển vào giữa, xuống dòng nhãn dài tại
  vị trí hợp lý; căn ba badge tải ứng dụng bằng chiều cao mã QR. Footer chuyển
  cột sớm hơn trên màn hình vừa, không ép logo vào ô quá hẹp.
- `UTE MALL/tests/auth_layout.cjs`: Chrome QA ở 320/390/768/1024/1440 px,
  font bình thường/chậm 700 ms/bị chặn đều đạt; tiêu đề và nút không dịch chuyển
  trong các frame đo (0 px), nhãn logo không tràn, QR/badge thẳng mép.
- Kiểm lại bật/tắt nút, hover, hiện/ẩn mật khẩu, lỗi mật khẩu và đăng nhập local
  qua `shopee_branding.cjs`: đạt, không có lỗi JavaScript. Dùng database QA riêng;
  không khởi động lại tiến trình `npm run demo` của người dùng.
- Ảnh và kết quả đo: `docs/evaluations/auth-layout/` (artifact local được ignore).

### Chrome Extension — bản kết nối ban đầu

- Đóng gói cùng Expo web bundle vào `extensions/shopee-connector/dist`; HTML
  không có inline/remote script, các entry/assets tồn tại, không tìm thấy giá trị
  Gemini/Groq API key trong bundle. Gói private có khóa ghép nối riêng, được ignore.
- TypeScript đạt; 11 bài API/lịch sử app đạt. Backend toàn suite 426 bài đạt trước
  khi bổ sung bài hủy/capacity; sau đó riêng bộ connector 14 bài đều đạt.
- Năm bài extension đạt: chặn fallback dữ liệu local, nguồn URL, allowlist API,
  tải ảnh lặp, lưu ảnh một lần, ghim/xóa/khôi phục phiên và không coi điền là đăng.
- Chrome fixture đạt: input/textarea nhiều dòng tiếng Việt, sự kiện native setter,
  chặn trường trùng, tài liệu cũ, giá trị bị framework reset và form đăng nhập.
  Fixture được intercept trong browser riêng, không phải trang Shopee thật.
- Gemini thật với dữ liệu kiểm thử: chat 2,12 giây; soạn text 1,40 giây, “5 xị”
  thành 500.000đ và tồn 12; nhận ảnh máy hủy giấy 3,11 giây, giá 1.200.000đ/tồn 3.
  Thời gian của ba lượt này không phải cam kết độ trễ. Kết quả ở
  `docs/evaluations/browser-connector/`, không có key hoặc dữ liệu shop thật.
- Chưa kiểm chứng Load unpacked/CSP, chọn ảnh trong extension, dashboard/catalog/
  đơn hàng và lưu/đăng trong phiên Shopee thật. Công cụ Chrome không kết nối được
  phiên hiện tại. Cần nạp extension và báo cáo DOM của các trang sau đăng nhập.
- Chưa đạt yêu cầu đầy đủ nghiệp vụ app trên Shopee thật. Phạm vi còn thiếu và
  các bước lấy báo cáo ghi trong `extensions/shopee-connector/README.md`.

### Sửa lỗi Chrome từ chối thư mục `_expo`

- Đổi tên các thư mục Expo dành riêng trong bản copy của extension, cập nhật
  đường dẫn script và font; giữ nguyên export web dùng thông thường.
- Thêm kiểm tra tên file/thư mục và tài nguyên thật vào cuối mỗi lần build.
  Hai bài đóng gói kiểm tra bundle/font, giữ nguyên dữ liệu nhị phân và định danh
  runtime Expo, chạy lặp, đồng thời chặn tên cấm và đường dẫn thiếu.
- `npm run test:extension`: 7 bài đạt. Load unpacked trên Chrome của người dùng
  vẫn là bước kiểm chứng riêng sau khi build; không coi kiểm tra file là đã cài.

### Chẩn đoán 404 và thông báo liên kết extension

- API đang chạy trả 200 ở `/health`, nhưng 404 ở `/browser-connector/health`;
  OpenAPI của tiến trình đó không có route connector. Source mới có route và khóa
  ghép nối khớp gói extension; cần người dùng khởi động lại phiên demo cũ.
- Sửa trạng thái UI lấy từ tab đã lưu, tách chưa liên kết/đã liên kết/tab đóng/
  tab không hoạt động. Nút liên kết hiển thị trực tiếp khi cần, không còn giữ câu
  “Liên kết tab Shopee để bắt đầu” sau khi khởi động lại giao diện đã liên kết.
- Lỗi thiếu route hướng dẫn restart backend; lỗi mất job và mất mạng có thông báo
  riêng. Đọc DOM thành công nhưng backend lỗi được báo riêng, không gọi là lỗi tab.
- TypeScript, 9 bài extension và build lại đạt. Không tự dừng tiến trình demo đang chạy.

### Extension desktop và mục tiêu tài khoản trình duyệt — 19/10/2026

- Shopee dùng `ExtensionShell` riêng: header 52px, tab trên, không dock iOS,
  không gọi API dashboard local chưa có adapter Shopee. Dùng chung chat/ảnh/lịch sử.
- Chọn nhãn tài khoản ngoài main/form/bảng bằng click thật; nonce 30 giây,
  kiểm tra extension/tab/frame/document, từ chối replay và thay phiên khi đổi nhãn.
  Nhãn này không phải Shop ID hoặc token API được Shopee xác thực.
- Kiểm tra mục tiêu/trang định kỳ bằng thông điệp chỉ trạng thái, không ghi lại
  storage ảnh/lịch sử mỗi lần kiểm tra; ẩn bản đọc khi nhãn/trang không còn khớp.
- Thay body text bằng JSON các trường/bảng trong allowlist; bỏ cột người mua,
  điện thoại, địa chỉ, giá trị input, tiêu đề trang và query/hash URL. Không chọn
  số liệu trùng nhãn/mơ hồ. JSON được giới hạn bằng bỏ nguyên dòng, không cắt chuỗi.
- Token ngữ cảnh ngẫu nhiên kiểm tra cả đổi query trước khi điền; không submit.
- TypeScript, 11 bài connector/packaging, 11 bài API/chat và fixture DOM đạt.
  UI fixture kiểm tra 320/380/520px, grow/shrink composer, typing, autoscroll,
  lịch sử, hộp kết nối, xóa số liệu khỏi màn hình khi target không khớp; không có
  lỗi JS hay request mạng thật. Hình/kết quả trong `docs/evaluations/extension-panel`.
- UI fixture dùng RPC giả lập có structured clone giống Chrome; chỉ đổi predicate
  origin trong bundle phục vụ test. Gói production trên đĩa không bị nới guard.
- Không dùng được kết nối Browser tích hợp của phiên này; Chrome riêng dùng cho
  QA, không truy cập hồ sơ Chrome thật. Thử nạp extension qua flags trong hồ sơ
  tạm không tạo service worker trên Chrome hiện có, nên chưa xác minh Load unpacked,
  CSP, bộ đọc và form trên Shopee đăng nhập. Thành viên phải Reload extension,
  tải lại tab Shopee, chọn nhãn và kiểm chứng trang thực tế trước thuyết trình.

### Thu thập nhiều trang Shopee và trả lời tồn kho từ Tổng quan — 19/10/2026

- Tự tìm liên kết/menu đang hiện trên trang, dùng tab nền cùng cửa sổ và phân trang
  có xác minh; không hardcode URL portal, không đọc cookie hoặc gọi API riêng Shopee.
- Job có tiến trình, hủy, giới hạn, tách theo connection/nhãn tài khoản; không ghi
  cache lẫn shop, không dùng cache quá 5 phút hay vượt kiểm tra tài khoản live.
- Tính tồn kho bằng code: dedup SKU/ID, xung đột là chưa biết, phân biệt 0 với thiếu,
  mặc định sắp hết là >0 và <=5. AI nhận summary và bằng chứng có giới hạn rõ ràng.
- Câu hỏi tồn kho không phải chờ lượt quét đơn hàng. Schema backend kiểm tra nhãn,
  UUID kết nối, tuổi dữ liệu, URL và quan hệ giữa các bộ đếm trước khi gọi model.
- Test: 17 bài extension/packaging/sync; DOM fixture gồm bảng native/div, SKU,
  liên kết quan sát được, phân trang, không submit và loại PII; UI 320/380/520px,
  tiến trình/dừng, summary, composer, lịch sử, autoscroll; TypeScript và toàn bộ
  backend đạt. Live Gemini dùng 3 SKU giả lập: K1 tồn 3, M1 tồn 0, H1 tồn 10;
  trả lời đúng nhóm sắp hết/hết, không yêu cầu người bán mở mục thủ công.
- Chrome plugin của phiên này không kết nối được; chưa kiểm chứng DOM Shopee thật.
  Reload extension và tab Shopee, khởi động lại backend để nạp schema shop_context.
  Độ phủ toàn shop chỉ được khẳng định sau nghiệm thu trên danh sách thực tế.

### Tách chat khỏi điều hướng trình duyệt — extension 0.2.1, 19/10/2026

- Gửi tin nhắn chỉ đọc dữ liệu còn hạn và trang liên kết hiện tại; không khởi
  chạy đồng bộ, mở tab, điều hướng tab hay chờ quét. Mất dữ liệu, cache hết hạn,
  lượt đọc lỗi và mở lại panel không tự thử lại. Liên kết mới hoặc nút Cập nhật
  mới bắt đầu lượt đồng bộ; nhiều mục dùng chung một tab nền, tự đóng khi xong.
- Tab được người dùng sử dụng hoặc chuyển ra ngoài Shopee được giữ nguyên;
  lượt đồng bộ không tiếp tục điều hướng tab đó. Cache vẫn tách theo tài khoản,
  giữ timestamp thật và không coi dữ liệu quá hạn là số liệu hiện tại.
- Facts gửi model bỏ tài nguyên rỗng, có hướng xử lý theo trạng thái. Kiểm tra
  đầu ra chặn tên trường/null và hướng dẫn tự mở từng mục để lấy dữ liệu thiếu.
  Nếu model phủ nhận dữ liệu thực tế đã cung cấp, trả lỗi thay vì bịa thiếu số liệu.
- QA phát hiện ô nhập web không thu nhỏ ổn định sau khi thay đoạn dài bằng ngắn.
  Đổi sang đo textarea trước khi vẽ, bỏ ảnh hưởng chiều cao mặc định hai dòng;
  giữ cách đo native. Kiểm tra dòng cuối/caret khi nội dung vượt chiều cao tối đa.
- Đạt: 19 bài extension; 31 bài browser backend; toàn bộ backend; 11 bài API/chat;
  TypeScript; build 0.2.1. UI fixture đạt 320/380/520px, nhập dài/ngắn, autoscroll,
  lịch sử, polling lỗi và mở lại panel không retry; chỉ lần bấm Cập nhật gửi sync_now.
- Giao diện kiểm tra bằng Chrome riêng với RPC/dữ liệu giả lập, không dùng tài
  khoản Shopee. Chưa kiểm chứng bộ đọc trên DOM Shopee đăng nhập hoặc đầy đủ tồn
  kho thật; các kiểm thử trên không chứng minh việc đọc toàn shop đã thành công.

### Tích hợp nhánh thach và thay đổi local — 19/10/2026

- Gộp `origin/thach` tại `ceaf09f` với phần đồng bộ trình duyệt và composer local;
  giữ lịch sử commit của thành viên. Nhánh bổ sung tra danh mục theo nhiều từ khóa,
  lọc giá trước phân trang, timeout Gemini nhiều key và ảnh tài khoản trên app.
- Bắt và sửa regression: “Còn hôm nay thì sao?” bị nhận thành tên sản phẩm, làm
  mất kỳ báo cáo. Câu hỏi theo thời gian và đại từ chưa xác định tiếp tục đi qua
  ngữ cảnh hội thoại; truy vấn giá chưa hiểu đầy đủ không vào đường tra nhanh.
- Hỗ trợ khoảng giá “từ… tới…”, phân biệt từ/đến với tên hàng “tủ/đèn”; không áp
  dụng điều kiện giá do classifier tự đặt mà không có bằng chứng từ tin nhắn.
- Thu hẹp cách lấy giá theo tham chiếu “giá của nó là…” để không nhận thông số
  camera/màn hình 4K thành giá 4.000đ. Giữ phân biệt giá vốn, phí và giá bán.
- Đạt: **499 backend tests** (JUnit: 0 failed/errors/skipped), **30 store tests**
  gồm bootstrap 6, commerce 18, reviews 6; commerce kiểm tra 181 liên kết người bán.
  Store scripts chạy trong các tiến trình riêng với SQLite tạm, tránh chia sẻ
  module Flask giữa nhóm test. Không sửa database shop hoặc dùng model bên ngoài.
- Đạt TypeScript, 11 test API/chat, 19 test extension, DOM fixture và panel fixture
  320/380/520px; xuất web/extension (1 bundle, 22 tài nguyên) và iOS/Hermes thành công.
  Kiểm tra mới được bổ sung vào CI cho extension và reviews của marketplace.
- Giới hạn nghiệm thu giữ nguyên: fixture không xác minh Shopee đăng nhập thật;
  xuất iOS bundle không thay thế kiểm thử trên thiết bị hoặc tạo bản IPA.
