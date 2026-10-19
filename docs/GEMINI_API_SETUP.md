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
