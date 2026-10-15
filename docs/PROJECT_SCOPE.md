# Phạm vi hiện tại

Theo yêu cầu hiện tại: tổ chức monorepo theo master plan, giữ frontend TypeScript/iOS
đang có, dựng nền backend chạy được rồi mới phát triển nghiệp vụ.

- Frontend: Expo + React Native + TypeScript; giữ màn hình, logo, EAS và nhận diện cũ.
- Backend: FastAPI, health, seller tools, proposal/confirm/reject, audit và Alembic.
- Dữ liệu: sản phẩm/biến thể/đơn lấy từ database UTE MALL; agent metadata ở DB riêng.
- Tài liệu gốc trong `UTE SV-Startup/` được giữ nguyên; bản sao plan/prompt ở `docs/`.

Quyết định điều chỉnh so với plan: **giữ Expo thay cho Vite/Tailwind/React Router**.
Navigation vẫn là tabs/modal React Native, không thêm một frontend web riêng.
`EXPO_PUBLIC_API_URL` thay `VITE_API_URL`; preview web dùng Metro trên port 5173.
Lý do: yêu cầu hiện tại ưu tiên app iOS đã được cấu hình và code hiện có.

Đã triển khai Qwen structured inference với fallback, tool tổng quan shop, tra SKU,
low stock, đổi giá có xác nhận và trace. Màn hình trợ lý Expo gọi API chat thật và xử
lý confirm/reject proposal. Chưa triển khai inbox khách hàng, daily brief, auth và
adapter Shopee/TikTok.

Qwen chỉ phân loại ý định và sinh structured output; model không được truy cập SQL hay
tự cập nhật giá ngoài quy trình proposal.
