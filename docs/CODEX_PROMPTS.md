# ShipCode SellerPilot — PROMPT CHO CODEX

> Dùng 3 prompt theo thứ tự. Đầu tiên hãy copy `SHIPCODE_MASTER_PLAN.md` vào repo ở `docs/SHIPCODE_MASTER_PLAN.md`. Mỗi prompt nên ở một lượt Codex riêng để kiểm soát kết quả. Không dùng một prompt yêu cầu viết toàn bộ app và mọi tính năng cùng lúc.

## PROMPT 1 — Dựng skeleton chạy được (D1)

```text
Bạn là senior fullstack engineer và tech lead cho dự án ShipCode SellerPilot.
Đọc toàn bộ docs/SHIPCODE_MASTER_PLAN.md rồi thực hiện CHỈ PHASE 1.

Goal: dựng monorepo MVP, có backend + frontend boot được trên máy local, cấu trúc sạch, không overengineering.

Tech stack:
- Backend Python 3.11+, FastAPI, SQLAlchemy 2, Pydantic v2, SQLite, Alembic, pytest.
- Frontend React + Vite + TypeScript + Tailwind + React Router + TanStack Query.
- AI provider interface dùng Ollama local (qwen3:4b-instruct). Chưa làm agent trong phase này.

Tasks:
1. Khởi tạo thư mục phù hợp cây repo ở master plan nhưng CHỈ tạo file thật sự dùng được; không tạo file rỗng hàng loạt.
2. Backend: cấu hình `.env`, app factory/main FastAPI, CORS localhost:5173, `/api/v1/health`, SQLite session, basic exception handling, OpenAPI docs, dependencies và pytest smoke test.
3. Frontend: Vite/React TS; responsive shell sidebar/topbar, route Overview/Inbox/Orders/Products/Operations/Import với placeholder có trạng thái rõ; reusable API client lấy base URL từ env, health status chip.
4. Tạo `.gitignore`, `.env.example`, `README.md` đầy đủ lệnh run cho macOS/Linux/Windows PowerShell.
5. Tạo `sample_data` schema/sample skeleton và docs API contract bản nháp.
6. Không viết endpoint Shopee thật, không fake API connected, không yêu cầu service cloud hoặc key.
7. Chạy tests/build khi môi trường có thể, báo output; nếu không thể chạy thì nói rõ blocker và lệnh test cần làm.

Definition of done:
- `uvicorn app.main:app --reload` từ backend chạy.
- `npm run dev` trong frontend chạy.
- `/api/v1/health` trả 200.
- `npm run build` và `pytest` pass.
- Cho tôi tree repo, các lệnh chạy, những thứ còn thiếu cho Phase 2.

Không bắt đầu Phase 2 khi chưa hoàn thành Phase 1.
```

## PROMPT 2 — Database + CRUD + CSV + rules (D2–D3)

```text
Đọc docs/SHIPCODE_MASTER_PLAN.md và code hiện có. Thực hiện CHỈ PHASE 2.

Tasks:
- SQLAlchemy models + Alembic schema cho shops/products/variants/orders/order_items/conversations/messages/shop_policies/alerts/action_proposals/agent_runs/import_batches.
- Define typed Pydantic request/response schemas, DB repositories/services.
- Deterministic seed script với data realistic nhưng FAKE: >=20 products, >=30 variants, >=50 orders, >=12 customer messages; 3+ alert cases; policies returns/shipping/warranty. Có thể rerun không tạo duplicate.
- Products, orders, inbox, metrics and alerts REST endpoints theo plan; pagination/filter.
- Import CSV theo **Phụ lục A** của master plan: dry validation/error rows, idempotency. Nếu scope quá lớn hãy ưu tiên products + variants và orders, giữ messages seeding.
- Rules engine low-stock và overdue-orders, metric VND integer; không đếm cancelled orders vào doanh thu.
- Frontend các trang Products, Orders, Overview nối API thật, loading/error/empty states.
- Test CRUD/import idempotency, metrics, alert rules; seed + e2e smoke manual steps in README.

Constraints:
- LLM chưa cần trong phase này, tránh gắn cứng business rule vào model.
- All external platform interactions disabled; mode=demo/CSV.
- Không để empty method / pass / TODO trong critical endpoints.
- Chạy pytest, build và sửa lỗi do code mới gây ra.

Báo cáo file đã sửa, database migration, endpoints đã có, commands test và blocker.
```

