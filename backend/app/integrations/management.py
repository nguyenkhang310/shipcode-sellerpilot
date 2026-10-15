"""Read models shared by the mobile manager and the seller assistant."""
import sqlite3
import unicodedata
from datetime import datetime, time, timedelta, timezone

from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository


def _search_text(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold().replace("đ", "d"))
    return "".join(char for char in value if not unicodedata.combining(char))


def _literal_query(value):
    return "%" + _search_text(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _columns(connection, table):
    return {row["name"] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _scope(connection, shop, table, alias=""):
    shop_id = shop._resolve_shop_id(connection)
    if shop_id is None:
        return "1=1", []
    if "shop_id" not in _columns(connection, table):
        raise ShopDatabaseError("Missing tenant column")
    return f"{alias + '.' if alias else ''}shop_id = ?", [shop_id]


def _product_rows(connection, shop, query="", limit=20, offset=0, low=False):
    scope, params = _scope(connection, shop, "product", "p")
    columns = _columns(connection, "product")
    image = "p.image_url" if "image_url" in columns else "NULL"
    sold = "p.sold_count" if "sold_count" in columns else "0"
    rating = "p.rating" if "rating" in columns else "0"
    filters = [scope]
    if query:
        # Literal search; user text never becomes SQL.
        connection.create_function("search_text", 1, _search_text, deterministic=True)
        filters.append("(search_text(p.name) LIKE ? ESCAPE '\\' OR search_text(p.sku) LIKE ? ESCAPE '\\')")
        params += [_literal_query(query)] * 2
    if low:
        filters.append("p.stock <= 5 AND p.status = 'active'")
    where = " AND ".join(filters)
    total = connection.execute(f"SELECT COUNT(*) FROM product p WHERE {where}", params).fetchone()[0]
    rows = connection.execute(
        f"""SELECT p.id, p.name, p.sku, p.price AS price_vnd, p.stock, p.status,
                   {image} AS image_url, {sold} AS sold_count, {rating} AS rating
            FROM product p WHERE {where}
            ORDER BY p.stock ASC, p.id DESC LIMIT ? OFFSET ?""" if low else
        f"""SELECT p.id, p.name, p.sku, p.price AS price_vnd, p.stock, p.status,
                   {image} AS image_url, {sold} AS sold_count, {rating} AS rating
            FROM product p WHERE {where}
            ORDER BY sold_count DESC, p.id DESC LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}


def products(shop: UTEMallRepository, query="", limit=20, offset=0, low=False):
    try:
        with shop._connect() as connection:
            connection.execute("BEGIN")
            return _product_rows(connection, shop, query, limit, offset, low)
    except sqlite3.Error as error:
        raise ShopDatabaseError("Cannot read products") from error


def orders(shop: UTEMallRepository, status="all", query="", limit=20, offset=0):
    try:
        with shop._connect() as connection:
            connection.execute("BEGIN")
            scope, params = _scope(connection, shop, "order", "o")
            columns = _columns(connection, "order")
            name = "o.shipping_name" if "shipping_name" in columns else "'Khách hàng'"
            extra = ", ".join(f"o.{field}" if field in columns else f"NULL AS {field}" for field in
                              ("payment_method", "payment_status", "shipping_fee", "discount_amount"))
            filters = [scope]
            if status != "all":
                filters.append("o.status = ?")
                params.append(status)
            if query:
                connection.create_function("search_text", 1, _search_text, deterministic=True)
                filters.append(f"(CAST(o.id AS TEXT) = ? OR search_text({name}) LIKE ? ESCAPE '\\')")
                params += [query.lstrip("#"), _literal_query(query)]
            where = " AND ".join(filters)
            total = connection.execute(f'SELECT COUNT(*) FROM "order" o WHERE {where}', params).fetchone()[0]
            rows = connection.execute(
                f"""SELECT o.id, {name} AS customer_name, o.total_amount AS total_vnd,
                           o.status, o.created_at, {extra},
                           (SELECT COUNT(*) FROM order_item i WHERE i.order_id=o.id) AS item_count
                    FROM "order" o WHERE {where} ORDER BY o.created_at DESC, o.id DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
            result = [dict(row, items=[], quantity=0) for row in rows]
            if result:
                product_scope, product_params = _scope(connection, shop, "product", "p")
                product_columns = _columns(connection, "product")
                item_columns = _columns(connection, "order_item")
                image = "p.image_url" if "image_url" in product_columns else "NULL"
                variant = "i.variant_title" if "variant_title" in item_columns else "NULL"
                sku = "COALESCE(i.sku, p.sku)" if "sku" in item_columns else "p.sku"
                placeholders = ",".join("?" for _ in result)
                by_id = {row["id"]: row for row in result}
                # Read purchased prices, not today's catalogue price. Product metadata
                # may be missing after deletion; never join a different seller's product.
                for item in connection.execute(
                    f"""SELECT i.id, i.order_id, i.quantity, i.price AS price_vnd,
                               p.name, {sku} AS sku, {variant} AS variant_title, {image} AS image_url
                        FROM order_item i LEFT JOIN product p ON p.id=i.product_id AND {product_scope}
                        WHERE i.order_id IN ({placeholders}) ORDER BY i.id""",
                    [*product_params, *by_id],
                ):
                    order = by_id[item["order_id"]]
                    order["items"].append(dict(item))
                    order["quantity"] += item["quantity"]
            return {"items": result, "total": total, "offset": offset, "limit": limit}
    except sqlite3.Error as error:
        raise ShopDatabaseError("Cannot read orders") from error


def dashboard(shop: UTEMallRepository, days=7):
    """One tenant, VN calendar days, no orders dated in the future."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(shop.timezone).date()
    start_day = today - timedelta(days=days - 1)
    start = datetime.combine(start_day, time.min, tzinfo=shop.timezone).astimezone(timezone.utc)
    previous_start = start - timedelta(days=days)
    previous_end = previous_start + (now - start)
    try:
        with shop._connect() as connection:
            connection.execute("BEGIN")  # consistent read across dashboard counters
            scope, params = _scope(connection, shop, "order")
            rows = connection.execute(
                f'SELECT total_amount, status, created_at FROM "order" WHERE {scope} AND created_at>=? AND created_at<=?',
                [*params, previous_start.replace(tzinfo=None).isoformat(sep=" "), now.replace(tzinfo=None).isoformat(sep=" ")],
            ).fetchall()
            values = {(start_day + timedelta(days=i)).isoformat(): 0 for i in range(days)}
            hourly = {f"{today.isoformat()}T{hour:02d}:00": 0 for hour in range(now.astimezone(shop.timezone).hour + 1)}
            count = cancelled = delivered = previous = 0
            period_status_counts = {status: 0 for status in ("pending", "paid", "shipped", "delivered", "cancelled", "returned")}
            for row in rows:
                created = datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc)
                local_time = created.astimezone(shop.timezone)
                local_date = local_time.date().isoformat()
                valid = row["status"] not in ("cancelled", "returned")
                amount = round(row["total_amount"])
                if local_date in values:
                    period_status_counts[row["status"]] = period_status_counts.get(row["status"], 0) + 1
                    if valid:
                        count += 1
                        values[local_date] += amount
                        if local_date == today.isoformat():
                            hourly[local_time.strftime('%Y-%m-%dT%H:00')] += amount
                        if row["status"] == "delivered":
                            delivered += amount
                    else:
                        cancelled += 1
                elif valid and created <= previous_end:
                    previous += amount
            counts = {row["status"]: row["n"] for row in connection.execute(
                f'SELECT status, COUNT(*) n FROM "order" WHERE {scope} GROUP BY status', params,
            )}
            product_scope, product_params = _scope(connection, shop, "product")
            product_counts = {row["status"]: row["n"] for row in connection.execute(
                f"SELECT status, COUNT(*) n FROM product WHERE {product_scope} GROUP BY status", product_params,
            )}
            low_count = connection.execute(
                f"SELECT COUNT(*) FROM product WHERE {product_scope} AND status='active' AND stock<=5", product_params,
            ).fetchone()[0]
            tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            shop_id = shop._resolve_shop_id(connection)
            shop_row = connection.execute("SELECT * FROM shop WHERE id=?", (shop_id,)).fetchone() if shop_id else None
            info = dict(shop_row) if shop_row else {}
            review_count = 0
            if "review" in tables and "seller_reply" in _columns(connection, "review"):
                review_scope, review_params = _scope(connection, shop, "product", "p")
                review_count = connection.execute(
                    f"SELECT COUNT(*) FROM review r JOIN product p ON p.id=r.product_id WHERE {review_scope} AND r.seller_reply IS NULL", review_params,
                ).fetchone()[0]
            top = _product_rows(connection, shop, limit=5)["items"]
            total = sum(values.values())
            return {
                "shop": {"name": info.get("name", "UTech Official"), "slug": shop.seller_shop_slug or "utech-official",
                         "rating": info.get("rating", 0), "followers": info.get("follower_count", 0),
                         "location": info.get("location", ""), "vacation_mode": bool(info.get("vacation_mode", False))},
                "days": days, "from_date": start_day.isoformat(), "to_date": today.isoformat(),
                "updated_at": now.isoformat(), "timezone": shop.timezone_name,
                "order_value_vnd": total, "order_count": count, "delivered_value_vnd": delivered,
                "average_order_vnd": round(total / count) if count else 0,
                "cancelled_count": cancelled, "previous_value_vnd": previous,
                "change_percent": round((total - previous) / previous * 100, 1) if previous else None,
                "series": [{"date": day, "value": value} for day, value in (hourly if days == 1 else values).items()],
                "order_status_counts": period_status_counts,
                "tasks": {"pending_orders": counts.get("pending", 0), "packing_orders": counts.get("paid", 0),
                          "shipping_orders": counts.get("shipped", 0), "low_stock_products": low_count,
                          "unanswered_reviews": review_count},
                "active_products": product_counts.get("active", 0), "top_products": top,
                "integration_mode": "local_store",
            }
    except (sqlite3.Error, ValueError) as error:
        raise ShopDatabaseError("Cannot load management dashboard") from error
