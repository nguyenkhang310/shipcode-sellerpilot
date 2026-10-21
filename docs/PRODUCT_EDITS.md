# Sửa sản phẩm qua SellerPilot

Sửa sản phẩm đã đăng được tách khỏi bản nháp đăng hàng. Có thể đề xuất sửa tiêu đề,
mô tả, giá bán và tồn kho trong một lần. Chủ shop xem giá trị trước/sau rồi xác nhận;
chat không tự ghi thay đổi lên gian hàng.

## Cách dùng

Khởi động lại phiên demo bằng `npm run demo`. Launcher tự chạy migration
`20261019_11` trước khi mở API. Migration thêm bảng đề xuất/audit và cột liên kết
trong lịch sử; không xóa sản phẩm hoặc lịch sử cũ.

Ví dụ — thay `A001` bằng SKU thật của shop:

```text
Sửa tiêu đề SKU A001 thành Bàn phím Nova K75 màu trắng
Mô tả: Bàn phím Nova K75 màu trắng.
Giá bán 5 xị
Tồn kho 20
```

Hoặc yêu cầu AI viết lại từ dữ kiện hiện tại:

```text
Tối ưu tiêu đề và mô tả SKU A001 cho rõ ràng hơn.
Giữ nguyên thông số, không thêm tính năng chưa có.
```

Tab **Sản phẩm → Gợi ý nội dung** mở yêu cầu soạn bản sửa. **Chỉnh sửa** mở form
ngay trong app, không chuyển sang trình duyệt. Tên sản phẩm duy nhất có thể được
tìm qua câu “Tối ưu mô tả cho [tên sản phẩm]”; nhiều kết quả cần chọn SKU chính xác.

## Sửa thủ công trong app

1. Mở Sản phẩm hoặc Hàng sắp hết, bấm **Chỉnh sửa** trên sản phẩm.
2. Nếu có phân loại, chọn SKU để sửa giá/tồn. Tên và mô tả dùng chung cho tất cả
   phân loại; không tự ghi giá/tồn sản phẩm cha khi chưa chọn SKU.
3. Nhập tên (3–200 ký tự), mô tả (tối đa 10.000 ký tự), giá nguyên từ 1.000 đến
   1.000.000.000 ₫ và tồn nguyên 0–1.000.000. Có thể nhập `500.000` hoặc `500000`;
   không dùng đơn vị rút gọn như `5 xị` ở ô số thủ công. Chat vẫn hỗ trợ tiếng lóng.
4. Bấm **Xem thay đổi sản phẩm** để đối chiếu cũ → mới, sau đó **Xác nhận lưu sản phẩm**.
   Đóng khi đang sửa có bước xác nhận bỏ thay đổi; chưa xác nhận lưu thì không ghi.

API local mới:

- `GET /api/v1/management/products/{id}`: nội dung, phân loại, trường được sửa và
  `version` của toàn bộ sản phẩm/phân loại hiện tại.
- `PATCH` cùng URL: gửi `expected_version`, `request_id` UUID, `variant_id` nếu
  đang sửa phân loại và chỉ các trường thực sự đổi (`name`, `description`,
  `price_vnd`, `stock`). Không nhận null/giá âm/số lẻ/tên rỗng hoặc trường lạ.
- Đối chiếu version và ghi trong cùng transaction. Mất phản hồi thì gửi lại
  đúng UUID/nội dung; receipt trả kết quả hiện tại, không ghi lần nữa. UUID cũ
  với nội dung khác hoặc version cũ trả 409. App yêu cầu tải lại trước khi sửa tiếp.
- Giữ nguyên phạm vi seller; không đổi SKU, trạng thái, ngành hàng hoặc ảnh trong
  form này. Luồng chỉ áp dụng cho gian hàng local của app; không gọi Open API
  Shopee thật. Không cần migration agent mới; receipt được tạo trong database shop
  ở lần lưu đầu tiên.

Giá và tồn nhận số mới từ lời người bán, không để model tự chốt. `5 xị` được quy đổi
500.000đ bằng parser tiền dùng chung. Nếu giá mơ hồ, hỏi lại trước khi tạo đề xuất.
Nội dung có sẵn được giữ xuống dòng; câu lệnh không biến thành tiêu đề/mô tả.
Nên đặt nội dung trong dấu ngoặc kép nếu chính đoạn mô tả có chứa các cụm như
“giá bán 100k, tồn kho 20” và bạn chỉ muốn sửa chữ, không đổi giá/tồn.

