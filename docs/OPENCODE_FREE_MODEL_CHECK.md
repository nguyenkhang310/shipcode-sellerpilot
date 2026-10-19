# Kiểm tra model OpenCode Free — 18/10/2026

Đã refresh danh sách bằng `opencode models opencode --refresh --verbose`
trên OpenCode 1.18.30. CLI trên máy liệt kê 10 model active với giá input,
output, cache read/write đều là số 0. Danh sách này không nhất thiết trùng
toàn bộ model công bố trên website hoặc được phép dùng với tài khoản khác.

| Model ID | Metadata nhận ảnh | Thử sinh nội dung qua server OpenCode |
|---|---|---|
| `glm-5.3-flash-free` | Có | 403, đã tái hiện bằng `npm run ai:check` |
| `deepseek-v4.1-flash-free` | Có | 403 |
| `mimo-v2.6-flash-free` | Có | 403 |
| `nemotron-3.5-super-vl-free` | Có | 403 |
| `longcat-2.5-preview-free` | Có | 403 |
| `space-bunny-free` | Có | 403 |
| `beam-free` | Không | 403 |
| `big-pickle` | Không | 403 |
| `nemotron-3.5-lightning-free` | Không | 403 |
| `nemotron-3-ultra-free` | Không | 403 |

Phản hồi giống nhau:

> OpenCode's free tier can only be used from within OpenCode.

Chín model thay thế được thử bằng một tin chào tiếng Việt giả lập qua API session
của server OpenCode chính thức. Đã xác minh `providerID=opencode` và `modelID`
trong từng phản hồi lỗi khớp model được yêu cầu; không bị kéo về model GLM mặc định.
Không gọi trực tiếp inference gateway, đổi header nhận diện hoặc cấp quyền công cụ.
Session/server thử nghiệm được dọn khi hoàn tất; không thay cấu hình app hoặc shop.

Không gửi dữ liệu shop, lịch sử hay ảnh người dùng. Cột ảnh chỉ là khai báo
capability, **chưa kiểm chứng chất lượng đọc ảnh** vì ngay câu chào đã bị từ chối.
Kết quả không dùng để xếp hạng chất lượng ngôn ngữ hoặc suy luận của các model.

Tại thời điểm thử, chưa tìm được model miễn phí nào trong danh sách CLI này
được gateway chấp nhận qua đường gọi backend hiện tại. Đổi ID model đơn thuần
chưa giải quyết được giới hạn quyền. Cần quyền sử dụng chính thức cho tích hợp,
provider/API cho phép backend, hoặc model local. Không suy rộng kết quả thành
mọi tài khoản, mọi client hay mọi thời điểm đều bị chặn.

Nguồn danh sách và điều kiện dịch vụ:
[OpenCode Models](https://opencode.ai/v2/docs/console/models/).
Xem thêm [chẩn đoán GLM và trạng thái fallback](GLM_SETUP.md#6-xử-lý-lỗi).
