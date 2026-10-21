# Kiểm thử ứng dụng

Từ root:

```sh
npm run typecheck
npm run test:api
npm run test:svg
npm run build
npm run build:ios
```

TypeScript bật strict và kiểm tra biến/tham số không dùng. `api-transport.cjs` kiểm tra ưu tiên URL API, ID ổn định khi thử lại, lấy kết quả đã lưu và hủy yêu cầu. `chat-messages.cjs` kiểm tra gộp bước upload nội bộ vào caption khi khôi phục lịch sử, giữ gallery và không tải lại ảnh đã hủy.

`svg-gradients.cjs` chạy bộ trích gradient native thật của phiên bản
`react-native-svg` đang cài. Bài này tái hiện cảnh báo `offset=".55"`, rồi kiểm
tra giá trị Stop của dock/biểu đồ không cảnh báo và vẫn giữ mốc 0.55. Browser có
thể chấp nhận chuỗi này nên riêng kiểm tra web không phát hiện được lỗi native.

## API UI giả lập

Từ `backend/`:

```sh
.venv/bin/python tests/chat_reliability_server.py
```

Server dùng shop, đơn hàng, ảnh mẫu và AI có độ trễ hoàn toàn giả lập. Không sao chép shop hoặc gửi dữ liệu lên model.

Dừng phiên Expo phát triển đang chạy trước khi xuất bundle QA, để tránh dùng chung cache với địa chỉ API giả lập. Sau kiểm thử, xuất lại bundle bình thường rồi khởi động `npm run demo`.

Từ root, terminal khác:

```sh
EXPO_PUBLIC_API_URL=http://127.0.0.1:8123/api/v1 npm run build
backend/.venv/bin/python -m http.server 5174 --bind 127.0.0.1 --directory frontend/dist/web
```

Với Playwright/Chrome đã cài, terminal khác từ root:

```sh
node frontend/tests/app-audit.cjs
node frontend/tests/dashboard-periods.cjs
node frontend/tests/dock-themes.cjs
node frontend/tests/management-editing.cjs
node frontend/tests/order-tracking.cjs
node frontend/tests/order-chat.cjs
node frontend/tests/chat-reliability.cjs
node frontend/tests/chat-scroll.cjs
node frontend/tests/chat-history.cjs
node frontend/tests/dashboard-live.cjs
node frontend/tests/chat-motion.cjs
```

Nếu Playwright không nằm trong dependency cục bộ, đặt `PLAYWRIGHT_MODULE` tới module đã cài và `CHROME_EXECUTABLE` tới Chrome. `QA_APP_URL` và `QA_API_ORIGIN` có thể đổi địa chỉ test. Không dùng API shop thật cho các test có tạo/sửa dữ liệu.

- `app-audit`: năm tab ở 320/375/430 px, ảnh sản phẩm, tìm kiếm, đơn, input co giãn, keyboard viewport, biểu đồ rỗng, lỗi đồng bộ và giao diện tối.
- `dashboard-periods`: đổi Hôm nay/7/30 ngày khi API chậm, bấm liên tục, phản hồi về trễ, cache 60 giây, khung không co giật, đồng bộ lỗi và phản hồi sai kỳ.
- `dock-themes`: 16 lần đổi sáng/tối ở 320/390/430/520px; kiểm tra material theo đúng theme, độ mờ, viền, backdrop, tab hiện tại, bản nháp chat và theme lưu sau reload. Chụp cả phần hiệu suất và thanh điều hướng. API bị chặn hoàn toàn bằng fixture, không cần 8123.
- `management-editing`: chọn ngày, chuyển nhanh trước/sau, phản hồi muộn, lỗi ngày và phục hồi; lịch ở 320/390/520px; form sửa tên/mô tả/giá/tồn, nhập tiền có phân cách, tồn 0, review, retry cùng UUID sau khi server đã lưu, bỏ thay đổi và 409. Xác minh `/qa/identity` trước khi chạy và chỉ ghi shop tạm tại 8123. Chạy **sau app-audit**; chạy lại cần khởi động lại đúng server QA để có dữ liệu gốc.
- `order-tracking`: thao tác đơn QA #10 ngay trong app, review trước khi ghi, chọn hãng, vận đơn, sao chép mã, timeline, cập nhật trạng thái từ phiên khác, giữ bản đang nhập và xử lý 409; không mở tab web. Có ảnh 320/390/520px, dark và reduced motion. Cần API QA sạch; có thể chạy sau `order-editor` (bài đó dùng đơn #5), nhưng không chạy hai bài đồng thời.
- `order-chat`: tra đơn #3 từ chat, mở chi tiết ngay trong app, hỏi tiếp bằng câu ngắn; đơn đã giao cũ có trạng thái khớp lịch sử mà không dựng giờ giao. Kiểm tra 320/390/520px và không có lệnh ghi hay popup.
- `chat-reliability`: Dừng, gửi tiếp sau Dừng, mất phản hồi sau commit, tải lại app và khôi phục upload mà không tạo bản nháp trùng.
- `chat-scroll`: hiệu ứng ba chấm đang gõ, câu trả lời dài tự cuộn, giữ vị trí khi đang đọc tin cũ, nút về cuối và composer co giãn.
- `chat-history`: vuốt trái thực tế, ghim/bỏ ghim, lưu qua reload, hủy/xác nhận xóa hội thoại đang mở và vùng chạm ở 320px.
- `dashboard-live`: số đơn/doanh thu tự cập nhật, khung giữ nguyên, tạm ngừng khi rời Quản lý, cập nhật ngay khi quay lại và phục hồi sau lỗi kết nối.
- `chat-motion`: chuyển tab/mở đóng lịch sử liên tục, giữ bản nháp, input 55 dòng giữ con trỏ ở dòng cuối và tùy chọn Giảm chuyển động.