Tiêu đề/mô tả thuộc sản phẩm cha và dùng chung cho phân loại; thẻ xem trước ghi rõ
phạm vi này. Giá/tồn của sản phẩm có phân loại cần SKU phân loại cụ thể; không âm
thầm đổi tất cả phân loại từ SKU cha. Các trường giống dữ liệu hiện tại không cần
ghi lại. Mỗi thẻ cho xem toàn bộ nội dung dài và có **Bỏ qua / Xác nhận sửa**.

Lệnh không dấu như `sua tieu de SKU A001 thanh Giay the thao` được nhận diện
trong cùng luồng. Tồn `2.000` được hiểu là 2.000 sản phẩm, tồn `0` vẫn hợp lệ;
số lẻ/khoảng như `2,5`, `2 hoặc 3` cần hỏi rõ, không lấy một phần con số. Sau
câu hỏi chỉ còn thiếu tồn, có thể trả lời ngắn `2.000` hoặc `ton: 2.000`. Khi
đang hỏi chọn món để sửa, `Thôi không sửa nữa` bỏ yêu cầu đang chờ; không tạo
đề xuất mới từ câu phủ định. Đề xuất đã tạo vẫn được duyệt/bỏ qua trên thẻ.

## Đồng bộ và bảo vệ dữ liệu

- Backend đối chiếu lại các trường đang sửa ngay trong transaction của shop.
  Nếu giá/tồn/nội dung đó đã đổi, trả 409 và yêu cầu đề xuất mới; không cập nhật nửa chừng.
- Sửa giá/tồn biến thể đồng bộ giá thấp nhất/tổng tồn khả dụng về sản phẩm cha.
- Một receipt gắn UUID được ghi cùng transaction cập nhật trong database shop.
  Nếu backend bị ngắt sau khi shop commit, xác nhận lại dựa trên receipt để hoàn tất
  audit, không dựa vào việc tình cờ giá trị hiện tại trùng giá trị muốn đổi.
- Audit duy nhất cho mỗi đề xuất. Đề xuất được cách ly theo shop đang liên kết.
- Sau xác nhận, app làm mới dữ liệu quản lý và danh mục. Website đọc cùng database
  UTE MALL; tải lại trang sản phẩm để thấy nội dung mới. URL/ảnh/SKU không bị thay.
- AI viết lại nội dung hiện hỗ trợ qua provider Gemini và Groq dự phòng trong adapter
  Gemini. Lệnh gán giá trị cụ thể dùng parser local, không cần model. Không cam kết
  model luôn viết tốt hoặc nhận diện được mọi đặc tính bịa; chủ shop vẫn duyệt thẻ.

## API

```http
POST /api/v1/product-edits
Content-Type: application/json

{"sku":"A001","changes":{"name":"Tiêu đề mới","description":"Mô tả mới","price_vnd":500000,"stock":20}}
```

`POST /api/v1/product-edits/{id}/confirm` và `.../reject` trả trạng thái mới cùng
`idempotent`. Chat trả `intent=update_product`, `product_edit_proposal`; trường
`proposal` cũ cho đổi giá đơn lẻ vẫn tương thích. Lịch sử đọc trạng thái đề xuất mới nhất.

Đầu vào chỉ cho phép 4 trường: tên 3–200 ký tự, mô tả tối đa 10.000 ký tự, giá từ
1.000đ đến 1 tỷ, tồn là số nguyên 0–1 triệu. Có thể xóa mô tả bằng chuỗi rỗng qua API;
không nhận trường SQL, HTML executable hoặc công cụ tùy ý từ model.

## Kiểm thử đã thực hiện

Test dùng DB tạm: trước xác nhận không ghi shop; sửa nhiều trường nguyên khối;
phân loại; hủy; cách ly tenant; dữ liệu stale; receipt khi ngắt giữa hai DB; audit
không trùng; migration nâng/hạ giữ lịch sử; ngữ nghĩa nhiều trường, nội dung chứa giá,
SKU nối tiếp và tên sản phẩm duy nhất. Gemini thật đã tạo nội dung sửa trên shop tự
tạo, xác nhận và xác nhận lặp, kiểm tra giá/tồn không bị sửa cùng nội dung.

UI được thử bằng web build trên Chrome riêng với API giả lập, gồm nội dung dài,
mở rộng bản xem trước và xác nhận. Chưa kiểm thử native iPhone/Android trong đợt này.
