# Prompt thiết kế SellerPilot trên Lovable

Sao chép toàn bộ khối bên dưới vào Lovable. Nếu có thể, đính kèm hai ảnh logo trong repo: `frontend/assets/shipcode-logo-app.png` và `frontend/assets/sellerpilot-tab-logo.png`.

```text
Thiết kế và triển khai prototype giao diện SellerPilot: trợ lý kinh doanh cho chủ shop Việt Nam. Đây là ứng dụng chủ shop dùng mỗi ngày, cần tối giản, sang, dễ đọc và thao tác nhanh như một sản phẩm iOS đã hoàn thiện. Tôi cần giao diện có cá tính và tính thực dụng, không giống một dashboard AI được tạo từ template.

ĐỊNH HƯỚNG HÌNH ẢNH
Tham khảo chất lượng typography và tương tác của Apple Wallet, Linear, Shopify và Stripe Dashboard; tham khảo cách tổ chức công việc của Shopee Seller Centre/TikTok Shop. Xây dựng ngôn ngữ riêng của SellerPilot, không chép nguyên bố cục của một thương hiệu.
- Nền #F6F6F8, bề mặt trắng, chữ #1C1C1E, màu chủ đạo navy #0B1F3F. Vàng #FFB800 chỉ nhấn ở logo và một vài chi tiết quan trọng.
- Font hỗ trợ dấu tiếng Việt đẹp, ưu tiên hệ thống iOS hoặc Inter. Nội dung chính 15–17px, metadata 12–13px nhưng đủ tương phản, số liệu dùng tabular numerals.
- Khoảng cách theo nhịp 4/8px. Thẻ bo 16–22px, viền mảnh, bóng rất nhẹ. Hạn chế nhét mọi thứ vào các thẻ lồng nhau.
- Không gradient tím/xanh, nền phát sáng, emoji trang trí, icon robot ở khắp nơi, số liệu màu mè hoặc đoạn giải thích tính năng thừa.
- Có light/dark mode thật, kiểm tra tương phản chữ, placeholder, badge và nút khi chuyển theme.
- Giữ logo ShipCode trong header nhỏ gọn; logo SellerPilot dạng tròn làm nút trợ lý nổi bật chính giữa thanh điều hướng. Không thay bằng chữ AI lớn.

CẤU TRÚC VÀ MÀN HÌNH
Ưu tiên mobile, kiểm tra ở 320, 390 và 430px. Có bố cục desktop hợp lý cho bản web; side panel trình duyệt 380–520px dùng mật độ gọn, không phóng to nút như một màn hình điện thoại bị kéo giãn.
Thanh dưới có 5 tab: Quản lý, Sản phẩm, Trợ lý (ở giữa bằng logo), Đơn hàng, Shop. Kính mờ vừa phải và nền đủ đặc để nội dung không xuyên lên làm rối chữ. Vùng được chọn rõ ràng; nội dung cuối trang cuộn lên khỏi thanh này.

1. QUẢN LÝ
- Tên shop, trạng thái kết nối và thời gian cập nhật ngắn gọn.
- Bộ chọn Hôm nay / 7 ngày / 30 ngày / lịch chọn ngày cụ thể, nền chọn trượt nhẹ 210ms và tắt khi reduced motion. Có nút ngày trước/sau, không chọn ngày tương lai. Ngày lịch sử lấy đủ 24 giờ Việt Nam; hôm nay đến hiện tại.
- Thẻ giá trị đơn hàng là số liệu chính; số đơn, giá trị đã giao, giá trị trung bình và chênh lệch kỳ trước là số liệu phụ.
- Biểu đồ đường đơn giản có thể chạm xem từng mốc; phân bố trạng thái đơn và sản phẩm bán tốt phía dưới.
- Việc cần xử lý: chờ xác nhận, chờ lấy hàng, đang giao, hàng sắp hết. Chạm vào đi đúng danh sách đã lọc.
- Khi đổi kỳ: không nhảy vị trí cuộn, không co giãn chiều cao thẻ, không gắn nhãn kỳ mới lên số kỳ cũ. Dùng placeholder có kích thước ổn định; phản hồi cũ đến muộn không ghi đè kỳ mới.
- Phân biệt giá trị đơn, doanh thu đã giao, lợi nhuận và tiền đã thu. Thiếu dữ kiện thì hiển thị “—”, không tự gán 0 hoặc bịa % tăng trưởng.

2. SẢN PHẨM
- Danh sách có ảnh thật, tên hai dòng, giá, SKU, tồn kho, đã bán và trạng thái. Tìm kiếm theo tên/SKU, bộ lọc hàng sắp hết, trạng thái rỗng và lỗi ảnh gọn.
- Nút thêm sản phẩm chuyển sang hội thoại trợ lý với ý định tạo bản nháp.
- Chỉnh tiêu đề/mô tả/giá/tồn qua đề xuất cũ → mới; người bán xem lại rồi xác nhận. Không hiển thị như đã lưu khi mới có gợi ý của AI.
- Nút Chỉnh sửa mở form thủ công ngay trong app, chọn SKU phân loại, giữ tên/mô tả chung. Có xem lại trước khi lưu, xác nhận bỏ thay đổi và khôi phục cùng UUID khi mất phản hồi. 409 yêu cầu tải lại, không tự ghi đè.

3. TRỢ LÝ
- Hội thoại gọn như ChatGPT/Gemini mobile. Bong bóng người dùng bên phải; trả lời trợ lý bên trái có khoảng trắng và phân cấp nội dung rõ. Markdown vừa đủ: đoạn văn, bullet, chữ đậm; không bảng rộng tràn màn hình, không hiện JSON thô.
- Header gồm lịch sử ở nút ba gạch, tên SellerPilot và tạo cuộc trò chuyện mới. Lịch sử vuốt trái để ghim/xóa; xóa có xác nhận.
- Composer bo tròn: nút cộng, ô nhập và gửi/dừng. Ô nhập tự tăng từ khoảng 46px đến tối đa 128px, sau đó cuộn nội bộ và luôn nhìn thấy con trỏ/dòng đang gõ. Không để textarea cao vọt lên hoặc che chữ khi xuống dòng.
- Chọn tối đa 6 ảnh: ảnh chỉ nằm ở khay đính kèm, có xóa/thêm ảnh; chỉ gửi khi người dùng bấm Gửi. Chọn ảnh không tự gửi tin.
- Bàn phím mở thì composer bám phía trên, thanh điều hướng không nhảy theo bàn phím hoặc chiếm chỗ vô lý. Khi đóng bàn phím, bố cục trở lại ổn định.
- Đang xử lý có ba chấm nhịp nhàng, nút Dừng hoạt động. Khi có trả lời mới, tự cuộn nếu đang ở cuối; nếu đang đọc phía trên thì giữ vị trí và hiện nút về cuối.
- Có các ví dụ hội thoại thực tế: hỏi doanh thu, tính giá có lời từ giá vốn/phí, đề xuất chiến lược dựa trên số liệu và lên kịch bản TikTok cho một sản phẩm cụ thể. Thể hiện rõ số liệu thực tế và giả định.
- Đăng hàng có thể bắt đầu bằng tin nhắn hoặc ảnh. Người dùng nói “đăng sản phẩm lên shop” thì trợ lý bắt đầu soạn; nói “xe đó” sau câu hỏi chọn món thì hiểu theo lịch sử/ảnh, không đặt nguyên câu đó làm tiêu đề.
- AI tự soạn tiêu đề/mô tả từ thông tin có thật; chỉ hỏi phần còn thiếu. Không bịa cấu hình, bảo hành, giá hoặc tồn kho. Giữ nguyên caption người dùng yêu cầu giữ.
- Thẻ bản nháp có gallery, tên, mô tả đọc được đầy đủ, ngành hàng, giá, tồn và trạng thái. Chưa có ảnh vẫn xem được bản nháp; chưa đủ thông tin thì chưa có nút đăng. Có đủ thì người bán duyệt trước khi đăng.

4. ĐƠN HÀNG
- Tìm mã đơn/người mua, lọc trạng thái bằng hàng chip cuộn ngang; nội dung chip không bị cắt chân.
- Thẻ đơn có người mua, thời gian, ảnh/tên hàng, số lượng, tổng tiền và badge trạng thái.
- “Quản lý đơn” mở bottom sheet ngay trong app; xem dòng hàng theo giá mua lúc đặt, người nhận, điện thoại, địa chỉ và ghi chú.
- Sửa thông tin nhận hàng khi chưa bàn giao; sửa ghi chú. Chỉ hiện chuyển trạng thái hợp lệ: chờ xác nhận → chờ lấy hàng hoặc hủy; chờ lấy hàng → đang giao hoặc hủy; đang giao → đã giao. Đơn đã giao/hủy/hoàn không cho tùy tiện chuyển ngược.
- Có màn xem lại thay đổi trước khi lưu/hủy. Hủy hoàn số lượng về kho trong hệ thống; không tuyên bố đã hoàn tiền ngân hàng.
- Nút lưu không bị che khi nội dung dài/bàn phím mở. Trong khi lưu khóa thao tác lặp. Mất phản hồi cho thử lại cùng operation ID; lỗi 409 yêu cầu tải chi tiết mới, không tự ghi đè.

5. SHOP
Thông tin shop đang liên kết, nguồn dữ liệu, kết nối, đồng bộ và cài đặt giao diện. Nhãn trạng thái chính xác, ít chữ. Phân biệt nguồn shop local với kết nối Shopee thật; không lấy dữ liệu nguồn này điền vào nguồn kia.

CHẤT LƯỢNG TƯƠNG TÁC
- Mục tiêu chạm tối thiểu 44×44px trên mobile; không cần vẽ mọi icon trong một nút tròn lớn.
- Hiệu ứng ngắn 160–220ms, ưu tiên opacity/transform. Không bounce mạnh hoặc animate chiều cao cả trang. Hỗ trợ reduced motion.
- Không mất nội dung đang nhập khi đổi tab. Không chồng chữ, mất chân chữ tiếng Việt, tràn số tiền dài hoặc ẩn nút dưới safe area.
- Hoàn thiện trạng thái loading, empty, offline, lỗi validation, mất phản hồi sau lưu, dữ liệu thay đổi đồng thời, ảnh lỗi, hội thoại dài, nhiều ảnh và nội dung rất dài.
- Mọi nút nhìn như có chức năng phải có tương tác thực tế trong prototype; không dùng các nút chết hay popup “coming soon”. Không thêm chức năng giả vượt quá phạm vi trên.

TÍCH HỢP VÀ ĐẦU RA
Lovable có thể tạo prototype React/TypeScript responsive, nhưng backend hiện có là FastAPI và app chính là Expo React Native. Tách component trình bày, state và API adapter để chuyển thiết kế sang app thuận tiện. Không tự thay backend bằng Supabase, không yêu cầu nhập API key trên giao diện.
- Thống kê: GET /api/v1/management/dashboard?days=1|7|30; một ngày lịch sử dùng ?days=1&date=YYYY-MM-DD. Kiểm tra from_date/to_date trước khi gắn dữ liệu lên ngày đang chọn; cache tách từng ngày.
- Sản phẩm/đơn: GET /api/v1/management/products và /orders với tìm kiếm, lọc và phân trang.
- Chi tiết: GET /api/v1/management/orders/{id}.
- Sản phẩm thủ công: GET/PATCH /api/v1/management/products/{id}; lưu request_id UUID, expected_version, variant_id nếu có và trường thực sự đổi. Dùng editable_fields/variants từ server.
- Lưu đơn: PATCH cùng URL, gửi request_id UUID, expected_version và các trường thực sự thay đổi. Dùng allowed_statuses/editable_fields từ server.
- Chat, ảnh, bản nháp, lịch sử và đề xuất dùng API adapter riêng theo các contract đã có trong repo; không phát minh endpoint rồi giả định backend hỗ trợ.
- Nếu chưa nối được backend, dùng fixture TypeScript tách biệt, dữ liệu nhất quán và có thể chuyển sang API thật. Không hiển thị nhãn kỹ thuật/dữ liệu giả trong thiết kế chính; ghi rõ chế độ fixture trong tài liệu prototype.
- Xuất một prototype hoàn chỉnh có đủ năm tab, design tokens, component tái sử dụng và hướng dẫn tích hợp ngắn. Ưu tiên làm tinh ba luồng: xem số liệu, chat tạo sản phẩm, sửa/xử lý đơn. Kiểm tra responsive và khả năng truy cập trước khi kết thúc.
```
