# Gemini API cho SellerPilot

Backend gọi Gemini trực tiếp qua HTTPS, không khởi động CLI cho từng tin nhắn.
Cấu hình mặc định là `gemini-3.5-flash-lite`, hỗ trợ văn bản, ảnh và đầu ra có schema.

## Thử một key trước

1. Tạo key trong [Google AI Studio](https://aistudio.google.com/apikey).
2. Mở `.env` ở **thư mục gốc**, cùng cấp `App.tsx`. Nếu chưa có file, copy
   `.env.example` một lần; không ghi đè cấu hình đang dùng.
3. Điền key thật sau dấu `=`, không thêm dấu `< >`:

```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
```

Chạy ở thư mục gốc sau khi đã cài dependencies theo README:

```sh
npm run ai:check
```

Lệnh này gọi model thật bằng dữ liệu thử và ảnh tự vẽ: kiểm tra hiểu lệnh,
hội thoại, trích chi phí và soạn sản phẩm từ ảnh. Không đọc hay sửa shop thật.
Health chỉ kiểm tra khả năng truy cập metadata; chưa chứng minh sinh nội dung được.

Sau khi kiểm tra thành công, dừng phiên demo cũ bằng Ctrl+C rồi chạy:

```sh
npm run demo
```

Thay `.env` cần khởi động lại backend. Backend đọc `.env` gốc rồi `backend/.env`;
nếu cùng tên biến, file sau ghi đè file trước; biến môi trường shell được ưu tiên.
Không đặt key trong frontend, biến `EXPO_PUBLIC_*`, chat, ảnh chụp hoặc Git.

## Tối đa ba key

Điền thêm khi cần, kèm **project ID thật** tương ứng trong AI Studio:

```dotenv
GEMINI_PROJECT_ID=
GEMINI_API_KEY_2=
GEMINI_PROJECT_ID_2=
GEMINI_API_KEY_3=
GEMINI_PROJECT_ID_3=
```

Hạn mức Gemini tính theo project, không theo số key hay số tài khoản Google.
Các key cùng project chia sẻ bộ đếm và thời gian chờ. Key thiếu project ID cùng
vào một nhóm chưa xác minh; backend không mặc định chúng có quota độc lập.
Key trùng được loại bỏ; khai báo cùng key với hai project khác nhau bị từ chối.

Backend luân phiên key đang khả dụng. Khi nhận 429, cả nhóm project nghỉ theo
`Retry-After` (mặc định 60 giây nếu dịch vụ không cung cấp thời gian), rồi mới được
dùng lại. Lỗi xác thực 401/403 vô hiệu key đó trong tiến trình hiện tại; sửa cấu
hình rồi khởi động lại. Lỗi nội dung/định dạng yêu cầu không được giải quyết bằng
cách đổi key. Không có vòng lặp gọi liên tục khi hết quota.

## Groq dự phòng, tùy chọn

Tạo key tại [Groq Console](https://console.groq.com/), kiểm tra quota gói Free
của tài khoản rồi cấu hình:

```dotenv
GROQ_FALLBACK_ENABLED=true
GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3.8-27b
```

Groq được gọi khi Gemini gặp lỗi tạm thời như 429, mất kết nối hoặc lỗi dịch vụ.
Không dùng Groq để che lỗi thiếu Gemini key hay cấu hình Gemini sai.
Thời gian gọi dự phòng nằm trong deadline chung, không cộng thêm một lượt chờ dài.

| Model Groq được hỗ trợ | Đầu vào | Giới hạn tích hợp |
| --- | --- | --- |
| `qwen/qwen3.8-27b` | Văn bản và ảnh | Tối đa 3 ảnh; model preview |
| `openai/gpt-oss-120b` | Văn bản | Không nhận ảnh |

Gemini vẫn nhận tối đa 6 ảnh. Nếu gửi 4–6 ảnh, backend **không bỏ bớt ảnh** để
chuyển sang Groq. Khi Gemini không khả dụng, app báo giới hạn và giữ bản nháp.
Llama 4 Scout đã ngừng phục vụ trên Groq từ 17/07/2026, không dùng ID model cũ.

## Ngôn ngữ và dữ liệu

Câu hỏi số liệu rõ ràng được đọc trực tiếp từ database và diễn đạt bằng bộ câu
tiếng Việt thống nhất. Câu tư vấn hoặc yêu cầu phức tạp dùng model với cùng quy
tắc giọng trả lời. Bộ nhận diện câu trực tiếp là parser ngôn ngữ có quy tắc,
không phải mô hình NLP được huấn luyện riêng. Chất lượng tư vấn vẫn phụ thuộc model.

Các số tiền, SKU và tồn kho tiếp tục qua kiểm tra backend; phép tính chi phí dùng
Decimal. AI không tự đoán giá bán/tồn kho từ ảnh. Đăng sản phẩm và sửa giá vẫn cần
xác nhận. Chuỗi JSON `{"answer": ...}` bị bọc nhầm được giải mã trước khi hiển thị;
lịch sử cũ được làm sạch khi đọc mà không sửa nhật ký gốc.

Audit ghi provider/model thực sự tạo câu trả lời, kể cả khi chuyển sang Groq.
Không ghi key hoặc prompt đầy đủ vào log chẩn đoán provider.

Lời chào/cảm ơn được xử lý trực tiếp, kể cả khi đang soạn sản phẩm; bản nháp và
yêu cầu sửa đang chờ vẫn được giữ. Câu “có kết nối được không?” đi luồng hội thoại,
không bị nhận nhầm thành tìm hàng. Có thể bắt đầu đăng sản phẩm bằng chữ rồi gửi
ảnh sau, không bắt buộc chọn ảnh ngay khi gửi câu lệnh.

Phản hồi model rỗng/bị cắt có một lần sửa trong cùng giới hạn thời gian. Nếu vẫn
không hợp lệ, backend giữ dữ kiện đã xác nhận và trả phương án tiếp tục rõ ràng;
không hiển thị bong bóng rỗng hoặc dùng phần JSON đang dở. Lỗi chặn nội dung/công
cụ không nằm trong nhóm thử sửa này. Tải ảnh bị gián đoạn giữ ảnh để gửi lại;
phản hồi bị mất nhưng server đã xử lý được khôi phục theo ID cũ.

Khi soạn hàng, có thể gửi bổ sung ảnh nhiều lần tới tổng 6 ảnh. “Để sau” giữ
nguyên nháp và ảnh để tiếp tục; hủy rõ ràng mới xóa ảnh chưa đăng. Đang chờ AI
thì hoàn tất/dừng phản hồi trước khi đăng hoặc đổi ảnh, để thao tác duyệt áp
đúng dữ liệu đã xem. Đăng/sửa thành công làm mới tab Sản phẩm độc lập với API
tổng quan; danh sách trong app ưu tiên sản phẩm mới nhất.

## Hạn mức và kiểm thử

Free Tier không có nghĩa là không giới hạn. Xem quota trực tiếp trong project:
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[Groq rate limits](https://console.groq.com/docs/rate-limits).
Không mặc định mỗi key có 1.500 lượt/ngày hay ba key làm quota tăng gấp ba.

Ảnh AI Studio của nhóm ngày 19/10/2026 hiển thị 3.5 Flash-Lite 15 RPM,
3.8 Flash 5 RPM, 2.5 Pro 0 RPM. Đồ thị 500 RPD đang chọn **3.1 Flash-Lite**;
không lấy con số đó áp cho mọi model. Quota có thể thay đổi theo project.

Test tự động dùng HTTP giả lập để kiểm tra key pool, 429, xác thực, timeout,
schema, ảnh, nguồn trả lời và luồng đăng có xác nhận. Chúng không chứng minh quota,
độ trễ hay chất lượng model thật. Chỉ `npm run ai:check` với key hợp lệ mới kiểm
tra kết nối thật trên máy của thành viên.

Kiểm chứng local ngày 19/10/2026: `npm run ai:check` với Gemini 3.5 Flash-Lite
đã qua cả bốn ca thật, gồm đọc ảnh bàn phím tự vẽ, trong tổng 7,3 giây.
Đây là một lần đo nhiều yêu cầu, không phải cam kết độ trễ mỗi tin nhắn.
Kiểm tra tiếp cùng ngày: cả ba key Gemini riêng lẻ đều trích đúng `5 xị = 500.000đ`;
pool thật luân phiên slot 1 → 2 → 3. Chưa khai báo project ID nên chưa xác nhận
ba key có quota độc lập; các key hiện vẫn chia sẻ nhóm giới hạn bảo thủ.

Groq Qwen 3.8 đã thử thật với chat và ảnh bàn phím sau lỗi Gemini 429 **được tiêm
giả lập**, không cố dùng cạn quota Gemini để thử. Ban đầu best-effort schema bỏ
mô tả/ngành hàng; chuyển sang strict schema và reasoning low cho tác vụ có cấu trúc
đã trả đủ tên, mô tả, ngành hàng, giá và tồn. Plain chat vẫn dùng instruct để giảm
độ trễ. Bộ chuyển schema giữ nullable, đóng object và yêu cầu đủ trường trên bản
copy; validation nghiệp vụ phía backend không bị bỏ qua.
Nguồn: [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs).

Một lượt đọc ảnh Groq sau sửa mất 3,17 giây; đây là phép thử ảnh tự vẽ, không phải
cam kết chất lượng caption mọi ảnh thật. Groq đã trả 429 khi thử dồn nhiều lượt,
vì vậy dự phòng cũng chịu hạn mức riêng và không bảo đảm luôn khả dụng.

Nguồn cấu hình: [Gemini models](https://ai.google.dev/gemini-api/docs/models),
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[GenerateContent](https://ai.google.dev/api/generate-content),
[Groq models](https://console.groq.com/docs/models),
[Groq deprecations](https://console.groq.com/docs/deprecations).


## Chẩn đoán timeout (cập nhật 21/10/2026)

Với `GEMINI_GENERATION_TIMEOUT_SECONDS=60` và Groq đang khả dụng, backend dành khoảng 40 giây
cho Gemini và tối đa 20 giây còn lại cho Groq. Trước đây Gemini bị cắt cứng ở 15
giây, dù deadline chung còn dư. Khi Groq đang cooldown do 429 hoặc không nhận đủ
số ảnh, Gemini dùng toàn bộ deadline; không chuyển sang một backup đã biết hết quota.
Connect/pool tối đa 5 giây, write tối đa 10 giây, luôn nằm trong deadline chung.
Không replay một request Gemini chậm qua tất cả các key.

60 giây là ngân sách sinh nội dung **chung cho một lượt chat**, gồm phân tích ý
định, trích dữ kiện, soạn câu trả lời và backup nếu có; không nhân thành 60 giây
cho từng bước. Thời gian chờ khóa xử lý/database và truyền mạng tới điện thoại
không nằm trong ngân sách này. Log `Chat timing` tách `queue_ms` và `processing_ms`;
log `AI generation timing` ghi task, provider/model thực sự chạy và ngân sách còn lại.

Các câu đọc số liệu đơn giản được nhận diện bằng quy tắc tiếng Việt có/không dấu,
ví dụ “nay shop sao rồi”, “hôm nay chốt được mấy đơn”, “sản phẩm nào gần hết hàng”,
“SKU SEED-PHONE còn mấy cái”. Chúng đọc dữ liệu đã xác thực và trả lời trực tiếp,
không gọi model. Câu tư vấn, so sánh phức tạp và thay đổi dữ liệu vẫn đi qua luồng
AI/xác nhận tương ứng. Đây là NLP theo quy tắc, không phải một model tiếng Việt mới.

Với câu tính lời đơn giản, AI vẫn trích chi phí/phí/giá bán rồi backend kiểm tra
bằng chứng và tính bằng Decimal. Sau đó dùng câu trả lời số liệu chuẩn, bỏ lượt
gọi AI chỉ để diễn đạt lại, tránh AI sửa sai kết quả tính.

Log phân biệt `api_connect_timeout`, `api_read_timeout`, `api_write_timeout`,
`api_pool_timeout` và deadline chung; log fallback có stage và elapsed_ms, không có
key/prompt. `npm run ai:check` cũng giải thích lỗi quota riêng với lỗi thời gian.
Metadata đọc được không đồng nghĩa sinh nội dung đã sẵn sàng.

Phép đo thật trong lượt rà soát: kết nối/TLS hoàn tất khoảng 0,23 giây; một yêu cầu
cực ngắn trả HTTP 200 sau 16,52 giây. Một lượt qua prompt chat đầy đủ chạm deadline
45 giây. Đây là bằng chứng mốc 15 giây quá ngắn cho một số lượt, đồng thời độ trễ
provider vẫn biến động; tăng budget không bảo đảm hết mọi timeout. Groq trong bộ
kiểm tra live cũng từng trả 429; không coi fallback là quota vô hạn.

### Đo lại trên máy của nhóm

Sau khi cài dependency phát triển của backend và điền key trong `.env`:

```sh
npm run ai:benchmark
```

Lệnh tạo database tạm và ảnh bàn phím tự vẽ, không đọc shop đang kết nối, không
đăng sản phẩm. Có gọi API thật và dùng quota. Báo cáo không chứa key/prompt nằm
ở `docs/evaluations/ai-latency/results.json` (gitignore); exit code khác 0 nếu
có ca thất bại/fallback. Các ca: chào hỏi, tổng quan, đơn, kho, SKU, tư vấn,
tính lời và bản nháp từ ảnh. Test này cần dependency `pytest` từ nhóm dev.

### Phản hồi “chưa gọi được AI” khi soạn hàng — 21/10/2026

Các lượt đọc số liệu vẫn gọi Gemini thành công trong khi nhật ký tạo nháp ghi
`invalid_response`. Đây là lỗi nội dung/contract, không phải bằng chứng key hết
quota hoặc mất mạng. Luồng tạo nháp đã sửa các trường hợp:

- “đây nè”, “nó nè”, “hình này”, “ảnh đây” được hiểu theo ảnh/lịch sử; không
  ghi nguyên câu thành tiêu đề. Bản nháp cũ có tiêu đề dạng này tự được sửa ở
  lượt chat kế tiếp, giữ ảnh/giá/tồn. Không chỉnh trực tiếp database của shop.
- Phản hồi chỉ hỏi thêm một trường còn thiếu vẫn hợp lệ. JSON rỗng hoặc hỏi
  lại trường đã đủ không được coi là nội dung hoàn chỉnh.
- Kiểm tra ngành hàng, tiêu đề/mô tả có nghĩa và bằng chứng nằm trong contract
  dùng chung, nên model được yêu cầu tự sửa trước khi service bỏ phản hồi.
  CTA cuối caption và “trải nghiệm mới” không bị nhầm thành câu lệnh hoặc lời
  khẳng định hàng mới; tuyên bố hàng mới/bảo hành vẫn phải có dữ kiện.
- JSON bị cắt vì `MAX_TOKENS` được thử lại một lần với yêu cầu ngắn gọn. Sau
  hai phản hồi cấu trúc không hợp lệ, có thể dùng đúng **một** lượt Groq đã cấu
  hình nếu còn thời gian/hạn mức và model nhận đủ gallery. Dùng nguyên validator
  cho mọi provider; không bỏ ảnh, chấp nhận JSON dở hoặc tự điền giá/tồn.
- Mọi bước giữ deadline chung 60 giây. Nội dung bị chặn hoặc chứa yêu cầu công
  cụ không được dùng cơ chế sửa schema để vượt qua chặn.

Log `Listing used grounded fallback` có `reason` và `stage`; facts của lượt lỗi
giữ `ai_failure` để đối chiếu mà không log prompt, ảnh hoặc key. UI phân biệt
AI đã trả nội dung không hợp lệ với lỗi gọi dịch vụ. `ai:check` cũng giải thích
`invalid_response` riêng, không mặc định quy lỗi cho API key.

Benchmark được chặn nếu **bất kỳ** đường database/static/uploads nào trỏ ra
ngoài thư mục tạm. Hai ca mới kiểm tra khởi đầu đăng hàng chưa rõ sản phẩm và
câu nối tiếp “đây nè”. Ngày 21/10 sau sửa: 10/10 ca qua, đọc trực tiếp 6–30ms,
các lượt Gemini 1,4–2,4s, không fallback. Các lần đo độc lập có thể khác nhau;
gói miễn phí vẫn chịu quota của nhà cung cấp.

Sau khi nhận code, khởi động lại phiên `npm run demo` đang chạy để API nạp mã
mới; không cần đổi key hoặc tạo lại database chỉ vì `invalid_response`.

Lần đo ngày 21/10: năm câu đơn giản 5–30ms trong backend, không gọi AI; tư vấn
32,9s, tính lời 20,5s (một lượt trích dữ kiện), tạo bản nháp ảnh 16,5s. Tất cả
qua kiểm tra nội dung và không fallback. Đây là số đo một lần trên máy phát triển,
không phải cam kết độ trễ; model/quota/mạng có thể thay đổi kết quả.
