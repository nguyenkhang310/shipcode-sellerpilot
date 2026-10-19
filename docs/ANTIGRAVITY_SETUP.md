# SellerPilot với Antigravity CLI

## Chuẩn bị

Đã kiểm tra CLI **1.1.22** trên macOS Apple Silicon. Cài từ
[nguồn chính thức](https://www.antigravity.google/docs/cli/install/), rồi chạy
`agy` và đăng nhập tài khoản của bạn. Cần Git trong PATH để tạo workspace tạm.
Máy backend cần Internet; không dùng model trên HDD.

```sh
agy --version
agy models
```

Trong CLI, mở `/config` và đối chiếu:

- `Use G1 Credits`: **off**. Provider từ chối khi bật; không tự dùng credit bù quota.
- `Tool Permission`: **request-review**.
- `Non-Workspace Access`: **off**.
- Không cấu hình quyền allow rộng hoặc provider API key cho phiên này.

Adapter hiện yêu cầu permissions ở trạng thái mặc định, không có cấu hình tùy
chỉnh khác. Nếu không tương thích, trả `provider_rejected` ở bước `cli_policy`;
không tự sửa cấu hình CLI toàn máy. CLI dùng phiên đăng nhập chính thức, không
trích token hay dựng proxy đến gateway. Hạn mức thuộc tài khoản đã đăng nhập.

## Cấu hình repo

Máy mới copy `.env.example` theo README. Máy đang có `.env`: chỉ sửa/thêm các khóa
sau, giữ nguyên đường dẫn database và thiết lập của store:

```dotenv
AI_PROVIDER=antigravity
ANTIGRAVITY_BINARY=agy
ANTIGRAVITY_MODEL=gemini-3.8-flash-low
ANTIGRAVITY_GENERATION_TIMEOUT_SECONDS=120
```

Có thể dùng đường dẫn đầy đủ cho `ANTIGRAVITY_BINARY` nếu IDE không nhận PATH.
Provider chỉ chấp nhận model Gemini 3.8 Flash với hậu tố `low`, `medium` hoặc `high`,
không tự đổi sang model khác. Low là cấu hình demo hiện tại; có thể chọn Medium khi cần đối chiếu chất lượng. Không cần tạo Gemini
API key khi dùng đường đăng nhập CLI này. Biến shell ưu tiên hơn root `.env`,
sau đó kiểm tra `backend/.env` nếu cấu hình cũ vẫn được dùng.

```sh
npm run ai:check
npm run demo
```

`ai:check` gọi model thật với dữ liệu và ảnh tự vẽ: phân loại đổi giá, chat tiếng
Việt, trích giá vốn/phí/giá bán, rồi nhận diện bàn phím và soạn nội dung. Không đọc
shop, ảnh upload hoặc lịch sử đang sử dụng. Exit code 0 là qua toàn bộ ca thử.

`demo` chạy web, backend và Expo như trước. Điện thoại gọi API SellerPilot, không
cần cài CLI. Khi cả nhóm dùng chung máy backend, chỉ máy đó cần phiên đăng nhập.
Nếu mỗi thành viên tự chạy backend, họ đăng nhập tài khoản riêng; không chia sẻ
file đăng nhập hoặc token qua Git. Ctrl+C dừng các dịch vụ.

## Ảnh được xử lý như thế nào

1. Ảnh app đã upload vẫn nằm trong kho ảnh/bản nháp của SellerPilot.
2. Adapter nhận tối đa 6 data URL JPG/PNG/WEBP, kiểm tra encoding, loại file và giới hạn 8 MB/ảnh.
3. Mỗi lượt gọi tạo workspace Git tạm riêng; chỉ chép những ảnh của lượt đó vào.
4. Agent chính `shipcode-sellerpilot` có `view_file` và `finish`, không có công cụ ghi shop.
   Không tạo subagent. Backend theo dõi NDJSON, chỉ chấp nhận xem đúng các đường dẫn ảnh đã cấp.
5. **Phải có sự kiện xem xong từng ảnh** mới nhận kết quả; bỏ sót một ảnh thì trả lỗi,
   không lặng lẽ bỏ ảnh thứ 4–6. Xem ngoài danh sách hoặc dùng công cụ khác bị dừng.
6. CLI `SUCCESS` chưa đủ: backend dùng `structured_output`, kiểm tra Pydantic,
   bằng chứng tiền/tồn, ngành hàng và các tuyên bố sản phẩm theo luồng hiện có.
7. Kết thúc, lỗi, timeout hoặc hủy đều dừng tiến trình do adapter tạo và dọn
   workspace/ảnh tạm. Ảnh/bản nháp gốc không bị xóa vì model lỗi.

Không đổi đường gửi ảnh thành block image của stdin: giao thức CLI hiện nhận
block text. Ảnh đi qua `view_file` chính thức. Không đặt nội dung chủ shop trong
shell command hoặc argv; truyền JSON qua stdin. Mỗi lượt là một hội thoại CLI
mới, ngữ cảnh được backend truyền có giới hạn để không lẫn các cuộc chat.

CLI có thể lưu lịch sử/chẩn đoán vào dữ liệu riêng của Antigravity trên máy.
Việc dọn workspace tạm không phải xóa lịch sử của CLI hay dữ liệu phía dịch vụ.
Không commit log, ảnh, token hoặc file cấu hình cá nhân.

## Các giới hạn cần biết

- CLI có thời gian khởi động và có thể cần nhiều bước để xem nhiều ảnh; không
  cam kết tốc độ như API thuần hoặc câu trả lời tức thời.
- Health kiểm tra cấu hình/model, không dùng quota để sinh câu trả lời. Sau lỗi
  sinh, health báo degraded đến khi một lượt thật thành công hoặc khởi tạo lại.
- Quota hết: báo `provider_rate_limited`; không tự bật credit hay chuyển model.
- `tool_not_allowed`: model yêu cầu công cụ hoặc đường dẫn ngoài phạm vi. Lượt
  đó bị dừng, không phê duyệt tự động. Kiểm tra trước khi gửi lại.
- Tài liệu và test không cam kết quyền phục vụ công khai nhiều người bằng một
  subscription. Phạm vi hiện tại là demo nhóm trên máy backend của chủ tài khoản.
- macOS đã thử thực tế; Windows/Linux cần chạy `ai:check` trên chính máy đó.

Nguồn: [headless/structured output](https://www.antigravity.google/docs/cli/headless/),
[agent configuration](https://www.antigravity.google/docs/cli/commands/agents/),
[credits](https://www.antigravity.google/docs/cli/credits/),
[quota](https://www.antigravity.google/docs/plans).

## Kết quả kiểm chứng ngày 18/10/2026

Các lượt thử dùng phiên đăng nhập chính thức trên máy backend, Gemini 3.8 Flash
Medium và dữ liệu/ảnh tự vẽ. Không bật credit, không ghi shop đang sử dụng.

| Ca thử | Kết quả |
|---|---|
| Hai ảnh bàn phím có khung màu khác nhau | Nhận đúng đồ vật, phân biệt khung đen/đỏ; có sự kiện đọc từng file |
| `ai:check` | Qua phân loại đổi giá, hội thoại, trích chi phí và soạn sản phẩm từ ảnh |
| API upload 6 ảnh / 6 màu | Đọc đủ 6 ảnh, caption nhận đúng đen/đỏ/xanh dương/xanh lá/vàng/tím |
| Giá `5 xị`, chưa có tồn | 500.000đ; chỉ hỏi số lượng còn thiếu, tự viết tên và mô tả |
| Nhắn tiếp `Kho còn 12 chiếc nhé` | Giữ tên/mô tả/giá và đủ 6 ảnh, bản nháp ready với tồn 12 |
| Xác nhận đăng trong shop tạm | Sản phẩm và gallery đủ 6 ảnh; API phục vụ ảnh trả 200 |
| Xác nhận đăng lại | Cùng product ID, không tạo trùng |
| Backend | 298 kiểm thử qua, gồm lỗi quyền/credit, bỏ sót ảnh, sai model/tool/SKU, timeout và hủy |
| Frontend | TypeScript và 9 kiểm thử transport/lịch sử tin nhắn qua |

Đã gặp trường hợp CLI báo `SUCCESS` nhưng JSON chưa đúng và tự lặp yêu cầu finish
khi agent không được cấp `finish`. Cấu hình hiện tại cấp đúng `finish`, đọc
`structured_output` và vẫn kiểm tra schema độc lập. Không chấp nhận SUCCESS đơn
thuần hoặc giả định model luôn trả đúng. Đây là các ca đã thử, không bảo đảm mọi
ảnh/sản phẩm/cách diễn đạt đều được nhận diện chính xác.

## Tối ưu độ trễ cho bản demo

Cấu hình mặc định hiện tại là `gemini-3.8-flash-low`. Backend dùng đúng model
được chọn; không tự chuyển sang dịch vụ khác khi lỗi hoặc hết quota.

Các thay đổi trong đường xử lý:

- Chào hỏi ngắn và câu đọc số liệu rõ ràng như `Doanh thu hôm nay bao nhiêu?`,
  `Xem tồn kho của shop`, `SKU A001 còn bao nhiêu?` lấy câu trả lời từ backend
  và dữ liệu hiện tại, không chờ model viết lại. Response ghi đúng
  `provider=deterministic_parser`, `model=null`; đây không phải câu do model sinh.
- Câu dài, yêu cầu phân tích, giả định hoặc chỉ dẫn bổ sung vẫn qua model.
  Không cache câu trả lời/số liệu của shop.
- Tư vấn thông thường gộp đọc hiểu và câu trả lời thành một lượt có schema.
  Khi có tính giá/lợi nhuận, cập nhật bộ nhớ hay cần tìm sản phẩm, backend vẫn
  kiểm tra bằng chứng, tính bằng Decimal và đọc dữ liệu trước khi viết câu trả lời cuối.
- Cache kết quả kiểm tra cấu hình CLI tối đa 60 giây; thay đổi file cấu hình
  hoặc binary làm mất cache. Không bật credit, mở rộng quyền hay bỏ kiểm tra ảnh.
- Log `Antigravity timing` có thời gian chờ, kiểm tra cấu hình, sinh câu trả lời
  và tổng thời gian, không ghi prompt/ảnh/thông tin đăng nhập.

Đo trên máy phát triển ngày 18/10/2026 với dữ liệu giả lập (mỗi ca một lượt,
không phải benchmark trung vị):

| Ca | Thời gian quan sát |
|---|---:|
| Medium, câu chào, đường gọi cũ | 57,42 giây |
| Low, câu chào qua schema, chưa cache cấu hình | 67,48 giây |
| Low, tư vấn hai việc ưu tiên, đường gộp một lượt và cache cấu hình | 41,79 giây |

**Low không bảo đảm nhanh hơn Medium ở mọi lượt.** Chọn model đơn thuần chưa
loại bỏ độ trễ của gateway/CLI. Đường gộp giảm số lần gọi cho tư vấn; câu đọc
số liệu chính xác tránh lượt model không cần thiết. Không cam kết chat suy luận
chỉ mất 1–2 giây qua CLI. Nếu cần mức đó ổn định cho sản phẩm, cần đo thêm với
API suy luận trực tiếp và quyền truy cập API phù hợp; gói CLI Pro không tự cấp
API key cho backend.

Sau khi đổi `.env`/code backend, Ctrl+C tiến trình `demo` cũ rồi chạy lại từ gốc:

```sh
npm run demo
```

Có thể kiểm tra cấu hình và chức năng bằng `npm run ai:check` trước buổi demo.

Kiểm chứng sau tối ưu: **316 kiểm thử backend qua**, TypeScript và **9 kiểm thử
frontend qua**. Đã gọi Flash Low thật cho chat, phân loại, trích chi phí và ảnh;
đã chạy lại API trên shop tạm với **6 ảnh**, giá `5 xị`, hỏi riêng tồn kho còn
thiếu, bổ sung 12 chiếc và xác nhận đăng đủ gallery. Gửi xác nhận lần hai giữ
nguyên product ID. Các kiểm tra này không sửa database shop đang dùng.
