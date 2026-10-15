# Data dictionary · schema dự kiến

| File mẫu | Trường |
|---|---|
| products.csv | external_product_id, name, description, active |
| variants.csv | external_variant_id, external_product_id, sku, size, color, price_vnd, stock, low_stock_threshold |
| orders.csv | external_order_id, fulfillment_status, payment_status, total_vnd, created_at |
| order_items.csv | external_order_id, sku, quantity, unit_price_vnd |
| messages.csv | external_message_id, external_thread_id, customer_alias, role, content, created_at, product_external_id |
| shop_policies.json | shipping, returns, warranty, general_faq |

`active`: true/false. `role`: customer/seller. Giá, tổng tiền, tồn kho và ngưỡng
là số nguyên không âm; quantity là số nguyên dương. Timestamp ISO 8601 có timezone,
normalize UTC. External IDs dùng để upsert; kiểm tra FK và duplicate SKU trước khi ghi.

Low stock khi `stock <= low_stock_threshold`. Giá trị đơn đủ điều kiện = sum total_vnd
của đơn paid và không cancelled/returned. Không gọi metric này là lợi nhuận.

12 bảng dự kiến: shops, products, variants, orders, order_items, conversations,
messages, shop_policies, alerts, action_proposals, agent_runs, import_batches.
Chi tiết cột tại [master plan mục 6](SHIPCODE_MASTER_PLAN.md); chưa tạo bảng ở Phase 1.

`frontend/src/data/demo.ts` chứa display models của UI cũ (giá dạng text, id dạng string).
Đây không phải DTO cho DB/API. Phase 2 sẽ thêm schema Pydantic và TypeScript DTO nhất quán.