Ảnh và JSON kết quả nằm trong `docs/evaluations/`, được gitignore. Khi xong, dừng hai server QA và chạy lại `npm run build` để bỏ địa chỉ API thử khỏi bundle web.

Các test browser không thay thế kiểm tra safe area, bàn phím, Dynamic Type và vòng đời app trên iPhone thật.

## Kiểm tra lỗi nhảy trang khi đổi kỳ

`dashboard-periods.cjs` và `dashboard-live.cjs` tự chặn API bằng dữ liệu trong
`management-fixture.cjs`, không cần server 8123 và không dùng database shop.
Chỉ cần bundle web đang được phục vụ ở 5174. `dashboard-periods` đo vị trí cuộn,
chiều cao trang, thẻ doanh thu và trạng thái đơn trong lúc tải chậm, lúc lỗi và
khi hồi phục; kiểm tra thêm cache, phản hồi sai kỳ, dữ liệu rỗng và giao diện tối.
Ảnh và kết quả của bài này mặc định nằm ở `docs/evaluations/dashboard-periods/`
(đổi bằng `QA_OUTPUT`).

`dashboard-state.cjs` kiểm tra hook React với API giả: chỉ cử chỉ kéo mới bật
`refreshing`, chuyển kỳ hủy lượt cũ, phản hồi muộn không ghi đè và polling không
thay snapshot khi số liệu giữ nguyên. Có thể cài bộ chạy riêng ngoài repo:

```sh
npm install --prefix /tmp/sellerpilot-qa --no-save react@19.2.3 react-test-renderer@19.2.3
QA_NODE_MODULES=/tmp/sellerpilot-qa/node_modules node --test frontend/tests/dashboard-state.cjs
```

React phát cảnh báo `react-test-renderer is deprecated`; bộ chạy này chỉ phục vụ
QA, không phải dependency của app. Hook test không mô phỏng hiệu ứng cuộn native.

`app-audit`, `chat-scroll` và `chat-motion` chuyển các yêu cầu API/ảnh qua
`qa-server.cjs` tới server giả lập 8123, kể cả khi bundle đang chứa địa chỉ API
phát triển. Vì vậy ba bài này không cần xuất lại bundle với địa chỉ 8123.

## Sửa và xử lý đơn ngay trong app

Sau khi chạy API QA với database tạm ở 8123 và phục vụ bundle web ở 5174:

```sh
node frontend/tests/order-editor.cjs
```

Bài này **ghi dữ liệu trong database QA tạm**, không dùng shop thật. Kiểm tra màn
chi tiết ở 320/390/520px, validation điện thoại, bước xem lại chưa ghi dữ liệu,
retry cùng UUID sau khi mất phản hồi, tải lại khi 409 và xác nhận/hủy đơn. Chạy
`app-audit.cjs` trước bài này nếu dùng chung một API QA; để chạy lại bài sửa đơn,
khởi động lại đúng server QA 8123 để có đơn #5 ở trạng thái ban đầu. Ảnh/kết quả
nằm tại `docs/evaluations/order-editor/` và không commit.

## Độ dễ đọc và bản nháp dài

`node frontend/tests/readability.cjs` chặn toàn bộ API bằng fixture; không ghi shop.
Kiểm tra nút trợ lý 72px nhô lên, đường khoét cong, bấm được phần phía trên, bốn
tab đủ 44px và chữ không bị thu xuống 10px; ảnh bấm đổi, tên/giá/tồn dài,
đọc toàn bộ mô tả và tải lịch sử đến muộn sau khi chuyển sang hội thoại mới.
Kiểm tra ở 320/390/430/520px; ảnh và JSON lưu tại `docs/evaluations/readability/`.
Bài này không thay thế Dynamic Type hoặc kiểm tra bàn phím iOS thật.

Các bài `chat-history` và `chat-reliability` cũng chuyển mọi API về server QA qua
`qa-server.cjs`; bundle không cần chứa địa chỉ 8123. Hai bài vẫn cần API QA đang chạy.
