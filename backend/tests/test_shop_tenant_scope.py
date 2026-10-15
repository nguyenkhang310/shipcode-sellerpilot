import sqlite3
from datetime import date

import pytest

from app.integrations.ute_mall import ShopItemNotFoundError, UTEMallRepository


def build_marketplace(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            '''
            CREATE TABLE shop (id INTEGER PRIMARY KEY, slug TEXT, status TEXT);
            CREATE TABLE product (
              id INTEGER PRIMARY KEY, shop_id INTEGER, sku TEXT, name TEXT,
              price REAL, old_price REAL, stock INTEGER, status TEXT
            );
            CREATE TABLE product_variant (
              id INTEGER PRIMARY KEY, product_id INTEGER, sku TEXT, title TEXT,
              size TEXT, color TEXT, price REAL, old_price REAL, stock INTEGER, is_active INTEGER
            );
            CREATE TABLE "order" (
              id INTEGER PRIMARY KEY, shop_id INTEGER, total_amount REAL,
              status TEXT, created_at TEXT
            );
            CREATE TABLE order_item (
              id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER,
              quantity INTEGER, price REAL
            );
            INSERT INTO shop VALUES (1, 'utech-official', 'active'), (2, 'other-shop', 'active');
            INSERT INTO product VALUES
              (1, 1, 'UT-P1', 'UTech keyboard', 500000, NULL, 9, 'active'),
              (2, 2, 'OTHER-P1', 'Other keyboard', 400000, NULL, 2, 'active');
            INSERT INTO product_variant VALUES
              (1, 1, 'UT-V1', 'Standard', NULL, NULL, 500000, NULL, 9, 1),
              (2, 2, 'OTHER-V1', 'Standard', NULL, NULL, 400000, NULL, 2, 1);
            INSERT INTO "order" VALUES
              (1, 1, 700000, 'pending', '2026-10-14 18:00:00'),
              (2, 2, 900000, 'pending', '2026-10-14 19:00:00');
            '''
        )


def test_repository_is_scoped_to_configured_seller(tmp_path):
    path = tmp_path / 'marketplace.db'
    build_marketplace(path)
    repository = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')

    assert repository.get_item_by_sku('UT-V1')['product_name'] == 'UTech keyboard'
    with pytest.raises(ShopItemNotFoundError):
        repository.get_item_by_sku('OTHER-V1')

    summary = repository.summary(date(2026, 10, 15))
    assert summary['order_count'] == 1
    assert summary['revenue_vnd'] == 700000

    with pytest.raises(ShopItemNotFoundError):
        repository.apply_price_change(
            target_kind='variant', product_id=2, variant_id=2,
            expected_price_vnd=400000, new_price_vnd=350000,
        )
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT price FROM product_variant WHERE id=2').fetchone()[0] == 400000


def test_marketplace_missing_tenant_column_never_falls_back_to_all_shops(tmp_path):
    from app.integrations.ute_mall import ShopDatabaseError
    path = tmp_path / 'broken-marketplace.db'
    build_marketplace(path)
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE product RENAME COLUMN shop_id TO missing_shop_id')
    repository = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    with pytest.raises(ShopDatabaseError):
        repository.summary(date(2026, 10, 15))
