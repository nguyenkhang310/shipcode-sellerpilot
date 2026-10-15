# Kiểm thử ứng dụng

Từ root:

```sh
npm run typecheck
npm run test:api
npm run build
npm run build:ios
```

TypeScript bật strict và kiểm tra biến/tham số không dùng. `api-transport.cjs` kiểm tra ưu tiên URL API, ID ổn định khi thử lại, lấy kết quả đã lưu và hủy yêu cầu.

## API UI giả lập

Từ `backend/`:

```sh
.venv/bin/python tests/chat_reliability_server.py
```

Server dùng shop, đơn hàng, ảnh mẫu và AI có độ trễ hoàn toàn giả lập. Không sao chép shop hoặc gửi dữ liệu lên model.

Từ root, terminal khác:

```sh
EXPO_PUBLIC_API_URL=http://127.0.0.1:8123/api/v1 npm run build
backend/.venv/bin/python -m http.server 5174 --bind 127.0.0.1 --directory frontend/dist/web
```

Với Playwright/Chrome đã cài, terminal khác từ root:

```sh
node frontend/tests/app-audit.cjs
node frontend/tests/dashboard-periods.cjs
node frontend/tests/chat-reliability.cjs
```

Nếu Playwright không nằm trong dependency cục bộ, đặt `PLAYWRIGHT_MODULE` tới module đã cài và `CHROME_EXECUTABLE` tới Chrome. `QA_APP_URL` và `QA_API_ORIGIN` có thể đổi địa chỉ test. Không dùng API shop thật cho các test có tạo/sửa dữ liệu.

- `app-audit`: năm tab ở 320/375/430 px, ảnh sản phẩm, tìm kiếm, đơn, input co giãn, keyboard viewport, biểu đồ rỗng, lỗi đồng bộ và giao diện tối.
- `dashboard-periods`: đổi Hôm nay/7/30 ngày khi API chậm, bấm liên tục, phản hồi về trễ, cache 60 giây, khung không co giật, đồng bộ lỗi và phản hồi sai kỳ.
- `chat-reliability`: Dừng, gửi tiếp sau Dừng, mất phản hồi sau commit, tải lại app và khôi phục upload mà không tạo bản nháp trùng.

Ảnh và JSON kết quả nằm trong `docs/evaluations/`, được gitignore. Khi xong, dừng hai server QA và chạy lại `npm run build` để bỏ địa chỉ API thử khỏi bundle web.

Các test browser không thay thế kiểm tra safe area, bàn phím, Dynamic Type và vòng đời app trên iPhone thật.
