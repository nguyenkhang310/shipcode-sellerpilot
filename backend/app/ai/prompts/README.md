# AI prompts

`classify.md` là system prompt đang chạy cho Qwen. Model chỉ trả intent và tham số
theo JSON Schema; backend mới được chọn tool, đọc database, tạo proposal và dựng câu
trả lời từ dữ liệu đã xác minh. Tin nhắn người dùng luôn được coi là dữ liệu không
tin cậy và không thể bỏ qua bước xác nhận.

Thư mục được giữ trong repo bằng tài liệu này; các file triển khai chỉ tạo khi dùng thật.
