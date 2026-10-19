# API AI miễn phí cho SellerPilot

Ngày đối chiếu: **18/10/2026**. Phạm vi: 11 nền tảng có liên quan đến chat,
đọc ảnh, trích dữ kiện và tích hợp backend. Đây là nghiên cứu tài liệu chính thức,
**chưa phải kết quả gọi API bằng tài khoản của nhóm**. Quyền model, quota, khu vực
và tốc độ thực tế cần kiểm tra bằng key được cấp trước khi chuyển provider.

## Kết quả và thứ tự thử

| Nền tảng | Dạng miễn phí hiện được công bố | Mức phù hợp với demo |
|---|---|---|
| Gemini API | Free Tier cho một số model, gồm Gemini 3.8 Flash | Ưu tiên thử cho chat và ảnh trên cùng model |
| Z.ai trực tiếp | GLM-4.7-Flash/4.5-Flash và GLM-4.6V-Flash được ghi Free | Đáng thử; tách model chat và model nhìn ảnh |
| Groq | Free Plan có quota theo model | Đáng thử; có Qwen3.8-27B nhận ảnh |
| OpenRouter | Model `:free`, quota tài khoản | Hợp làm dự phòng hoặc thử nhanh |
| Cloudflare Workers AI | 10.000 Neurons/ngày với model đủ điều kiện | Có thể làm demo, phải chọn đúng model |
| Cohere | Evaluation key miễn phí có giới hạn | Phù hợp đánh giá/prototype |
| NVIDIA Build | Một số endpoint được ghi Free Endpoint | Phù hợp thử nghiệm, điều kiện theo endpoint/tài khoản |
| Mistral | Tài liệu công bố Free mode, hạn chế sử dụng | Cần xác minh model và quota trên tài khoản trước |
| Cerebras | Credit dùng thử, có thời hạn | Không tính là nguồn free gia hạn định kỳ |
| Hugging Face Inference Providers | Tài khoản Free hiện không có monthly credit | Không chọn làm nguồn API miễn phí mặc định |
| GitHub Models | Đã ngừng hoạt động | Loại khỏi phương án mới |

### Gemini API

`gemini-3.8-flash` nhận text và ảnh, có structured outputs. Bảng giá Standard ghi
input/output miễn phí ở Free Tier. Hạn mức thực tế xem trong AI Studio, áp theo
project; không cố định một con số chung cho mọi tài khoản. Free Tier có chính sách
sử dụng nội dung để cải thiện sản phẩm. Chưa đo chất lượng tiếng Việt trên các ca
SellerPilot nên thứ tự ưu tiên ở đây là đánh giá phù hợp tính năng, không phải benchmark.

