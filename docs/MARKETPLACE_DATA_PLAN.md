# UTE MALL — kiến trúc dữ liệu Marketplace + SellerPilot

**Cập nhật:** 15/10/2026\
**Trạng thái:** Marketplace demo và tenant UTech Official đã được triển khai.

## Mô hình sản phẩm

- **UTE MALL** phục vụ người mua: catalog đa ngành, nhiều shop, tìm kiếm, Flash Sale, giỏ hàng và checkout.
- **UTech Official** là shop công nghệ của chủ shop trong kịch bản demo.
- **ShipCode SellerPilot** phục vụ chủ UTech: xem summary, tra tồn kho, tìm hàng sắp hết và đề xuất đổi giá có xác nhận.

SellerPilot lấy shop scope từ cấu hình backend, không nhận `shop_id` tự do từ nội dung chat.

## Dữ liệu đã chọn

### Toàn sàn

Dùng **Amazon Berkeley Objects (ABO)** cho phần lớn catalog đa ngành. ABO có 147.702 listing, 398.212 ảnh catalog và giấy phép CC BY 4.0. Bản demo chọn một tập cân bằng theo ngành thay vì đưa toàn bộ archive vào database.

Tập `VashuTheGreat2/E-Commerce-Product-Recommendation` chỉ dùng 700 dòng apparel cho hai ngành thời trang. Phân tích file cho thấy hơn 94% dữ liệu là apparel, accessories và footwear nên không phù hợp làm catalog toàn sàn.

### Shop SellerPilot

UTech Official dùng 270 listing công nghệ được chọn từ ABO, trải trên máy tính, laptop, bàn phím, chuột, lưu trữ, tai nghe, sạc, thiết bị văn phòng, phụ kiện và ốp điện thoại. Ảnh của các SKU này được tải local. Giá, stock và sold count được sinh theo khoảng giá riêng của từng nhóm sản phẩm.

Không dùng Amazon Reviews 2023 trong bản chạy hiện tại vì riêng metadata Electronics đã khoảng 1,96 GB và dataset card không công bố giấy phép rõ như ABO. Cách chọn này giúp bản demo gọn và provenance rõ hơn.

## Quy mô đã triển khai

| Entity | Số lượng |
|---|---:|
| Root categories | 16 |
| Shops | 24 |
| Products | 5.898 |
| UTech products/SKU | 270 |
| Synthetic buyers | 450 |
| UTech orders | 1.500 |
| UTech order items | 1.991 |

## Schema tenant hiện tại

- `shop`: slug, nhận diện, vị trí, rating, follower, verified, `is_sellerpilot`.
- `category`: slug, parent, icon, image và thứ tự hiển thị.
- `product`: `shop_id`, provenance, sold count, location, attributes và featured flag.
- `order`: `shop_id`, `checkout_reference`, `shipping_fee`, `discount_amount`.
- `product_variant`: SKU bán được; 270 sản phẩm UTech có variant tiêu chuẩn.

Checkout đa shop đã được triển khai: một order cho mỗi nhà bán, cùng `checkout_reference` cho một lượt đặt. Phí vận chuyển và giảm giá phân bổ theo shop; tổng các order khớp tổng checkout.

## Bất biến SellerPilot

- `SELLER_SHOP_SLUG` mặc định là `utech-official`.
- Tìm SKU luôn kiểm tra `product.shop_id`.
- Low stock chỉ lấy variant của UTech.
- Confirm đổi giá xác minh lại ownership trước khi update.
- SKU shop khác trả `sku_not_found`.
- Summary lọc `order.shop_id` và bỏ order cancelled khi tính doanh thu.

## Kênh Người Bán đã triển khai

Có `shop_member`, `shop_follow`, `conversation`, `message`, `return_request` và `seller_activity`. Tài khoản `utech` chỉ quản lý UTech Official. Mô tả các luồng và kiểm thử tại `UTE_MALL_ACCEPTANCE.md`.

## Provenance

Catalog chạy demo hiện được đóng gói trong `UTE MALL/data/demo-catalog.json.gz`; không phụ thuộc ổ cứng của máy phát triển. Database demo giữ `source`, `source_id`, `source_url` và `attributes_json`; các trường synthetic được ghi trong `field_origin`. Footer website hiển thị attribution tới ABO và các nguồn thời trang.
