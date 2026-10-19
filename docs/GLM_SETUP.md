# GLM Free — cài đặt và kiểm tra cho nhóm

SellerPilot chuyển từ Muse sang **`opencode/glm-5.3-flash-free`** ngày 18/10/2026.
GLM chạy qua OpenCode trên máy backend, không phải model tải xuống HDD. Không cần
cài Qwen/Ollama khi chọn provider này. Điện thoại chỉ gọi API SellerPilot.

## 1. Chuẩn bị runtime

Cài Node và hai môi trường Python theo [README](../README.md). Kiểm tra:

```sh
opencode --version
```

Backend hiện dùng giao thức server **OpenCode 1.x**, đã kiểm chứng **1.18.30**.
Nếu máy đã có bản này, giữ nguyên. Nếu chưa có:

```sh
npm install -g opencode-ai@1.18.30
opencode --version
```

Nếu đây là máy mới hoặc gặp lỗi quyền free, mở OpenCode chính thức và thử một
tin nhắn với đúng model:

```sh
opencode -m opencode/glm-5.3-flash-free
```

Hoàn thành đăng nhập theo giao diện chính thức nếu được yêu cầu; không chọn bản
GLM tính phí hoặc thêm khóa cá nhân vào repo. Sau khi thử xong có thể đóng TUI;
backend sẽ mở server riêng khi chạy demo.

`@opencode/cli` là dòng v2 với API khác; không thay thế runtime 1.x của backend này.
Nếu muốn giữ v2 cho việc lập trình, cài bản 1.x vào vị trí riêng và đặt
`OPENCODE_BINARY` thành đường dẫn đầy đủ tới binary 1.x trong `.env`.
Không đổi endpoint, header nhận diện hay quyền công cụ để vượt giới hạn free.

