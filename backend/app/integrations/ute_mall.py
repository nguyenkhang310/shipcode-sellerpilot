import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ShopDatabaseError(RuntimeError):
    pass


class ShopItemNotFoundError(LookupError):
    pass


class StaleShopPriceError(RuntimeError):
    def __init__(self, current_price_vnd: int):
        super().__init__("Shop price changed after the proposal was created")
        self.current_price_vnd = current_price_vnd


class ProductPublishConflictError(RuntimeError):
    pass


class UTEMallRepository:
    """Restricted gateway to the existing UTE MALL SQLite database."""

    def __init__(self, database_path: Path, timezone_name: str, seller_shop_slug: str | None = None):
        self.database_path = Path(database_path).expanduser().resolve()
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown shop timezone: {timezone_name}") from error
        self.timezone_name = timezone_name
        self.seller_shop_slug = (seller_shop_slug or '').strip() or None

    def _resolve_shop_id(self, connection: sqlite3.Connection) -> int | None:
        """Resolve the configured seller tenant; old single-shop test DBs stay compatible."""
        tables = {row['name'] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'shop' not in tables:
            return None
        product_columns = {row['name'] for row in connection.execute('PRAGMA table_info(product)')}
        if 'shop_id' not in product_columns:
            raise ShopDatabaseError('Missing product tenant column in marketplace database')
        if not self.seller_shop_slug:
            raise ShopDatabaseError('Seller shop slug is required for a marketplace database')
        row = connection.execute(
            "SELECT id FROM shop WHERE slug = ? AND status = 'active' LIMIT 1",
            (self.seller_shop_slug,),
        ).fetchone()
        if not row:
            raise ShopDatabaseError(f"Seller shop does not exist: {self.seller_shop_slug}")
        return int(row['id'])

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self.database_path.is_file():
            raise ShopDatabaseError(f"Shop database does not exist: {self.database_path}")
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def ping(self) -> None:
        try:
            with self._connect() as connection:
                tables = {
                    row["name"]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                        "('product', 'product_variant', 'order', 'order_item')"
                    )
                }
            if tables != {"product", "product_variant", "order", "order_item"}:
                raise ShopDatabaseError("Shop database schema is incomplete")
            with self._connect() as connection:
                self._resolve_shop_id(connection)
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot read shop database") from error

    def summary(self, local_day: date, *, as_of: datetime | None = None) -> dict:
        start_local = datetime.combine(local_day, time.min, tzinfo=self.timezone)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
        if as_of is not None:
            end_utc = min(end_utc, as_of.astimezone(timezone.utc).replace(tzinfo=None))

        try:
            with self._connect() as connection:
                shop_id = self._resolve_shop_id(connection)
                order_columns = {row['name'] for row in connection.execute('PRAGMA table_info("order")')}
                if shop_id is not None and 'shop_id' not in order_columns:
                    raise ShopDatabaseError('Missing order tenant column')
                shop_filter = ' AND shop_id = ?' if shop_id is not None and 'shop_id' in order_columns else ''
                params = [start_utc.isoformat(sep=" "), end_utc.isoformat(sep=" ")]
                if shop_filter:
                    params.append(shop_id)
                rows = connection.execute(
                    f"""
                    SELECT status, COUNT(*) AS order_count,
                           COALESCE(SUM(total_amount), 0) AS order_value
                    FROM "order"
                    WHERE created_at >= ? AND created_at < ?
                    {shop_filter}
                    GROUP BY status
                    """,
                    tuple(params),
                ).fetchall()
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot calculate shop summary") from error

        status_counts = {str(row["status"]): int(row["order_count"]) for row in rows}
        active_rows = [row for row in rows if row["status"] not in {"cancelled", "returned"}]
        return {
            "date": local_day.isoformat(),
            "timezone": self.timezone_name,
            "order_count": sum(int(row["order_count"]) for row in active_rows),
            "revenue_vnd": int(round(sum(float(row["order_value"]) for row in active_rows))),
            "pending_count": status_counts.get("pending", 0),
            "cancelled_count": status_counts.get("cancelled", 0),
            "status_counts": status_counts,
        }

    def get_item_by_sku(self, sku: str) -> dict:
        normalized_sku = sku.strip()
        try:
            with self._connect() as connection:
                shop_id = self._resolve_shop_id(connection)
                shop_filter = ' AND p.shop_id = ?' if shop_id is not None else ''
                sku_params = (normalized_sku, shop_id) if shop_id is not None else (normalized_sku,)
                variant = connection.execute(
                    f"""
                    SELECT v.id AS variant_id, v.product_id, v.sku, v.title AS variant_title,
                           v.size, v.color, v.price, v.stock, v.is_active,
                           p.name AS product_name, p.status AS product_status
                    FROM product_variant v
                    JOIN product p ON p.id = v.product_id
                    WHERE UPPER(v.sku) = UPPER(?)
                    {shop_filter}
                    LIMIT 1
                    """,
                    sku_params,
                ).fetchone()
                if variant:
                    return self._variant_to_dict(variant)

                product = connection.execute(
                    f"""
                    SELECT p.id AS product_id, p.sku, p.name AS product_name,
                           p.price, p.stock, p.status,
                           COUNT(v.id) AS variant_count,
                           COALESCE(SUM(CASE WHEN v.is_active = 1 THEN v.stock ELSE 0 END), p.stock) AS total_stock
                    FROM product p
                    LEFT JOIN product_variant v ON v.product_id = p.id
                    WHERE UPPER(p.sku) = UPPER(?)
                    {shop_filter}
                    GROUP BY p.id
                    LIMIT 1
                    """,
                    sku_params,
                ).fetchone()
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot read shop inventory") from error

        if not product:
            raise ShopItemNotFoundError(normalized_sku)
        return {
            "target_kind": "product",
            "product_id": int(product["product_id"]),
            "variant_id": None,
            "sku": str(product["sku"]),
            "product_name": str(product["product_name"]),
            "variant_title": None,
            "size": None,
            "color": None,
            "price_vnd": int(round(float(product["price"]))),
            "stock": int(product["total_stock"] if product["variant_count"] else product["stock"]),
            "is_active": product["status"] == "active",
        }

    def inventory_overview(self, low_stock_threshold: int = 5) -> dict:
        """Summarize active inventory for one seller without double-counting variants."""
        try:
            with self._connect() as connection:
                shop_id = self._resolve_shop_id(connection)
                shop_filter = " AND p.shop_id = ?" if shop_id is not None else ""
                params = (shop_id,) if shop_id is not None else ()
                product_count = connection.execute(
                    f"SELECT COUNT(*) FROM product p WHERE p.status = 'active'{shop_filter}",
                    params,
                ).fetchone()[0]
                row = connection.execute(
                    f"""
                    WITH inventory AS (
                        SELECT v.sku, v.stock, v.price
                        FROM product_variant v
                        JOIN product p ON p.id = v.product_id
                        WHERE p.status = 'active' AND v.is_active = 1{shop_filter}

                        UNION ALL

                        SELECT p.sku, p.stock, p.price
                        FROM product p
                        WHERE p.status = 'active'
                          AND p.sku IS NOT NULL AND p.sku != ''{shop_filter}
                          AND NOT EXISTS (
                              SELECT 1 FROM product_variant v WHERE v.product_id = p.id
                          )
                    )
                    SELECT COUNT(*) AS sku_count,
                           COALESCE(SUM(stock), 0) AS unit_count,
                           COALESCE(SUM(CASE WHEN stock = 0 THEN 1 ELSE 0 END), 0) AS out_of_stock_count,
                           COALESCE(SUM(CASE WHEN stock > 0 AND stock <= ? THEN 1 ELSE 0 END), 0) AS low_stock_count,
                           COALESCE(SUM(price * stock), 0) AS retail_value_vnd
                    FROM inventory
                    """,
                    (*params, *params, low_stock_threshold),
                ).fetchone()
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot summarize shop inventory") from error

        return {
            "active_product_count": int(product_count),
            "sku_count": int(row["sku_count"]),
            "unit_count": int(row["unit_count"]),
            "low_stock_threshold": low_stock_threshold,
            "low_stock_count": int(row["low_stock_count"]),
            "out_of_stock_count": int(row["out_of_stock_count"]),
            "retail_value_vnd": int(round(float(row["retail_value_vnd"]))),
        }

    def product_categories(self) -> list[dict]:
        """Return every marketplace root category available to this seller.

        A shop may expand into a category it has not listed in before, so the
        composer must not derive its choices from the shop's existing catalog.
        """
        try:
            with self._connect() as connection:
                self._resolve_shop_id(connection)
                category_columns = {
                    row["name"] for row in connection.execute("PRAGMA table_info(category)")
                }
                root_filter = "WHERE parent_id IS NULL" if "parent_id" in category_columns else ""
                order = "display_order, id" if "display_order" in category_columns else "id"
                rows = connection.execute(
                    f"SELECT id, name FROM category {root_filter} ORDER BY {order}"
                ).fetchall()
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot read product categories") from error
        return [{"id": int(row["id"]), "name": str(row["name"])} for row in rows]

    def publish_product(
        self,
        *,
        draft_id: int,
        name: str,
        description: str,
        category_id: int,
        price_vnd: int,
        stock: int,
        sku: str,
        image_urls: list[str],
    ) -> int:
        """Publish one standard-variant product to the connected seller shop."""
        source_id = f"sellerpilot-draft:{draft_id}"
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                shop_id = self._resolve_shop_id(connection)
                if shop_id is None:
                    raise ShopDatabaseError("Publishing requires a marketplace seller shop")
                existing = connection.execute(
                    "SELECT id, source_id FROM product WHERE UPPER(sku)=UPPER(?) LIMIT 1",
                    (sku,),
                ).fetchone()
                if existing:
                    if existing["source_id"] == source_id:
                        connection.commit()
                        return int(existing["id"])
                    raise ProductPublishConflictError("SKU already exists")
                if connection.execute(
                    "SELECT 1 FROM product_variant WHERE UPPER(sku)=UPPER(?) LIMIT 1", (sku,)
                ).fetchone():
                    raise ProductPublishConflictError("SKU already exists")
                category = connection.execute(
                    "SELECT id FROM category WHERE id=? LIMIT 1", (category_id,)
                ).fetchone()
                if not category:
                    raise ProductPublishConflictError("Category no longer exists")
                shop = connection.execute(
                    "SELECT location FROM shop WHERE id=? AND status='active'", (shop_id,)
                ).fetchone()
                if not shop:
                    raise ProductPublishConflictError("Shop is not active")
                now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
                slug = f"utech-sellerpilot-{draft_id}-{sku.lower()}"
                primary_image_url = image_urls[0] if image_urls else ""
                extra_images = json.dumps(image_urls[1:], ensure_ascii=False) if len(image_urls) > 1 else None
                cursor = connection.execute(
                    """
                    INSERT INTO product (
                        name, description, price, old_price, image_url, extra_images, category_id,
                        is_new, is_on_sale, stock, created_at, sku, slug, source,
                        source_id, currency, rating, rating_count, status, shop_id,
                        sold_count, historical_sold_count, location, is_featured
                    ) VALUES (?, ?, ?, NULL, ?, ?, ?, 1, 0, ?, ?, ?, ?, 'sellerpilot',
                              ?, 'VND', 0, 0, 'active', ?, 0, 0, ?, 0)
                    """,
                    (name, description, price_vnd, primary_image_url, extra_images, category_id, stock, now,
                     sku, slug, source_id, shop_id, shop["location"]),
                )
                product_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO product_variant (
                        product_id, sku, title, price, old_price, stock, is_active
                    ) VALUES (?, ?, 'Phiên bản tiêu chuẩn', ?, NULL, ?, 1)
                    """,
                    (product_id, sku, price_vnd, stock),
                )
                tables = {row["name"] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                if "seller_activity" in tables:
                    connection.execute(
                        "INSERT INTO seller_activity (shop_id, user_id, action, created_at) VALUES (?, NULL, ?, ?)",
                        (shop_id, f"SellerPilot đăng sản phẩm: {name}"[:500], now),
                    )
                connection.commit()
                return product_id
        except ProductPublishConflictError:
            raise
        except sqlite3.IntegrityError as error:
            raise ProductPublishConflictError("Product data changed before publishing") from error
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot publish product") from error

    def low_stock(self, threshold: int, limit: int) -> list[dict]:
        try:
            with self._connect() as connection:
                shop_id = self._resolve_shop_id(connection)
                shop_filter = ' AND p.shop_id = ?' if shop_id is not None else ''
                variant_params = (threshold, shop_id, limit) if shop_id is not None else (threshold, limit)
                variants = connection.execute(
                    f"""
                    SELECT v.id AS variant_id, v.product_id, v.sku, v.title AS variant_title,
                           v.size, v.color, v.price, v.stock, v.is_active,
                           p.name AS product_name, p.status AS product_status
                    FROM product_variant v
                    JOIN product p ON p.id = v.product_id
                    WHERE v.is_active = 1 AND p.status = 'active' AND v.stock <= ?
                    {shop_filter}
                    ORDER BY v.stock ASC, p.name ASC, v.sku ASC
                    LIMIT ?
                    """,
                    variant_params,
                ).fetchall()
                remaining = max(0, limit - len(variants))
                product_params = (threshold, shop_id, remaining) if shop_id is not None else (threshold, remaining)
                products = connection.execute(
                    f"""
                    SELECT p.id AS product_id, p.sku, p.name AS product_name,
                           p.price, p.stock, p.status
                    FROM product p
                    WHERE p.status = 'active' AND p.sku IS NOT NULL AND p.sku != ''
                      AND p.stock <= ?
                      {shop_filter}
                      AND NOT EXISTS (SELECT 1 FROM product_variant v WHERE v.product_id = p.id)
                    ORDER BY p.stock ASC, p.name ASC, p.sku ASC
                    LIMIT ?
                    """,
                    product_params,
                ).fetchall() if remaining else []
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot read low stock inventory") from error

        items = [self._variant_to_dict(row) for row in variants]
        items.extend({
            "target_kind": "product",
            "product_id": int(row["product_id"]),
            "variant_id": None,
            "sku": str(row["sku"]),
            "product_name": str(row["product_name"]),
            "variant_title": None,
            "size": None,
            "color": None,
            "price_vnd": int(round(float(row["price"]))),
            "stock": int(row["stock"]),
            "is_active": row["status"] == "active",
        } for row in products)
        return items

    def apply_price_change(
        self,
        *,
        target_kind: str,
        product_id: int,
        variant_id: int | None,
        expected_price_vnd: int,
        new_price_vnd: int,
    ) -> None:
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                shop_id = self._resolve_shop_id(connection)
                if target_kind == "variant" and variant_id is not None:
                    variant_filter = ' AND p.shop_id = ?' if shop_id is not None else ''
                    variant_params = (variant_id, product_id, shop_id) if shop_id is not None else (variant_id, product_id)
                    row = connection.execute(
                        f"SELECT v.price FROM product_variant v JOIN product p ON p.id=v.product_id WHERE v.id = ? AND v.product_id = ?{variant_filter}",
                        variant_params,
                    ).fetchone()
                    if not row:
                        raise ShopItemNotFoundError(str(variant_id))
                    current = int(round(float(row["price"])))
                    if current != expected_price_vnd:
                        raise StaleShopPriceError(current)
                    connection.execute(
                        "UPDATE product_variant SET old_price = price, price = ? WHERE id = ?",
                        (new_price_vnd, variant_id),
                    )
                    connection.execute(
                        """
                        UPDATE product
                        SET price = (
                            SELECT MIN(price) FROM product_variant
                            WHERE product_id = ? AND is_active = 1
                        )
                        WHERE id = ?
                        """,
                        (product_id, product_id),
                    )
                elif target_kind == "product":
                    product_filter = ' AND shop_id = ?' if shop_id is not None else ''
                    product_params = (product_id, shop_id) if shop_id is not None else (product_id,)
                    row = connection.execute(
                        f"SELECT price FROM product WHERE id = ?{product_filter}", product_params,
                    ).fetchone()
                    if not row:
                        raise ShopItemNotFoundError(str(product_id))
                    current = int(round(float(row["price"])))
                    if current != expected_price_vnd:
                        raise StaleShopPriceError(current)
                    connection.execute(
                        "UPDATE product SET old_price = price, price = ? WHERE id = ?",
                        (new_price_vnd, product_id),
                    )
                else:
                    raise ShopDatabaseError("Invalid price target")
                connection.commit()
        except (ShopItemNotFoundError, StaleShopPriceError, ShopDatabaseError):
            raise
        except sqlite3.Error as error:
            raise ShopDatabaseError("Cannot update shop price") from error

    @staticmethod
    def _variant_to_dict(row: sqlite3.Row) -> dict:
        return {
            "target_kind": "variant",
            "product_id": int(row["product_id"]),
            "variant_id": int(row["variant_id"]),
            "sku": str(row["sku"]),
            "product_name": str(row["product_name"]),
            "variant_title": str(row["variant_title"]),
            "size": row["size"],
            "color": row["color"],
            "price_vnd": int(round(float(row["price"]))),
            "stock": int(row["stock"]),
            "is_active": bool(row["is_active"]) and row["product_status"] == "active",
        }
