# Kết quả kiểm tra SellerPilot local

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