## PROMPT 3 — AI Inbox + approval + trace + hoàn thiện (D4–D7)

```text
Đọc docs/SHIPCODE_MASTER_PLAN.md và code hiện có. Thực hiện CHỈ PHASE 3.

Goal: end-to-end agent có kiểm chứng và approval, chạy trên Ollama local.

Tasks:
1. Tích hợp local Ollama qua package `ollama`, model lấy từ OLLAMA_MODEL=qwen3:4b-instruct.
2. Pydantic structured output cho intent extraction và reply draft; dùng temperature=0, bounded timeout, retry <=1, fallback minh bạch.
3. Orchestrator cố định: classify -> read-only allowlisted tools -> verify facts -> draft -> proposal pending -> agent trace.
4. Read-only tools: search_catalog, get_variant_stock, get_order_status, get_shop_policy, get_shop_metrics; validate input IDs và shop scope.
5. Không cho LLM tự chạy SQL/http, không tự viết vào Shopee/TikTok, không auto send; approve/reject chỉ ghi DB nội bộ.
6. REST: POST inbox/conversations/{id}/draft-reply, POST agent/ask, GET agent/runs/{id}, POST operations/proposals/{id}/approve|reject, POST brief/daily.
7. Frontend AI Inbox: conversation history + generate draft + evidence + human review; agent trace; daily brief; notifications.
8. Tests với mock Ollama (không cần model khi CI) và cases: stock=0, no policy, invalid SKU, injection request, model down. Dùng real Ollama manual smoke riêng.
9. Hiện badge DEMO DATA và `sent_to_platform=false` ở mọi trạng thái có thể gây hiểu lầm.

Finish:
- Seed -> inbox -> draft -> evidence -> approval -> dashboard alerts -> daily brief chạy end-to-end.
- `pytest`, `npm run build` pass.
- Update README và `docs/DEMO_SCRIPT.md` trong 4 phút.
- Không đi sang P1 Shopee API nếu chưa có credentials+approved scopes.

Trả lại summary, files changed, test output, demo commands, remaining risks.
```

## PROMPT 4 — QA / Finalize (D8–D10)

```text
Đọc docs/SHIPCODE_MASTER_PLAN.md, tài liệu demo và tất cả code.
Mục tiêu chỉ sửa blocker và chuẩn bị bản thi `v0.1.0-demo`.

- Đảm bảo test imports/metrics/stock grounding/proposal idempotency và error fallback.
- Kiểm tra các trang và endpoint bắt đầu từ database trống, rồi seed.
- Tạo tập 20–30 evaluation questions tiếng Việt (kết quả gắn nhãn expected) và script đánh giá thủ công.
- Chạy build/tests, xử lý lỗi, kiểm tra `.env` không commit secrets.
- Chuẩn hóa demo mode & labels; tuyệt đối không claim live integration.
- Viết docs/DEMO_SCRIPT.md (3–4 phút) và RUNBOOK_DEMO.md (khởi động, reset, fallback, quay video).
- Nếu cần tích hợp Shopee, CHỈ đề xuất kế hoạch kỹ thuật và yêu cầu auth/scope; không tự tiến hành bypass quyền API.
- Đưa báo cáo cuối: features ready, features not ready, test evidence, demo steps và issue severity.
```

## Prompt rescue khi Codex tạo quá nhiều file nhưng chạy không được

```text
Dừng mở rộng tính năng. Hãy kiểm tra repo bằng các lệnh cài dependency, migration/seed, pytest, npm build, curl health; sửa lỗi khiến monorepo không khởi động được. Không thêm abstraction hoặc module mới nếu chưa cần. Chỉ công bố DONE khi có output thực tế; nếu môi trường không chạy được, mô tả chính xác lỗi còn tồn đọng và command để tái hiện.
```