Nguồn: [pricing](https://ai.google.dev/gemini-api/docs/pricing),
[model](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[rate limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[tạo API key](https://ai.google.dev/gemini-api/docs/api-key).

### Z.ai trực tiếp

Bảng giá ghi Free cho `glm-4.7-flash`, `glm-4.5-flash` và `glm-4.6v-flash`.
Hai model đầu là text; bản 4.6V-Flash nhận ảnh/text. Không nhầm với
`glm-5.3-flash` hoặc các bản **FlashX**, vốn có phí. Cần Standard API Key;
endpoint nền là `https://api.z.ai/api/paas/v4`. Đây là API riêng của Z.ai,
không dùng quyền Free của OpenCode. Quota phải xem trong tài khoản.

Nguồn: [pricing](https://docs.z.ai/guides/overview/pricing),
[vision](https://docs.z.ai/guides/vlm/glm-4.6v),
[API và xác thực](https://docs.z.ai/api-reference/introduction),
[quota tài khoản](https://z.ai/manage-apikey/rate-limits).

### Groq

Free Plan công bố cho `qwen/qwen3.8-27b`: 30 requests/phút, 1.000/ngày,
8.000 tokens/phút và 200.000 tokens/ngày; hạn mức tài khoản có thể khác.
Model nhận tối đa 3 ảnh/request, mỗi ảnh tính 2.048 input tokens. App đang cho
chọn 6 ảnh nên không thể chuyển nguyên request mà giữ hành vi cũ; phải thiết kế
xử lý đủ ảnh và tính thêm quota. `openai/gpt-oss-120b` là lựa chọn text có trong
Free Plan. Muse Spark Open trên Groq được ghi Enterprise/contact sales, không coi
là model free thay thế Muse trước đây.

Nguồn: [Free Plan limits](https://console.groq.com/docs/rate-limits),
[vision](https://console.groq.com/docs/vision),
[model catalog](https://console.groq.com/docs/models).

### OpenRouter

Free models có mức 20 requests/phút và 50/ngày khi chưa đạt điều kiện mua credit.
Mua ít nhất $10 credit nâng giới hạn free-model lên 1.000/ngày; điều đó vẫn cần
tiền ban đầu, không xếp vào phương án không chi phí. Lượt thất bại cũng tính quota.
`openrouter/free` chọn model tự động theo khả năng yêu cầu; với bản demo cần tái
lập hành vi, ưu tiên chọn ID model cụ thể đã kiểm tra.

Nguồn: [pricing và limits](https://openrouter.ai/pricing),
[free router](https://openrouter.ai/openrouter/free).

### Cloudflare Workers AI

Có 10.000 Neurons/ngày, reset 00:00 UTC; Neurons là đơn vị compute,
không phải 10.000 tin chat. Có model nhìn ảnh như Llama-3.2-11B-Vision.
Một số model mới như GLM-5.3-Flash, Kimi và DeepSeek V4 thuộc danh sách cần
phương thức thanh toán/credit; không suy rằng tất cả model trong catalog đều
dùng được bằng free allocation. Cần API token và account ID.

Nguồn: [pricing và điều kiện model](https://developers.cloudflare.com/workers-ai/platform/pricing/),
[vision model](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/).

### Cohere, NVIDIA và Mistral

- **Cohere:** evaluation/trial key giới hạn tổng 1.000 API calls/tháng;
  Chat API hiện ghi 20 requests/phút cho Command A và Command A Vision.
  Phân biệt evaluation key với production key.
  [Nguồn](https://docs.cohere.com/docs/rate-limits).
- **NVIDIA:** tài liệu xác nhận free inference endpoints ở Build, dùng key riêng
  với NGC. Chọn endpoint được đánh dấu Free; không cam kết con số quota chung
  hoặc quyền chạy production nếu chưa kiểm tra điều kiện endpoint/tài khoản.
  [Nguồn](https://docs.nvidia.com/ai-workbench/reference/faq#integrations-and-credentials),
  [catalog](https://build.nvidia.com/models).
- **Mistral:** quickstart hiện ghi Free mode có API, không cần credit card.
  Chưa xác minh quota dương hoặc quyền model trên tài khoản nhóm; chưa chọn làm
  provider chính. Key cho API automation khác key/budget của Vibe Code CLI.
  [Quickstart](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key),
  [giải thích hạn mức](https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them).

## Các thông tin cũ không nên dùng để chọn dịch vụ

- **Cerebras:** tài liệu hiện nêu $5 trial sau khi thêm phương thức thanh toán
  đã xác minh, hết hạn sau 30 ngày; không có gói no-cost tự gia hạn.
  [Nguồn](https://inference-docs.cerebras.ai/support/rate-limits).
- **Hugging Face:** bảng hiện tại ghi Free Users = None ở monthly credits.
  Không dùng số $0,10/tháng từ kết quả tìm kiếm hoặc bài cũ.
  [Nguồn](https://huggingface.co/docs/inference-providers/pricing).
- **GitHub Models:** đã đóng hoàn toàn ngày 30/07/2026, bao gồm inference API.
  GitHub Copilot là dịch vụ khác.
  [Nguồn](https://docs.github.com/en/github-models).

## Quyết định đề xuất cho repo

Ưu tiên thử **Gemini 3.8 Flash** với cả chat và ảnh; đồng thời **Z.ai** là ứng viên
đáng thử khi muốn API GLM miễn phí, gồm model text và vision riêng. **Groq** là
ứng viên tiếp theo nếu tốc độ đạt yêu cầu và xử lý được giới hạn 3 ảnh. Đây là
thứ tự thử dựa trên tài liệu, chưa khẳng định model nào hay hơn Muse.

Trước khi chuyển provider cần test bằng key được cấp và dữ liệu/ảnh giả lập:

1. Tiếng Việt: `5 xị`, `hai củ rưỡi`, câu phủ định, khoảng giá cần hỏi rõ.
2. Tin đủ thông tin không hỏi lại; câu trả lời tiếp nối đúng trường còn thiếu.
3. Nhiều ảnh cùng sản phẩm, ảnh không liên quan và ảnh của nhiều món khác nhau.
4. Tự soạn nội dung, không biến câu lệnh thành tên; không bịa bảo hành/thông số.
5. Tư vấn dùng dữ liệu shop; tính lời bằng backend, chỉ dùng chi phí có bằng chứng.
6. Hết quota/timeout/403 báo đúng trạng thái; không làm mất bản nháp hoặc đăng trùng.

Một tin nhắn trong SellerPilot có thể gọi nhiều lần API: phân loại, trích thông tin,
soạn câu trả lời, sửa schema hoặc retry. Vì vậy 50 requests/ngày không bằng 50
tin nhắn. Cần giảm lượt gọi thừa, giới hạn tổng retry, đọc Retry-After và theo dõi
token/quota. Không tự động chuyển sang model tính phí khi quota free hết.

Chưa thêm provider mới, đổi `.env`, tải model hay tạo tài khoản trong lần nghiên
cứu này. Backend vẫn giữ cơ chế kiểm tra dữ kiện và xác nhận thao tác ghi shop.
