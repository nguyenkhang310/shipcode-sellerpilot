# Third-party data and assets

Repository chứa source của SellerPilot/UTE MALL và một catalog để chạy demo. Giấy phép dataset không tự áp dụng cho toàn bộ source dự án.

## Amazon Berkeley Objects (ABO)

Nguồn: [Amazon Berkeley Objects](https://amazon-berkeley-objects.s3.amazonaws.com/index.html). Metadata và ảnh ABO được phát hành theo [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).

Một phần catalog và ảnh trong `UTE MALL/static/catalog/` được chọn từ ABO. Product records giữ `source=abo`, `source_id` và URL nguồn. Việc quy đổi tên ngành hàng, giá VND, tồn kho, số bán mô phỏng và gán shop là biến đổi phục vụ demo; không phải dữ liệu kinh doanh thực tế do Amazon cung cấp.

## Livostyle

Nguồn: [Livostyle Women's Fashion Catalog](https://github.com/arturayupov/womens-fashion-catalog-open-data), Arcada LLC (d/b/a Livostyle), MIT License.

Bản license đầy đủ được giữ tại [UTE MALL/data/LIVOSTYLE_LICENSE.txt](UTE%20MALL/data/LIVOSTYLE_LICENSE.txt). Catalog giữ `source=livostyle` và ID nguồn. Giá VND và tồn kho là giá trị mô phỏng.

## Metadata thời trang

Nguồn: [VashuTheGreat2/E-Commerce-Product-Recommendation](https://huggingface.co/datasets/VashuTheGreat2/E-Commerce-Product-Recommendation). Records giữ `source=vashu_hf`, ID và URL nguồn. Ảnh của nhóm này tham chiếu URL nguồn bên ngoài; khả năng truy cập phụ thuộc chủ nguồn.

Không coi việc một URL công khai là giấy phép sử dụng thương mại hoặc huấn luyện model. Cần kiểm tra quyền sử dụng nguồn tương ứng trước các mục đích ngoài bản demo học thuật của nhóm. Snapshot này không phải dữ liệu huấn luyện model.

## Project assets

Logo ShipCode/SellerPilot nằm tại `frontend/assets/`. Không dùng tên hoặc logo Shopee để ngụ ý UTE MALL là sản phẩm chính thức của Shopee.
