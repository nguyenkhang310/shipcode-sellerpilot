import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.ai.contracts import AIProviderError, ProviderHealth
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app
import app.models  # noqa: F401


class OfflineProvider:
    async def check_health(self):
        return ProviderHealth(availability="unavailable")

    async def classify(self, _message, *, today):
        raise AIProviderError("provider_unavailable")


@pytest.fixture
def shop_db_path(tmp_path):
    database_path = tmp_path / "shop.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE product (
                id INTEGER PRIMARY KEY,
                sku TEXT UNIQUE,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                old_price REAL,
                stock INTEGER NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE product_variant (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                size TEXT,
                color TEXT,
                price REAL NOT NULL,
                old_price REAL,
                stock INTEGER NOT NULL,
                is_active INTEGER NOT NULL,
                FOREIGN KEY(product_id) REFERENCES product(id)
            );
            CREATE TABLE "order" (
                id INTEGER PRIMARY KEY,
                total_amount REAL NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE order_item (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL
            );

            INSERT INTO product VALUES (1, 'P001', 'Áo thun trơn', 150000, NULL, 4, 'active');
            INSERT INTO product VALUES (2, 'P002', 'Giày thể thao', 150000, NULL, 13, 'active');
            INSERT INTO product_variant VALUES
                (1, 2, 'A001', 'Đen / 40', '40', 'Đen', 150000, NULL, 3, 1),
                (2, 2, 'A002', 'Trắng / 41', '41', 'Trắng', 200000, NULL, 10, 1);

            INSERT INTO "order" VALUES
                (1, 100000, 'pending',   '2026-10-14 17:00:00'),
                (2, 200000, 'delivered', '2026-10-15 16:59:59'),
                (3, 999000, 'cancelled', '2026-10-15 05:00:00'),
                (4, 50000,  'pending',   '2026-10-14 16:59:59');
            """
        )
    return database_path


@pytest.fixture
def client(shop_db_path, tmp_path):
    agent_db_path = tmp_path / "agent.db"
    shop_static_dir = tmp_path / "shop-static"
    (shop_static_dir / "catalog").mkdir(parents=True)
    (shop_static_dir / "catalog" / "sample.png").write_bytes(b"sellerpilot-image")
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{agent_db_path}",
        shop_database_path=shop_db_path,
        shop_static_dir=shop_static_dir,
    )
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)
    from auth_fixture import authenticated_fixture
    authenticated_fixture(app)
    with TestClient(app) as test_client:
        app.state.ai_provider = OfflineProvider()
        yield test_client