Nguồn chính thức: [CLI v1](https://opencode.ai/docs/cli/),
[CLI v2 và API mới](https://opencode.ai/v2/docs/cli/).

## 2. Cấu hình model

Máy mới: copy `.env.example` thành `.env` ở root theo README. Máy đã cấu hình:
**sửa các khóa dưới đây, không copy đè toàn bộ `.env`**, để giữ đường dẫn dữ liệu.

```dotenv
AI_PROVIDER=opencode
OPENCODE_MODEL=glm-5.3-flash-free
OPENCODE_BINARY=opencode
OPENCODE_GENERATION_TIMEOUT_SECONDS=90
```

`OPENCODE_MODEL` không có tiền tố `opencode/`. Backend đọc root `.env`, sau đó
`backend/.env`; biến trong terminal có ưu tiên cao nhất. Kiểm tra cả ba nơi nếu
vẫn xuất hiện Muse. Khởi động lại backend sau khi sửa; lịch sử và bản nháp cũ được giữ.

Code từ chối model trả phí `glm-5.3-flash` và model Muse cũ. Không đặt API key
vào frontend hoặc Git. Không tự chuyển sang model trả phí khi hết hạn mức.

## 3. Kiểm tra trước buổi demo

Tại root, chạy:

```sh
npm run ai:check
```

Hoặc từ `backend`:

```sh
.venv/bin/python -m app.scripts.check_ai
```

Script kiểm tra lần lượt:

1. Binary 1.x và server riêng có mật khẩu ngẫu nhiên.
2. Model GLM active, giá input/output/cache đều được khai báo bằng 0, có khả năng nhận ảnh.
3. Phân loại câu đổi giá giả lập, đúng SKU và số tiền.
4. Hội thoại bằng tiếng Việt.
5. Trích giá vốn, đóng gói, phí sàn và giá bán đúng ý nghĩa.
6. Nhận diện một ảnh bàn phím tự vẽ, soạn tiêu đề/mô tả, chọn ngành và trích giá/tồn.

Mỗi lượt gọi có deadline 90 giây mặc định. Script gọi model qua Internet nhưng
**không mở database shop, ảnh upload hoặc lịch sử thật**; không gọi công cụ bán hàng.
Server/session thử nghiệm tự dọn sau khi kết thúc. Exit code 0 nghĩa là các kiểm tra
đã qua; exit code 1 nghĩa là cần xử lý trước khi demo. Chất lượng nội dung vẫn cần
chủ shop kiểm tra trước khi xác nhận đăng.

`GET /api/v1/health` kiểm tra metadata, không tạo một lượt sinh nội dung thật:
`model_available=true` không bảo đảm hạn mức hoặc mọi câu hỏi sẽ thành công.
Vì vậy nên chạy `ai:check` trên **từng máy chạy backend**, không chỉ nhìn health.
Nếu một lượt sinh bị gateway từ chối quyền free, health chuyển sang `degraded`,
`model_available=false` dù runtime OpenCode vẫn chạy. Trạng thái này được giữ
đến khi một lượt sinh thật thành công trong tiến trình backend đó.

## 4. Chạy app và web

```sh
npm run demo
```

Một terminal chạy UTE MALL, API và Expo. Android/iPhone dùng Expo Go và cùng Wi-Fi
với máy backend; quét QR. Ctrl+C dừng cả cụm. Không cần mở phiên chat OpenCode riêng.

## 5. Những chức năng được giữ

- Chat ngữ cảnh nhiều lượt, báo cáo doanh số và tồn kho từ dữ liệu shop, tư vấn việc ưu tiên.
- Cá nhân hóa theo thông tin chủ shop đã xác nhận; tính lời, hòa vốn và giảm giá bằng Decimal.
- Chọn 1–6 ảnh rồi bấm Gửi; ảnh không tự gửi ngay khi chọn.
- Hiểu tên, mô tả, giá và tồn trong một tin; chỉ hỏi phần thiếu. Không lấy câu lệnh làm tiêu đề.
- GLM tự soạn tên/mô tả từ dữ kiện và ảnh; không suy giá bán/tồn từ ảnh.
- Bản nháp phải được người bán duyệt; xác nhận mới đăng và đồng bộ sản phẩm/ảnh vào UTE MALL.
- Đổi giá cần proposal/xác nhận; chống gửi trùng, hủy tác vụ, ghim/xóa lịch sử vẫn giữ nguyên.

JSON hợp lệ chưa đủ để ghi shop: backend tiếp tục kiểm tra bằng chứng giá/tồn,
ID ngành, trạng thái bản nháp, shop sở hữu và điều kiện đồng thời. GLM không được
phê duyệt hay thực thi công cụ OpenCode. Yêu cầu cấp quyền bất ngờ sẽ bị dừng và dọn session.

Cấu hình agent tránh `steps=1`: OpenCode v1 có thể chèn lời nhắc đã hết bước
ngay ở lần sinh nội dung đầu tiên. Giới hạn hiện tại là 2; trả lời bình thường kết
thúc sau một lần sinh, còn yêu cầu công cụ vẫn bị chặn. Backend cũng không hiển thị
lời nhắc nội bộ về hết bước. Xem [báo cáo kỹ thuật OpenCode](https://github.com/anomalyco/opencode/issues/30866).

## 6. Xử lý lỗi

| Hiện tượng | Cách xử lý |
|---|---|
| Cấu hình vẫn yêu cầu Muse | Sửa `OPENCODE_MODEL` ở root `.env`, `backend/.env` và terminal; restart backend. |
| Binary là 2.x | Chỉ định bản 1.x bằng `OPENCODE_BINARY`; không dùng API v2 với adapter v1. |
| `free_model_unavailable` | Kiểm tra `opencode models opencode --refresh --verbose`. Model phải active, đủ giá 0. Không đổi sang ID trả phí. |
| `free_tier_restricted` / 403 | Đọc mục chẩn đoán bên dưới. Model có metadata giá 0 không bảo đảm backend có quyền gọi. Không đổi header/client để vượt giới hạn. |
| `provider_rate_limited` / 429 | Xem hạn mức trong [OpenCode Console](https://opencode.ai/console), chờ rồi thử lại; không tự gọi lặp vô hạn. |
| `provider_timeout` | Kiểm tra mạng và tải dịch vụ; lượt này chưa có kết quả AI hợp lệ. |
| `invalid_response` | Schema/câu trả lời không đạt sau lần sửa có giới hạn; không bỏ validation để cho qua. |
| Chat hoạt động nhưng ảnh không hiểu | Chạy `ai:check`, kiểm tra khả năng ảnh và đúng model; bản Qwen văn bản không thay thế được GLM đọc ảnh. |

### Chẩn đoán quyền free ngày 18/10/2026

Sau các lượt kiểm chứng thành công ban đầu, `npm run ai:check` đã tái hiện lỗi
trên managed adapter hiện có. Gateway trả HTTP 403 với đúng thông báo:

> OpenCode's free tier can only be used from within OpenCode.

Metadata vẫn báo GLM active, input/output/cache giá 0 và có hỗ trợ ảnh. Đây là
**từ chối quyền sử dụng trên đường gọi này**, không đủ bằng chứng kết luận model
đã hết miễn phí, người dùng hết quota, sai Wi-Fi hoặc prompt sai. HTTP 200 của
`POST /chat` chỉ có nghĩa API đã trả response; xem `mode=fallback` và
`fallback_reason=free_tier_restricted` để nhận biết chưa có câu trả lời model.

Backend dừng gọi lại gateway trong 60 giây sau lỗi quyền free. Trong thời gian này
các agent khác dùng cùng provider cũng nhận lỗi rõ ràng, không gửi lại ảnh/prompt.
Hết 60 giây, **yêu cầu chat tiếp theo** mới có thể thử lại; không có tác vụ tự gọi
định kỳ. Thời gian trôi qua hay metadata không tự chuyển health về sẵn sàng.
Restart backend tạo phiên trạng thái mới, nhưng không mở khóa quyền phía gateway.

Để tiếp tục AI cần quyền sử dụng chính thức cho tích hợp này, hoặc chuyển có chủ
đích sang provider/API cho phép backend hay Ollama local. Không tự chuyển model
tính phí, thêm khóa, đổi danh tính client hoặc bỏ validation. Với lỗi listing,
ảnh và thông tin bản nháp được giữ; trả thông báo chưa đọc/viết được ở lượt đó,
không ép người dùng trả lời lại vì tưởng AI đã hiểu ảnh.

Các kết quả thành công ở mục 8 là bản ghi của lần kiểm chứng trước lỗi quyền này,
không phải cam kết gateway luôn chấp nhận các yêu cầu về sau.

Đã kiểm tra thêm chín model miễn phí khác trong CLI; tất cả trả cùng lỗi quyền
trên đường gọi hiện tại. Xem [bảng kết quả và phạm vi thử](OPENCODE_FREE_MODEL_CHECK.md).

## 7. Giới hạn dịch vụ

Theo [bảng model OpenCode](https://opencode.ai/v2/docs/console/models/), GLM-5.3-Flash
Free đang miễn phí có thời hạn. Nhà cung cấp công bố zero-retention và không dùng
dữ liệu để huấn luyện cho model này. Điều khoản/hạn mức có thể thay đổi; kiểm tra lại
trước buổi demo. Giữ một worker API như kiến trúc hiện tại; triển khai nhiều chủ shop
qua Internet vẫn cần xác thực/phân quyền riêng.

Kết quả Muse trong các tài liệu kiểm chứng cũ được giữ như bản ghi lịch sử,
không dùng để chứng nhận chất lượng GLM.

## 8. Kết quả kiểm chứng ngày 18/10/2026

Đã chạy OpenCode 1.18.30 và GLM Free thật qua adapter backend, không gọi trực tiếp
gateway của model, không giả mạo header và không chuyển sang model tính phí.

| Ca thử | Kết quả |
|---|---|
| `npm run ai:check` | Qua cả bốn agent, gồm đọc ảnh tự vẽ và schema nội dung |
| Doanh số qua API với shop tạm | Đúng 2 đơn, giá trị 1.600.000đ theo dữ liệu tạo trước |
| Giá vốn 500k, đóng gói 20k, phí 10%, bán 900k | Backend tính lời 290.000đ; giảm giá 10% còn lời 209.000đ |
| Đổi giá qua chat | Proposal pending, chưa đổi giá; reject giữ nguyên catalog |
| Hai ảnh và một tin đủ tên/mô tả/990k/8 cái | Ready ngay; giữ mô tả, đúng ngành và không dùng câu lệnh làm tên |
| Xác nhận đăng hai lần | Một sản phẩm active, một gallery đồng bộ, không tạo trùng |
| Ghim rồi xóa chat đã đăng | Xóa lịch sử; ảnh của sản phẩm đã đăng vẫn còn |
| Chỉ ảnh, nhờ AI tự viết | Tự soạn tên/mô tả, chọn ngành; chỉ hỏi giá và tồn kho còn thiếu |
| Hủy bản nháp ảnh chưa đăng | Dọn đúng ảnh của bản nháp đó, giữ ảnh sản phẩm đã đăng |
| Trợ lý cá nhân hóa, 4 lượt | Nhớ khách sinh viên và mục tiêu bền vững; nối tiếp tính lời/giảm giá; chat mới giữ sở thích nhưng không mang giá giả định cũ |
| Backend tự động | 229 test qua, dùng database tạm |
| Frontend | TypeScript và 9 test transport/lịch sử tin nhắn qua |

Trong thử nghiệm, có phản hồi JSON cần yêu cầu sửa định dạng và có câu tư vấn
bị kiểm tra số tiền chặn trước khi viết lại. Các kiểm tra này được giữ lại;
không xem việc model trả lời được là bảo đảm mọi câu trả lời đều chính xác.
Toàn bộ thao tác ghi để kiểm thử nằm trong database/ảnh giả lập ở thư mục tạm,
không đăng hoặc đổi giá sản phẩm của shop đang sử dụng.
