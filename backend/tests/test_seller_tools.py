import sqlite3

from app.models.action import ActionAudit, ActionProposal


def test_summary_uses_vietnam_day_and_excludes_cancelled(client):
    response = client.get("/api/v1/shop/summary?date=2026-10-15")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "date": "2026-10-15",
        "timezone": "Asia/Ho_Chi_Minh",
        "order_count": 2,
        "revenue_vnd": 300000,
        "pending_count": 1,
        "cancelled_count": 1,
        "status_counts": {"cancelled": 1, "delivered": 1, "pending": 1},
    }


def test_inventory_lookup_and_low_stock(client):
    item = client.get("/api/v1/inventory/a001")
    assert item.status_code == 200
    assert item.json()["data"] == {
        "target_kind": "variant",
        "product_id": 2,
        "variant_id": 1,
        "sku": "A001",
        "product_name": "Giày thể thao",
        "variant_title": "Đen / 40",
        "size": "40",
        "color": "Đen",
        "price_vnd": 150000,
        "stock": 3,
        "is_active": True,
    }

    low_stock = client.get("/api/v1/inventory/low-stock?threshold=5").json()["data"]
    assert low_stock["count"] == 2
    assert {row["sku"] for row in low_stock["items"]} == {"A001", "P001"}


def test_price_change_requires_confirmation_and_is_idempotent(client, shop_db_path):
    created = client.post("/api/v1/proposals/price-change", json={
        "sku": "A001", "new_price_vnd": 120000,
    })
    assert created.status_code == 201
    proposal = created.json()["data"]
    assert proposal["status"] == "pending"
    assert proposal["old_price_vnd"] == 150000

    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute(
            "SELECT price FROM product_variant WHERE sku='A001'"
        ).fetchone()[0] == 150000

    confirmed = client.post(f"/api/v1/proposals/{proposal['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "approved"
    assert confirmed.json()["data"]["idempotent"] is False

    repeated = client.post(f"/api/v1/proposals/{proposal['id']}/confirm")
    assert repeated.status_code == 200
    assert repeated.json()["data"]["idempotent"] is True

    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute(
            "SELECT price FROM product_variant WHERE sku='A001'"
        ).fetchone()[0] == 120000
        assert connection.execute("SELECT price FROM product WHERE id=2").fetchone()[0] == 120000

    with client.app.state.session_factory() as session:
        assert session.query(ActionAudit).count() == 1


def test_reject_keeps_price_and_is_idempotent(client, shop_db_path):
    proposal = client.post("/api/v1/proposals/price-change", json={
        "sku": "P001", "new_price_vnd": 99000,
    }).json()["data"]

    rejected = client.post(f"/api/v1/proposals/{proposal['id']}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
    assert client.post(f"/api/v1/proposals/{proposal['id']}/reject").json()["data"]["idempotent"] is True
    assert client.post(f"/api/v1/proposals/{proposal['id']}/confirm").status_code == 409

    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute("SELECT price FROM product WHERE sku='P001'").fetchone()[0] == 150000


def test_stale_proposal_does_not_overwrite_newer_price(client, shop_db_path):
    proposal = client.post("/api/v1/proposals/price-change", json={
        "sku": "A002", "new_price_vnd": 180000,
    }).json()["data"]
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute("UPDATE product_variant SET price=190000 WHERE sku='A002'")

    response = client.post(f"/api/v1/proposals/{proposal['id']}/confirm")
    assert response.status_code == 409
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute(
            "SELECT price FROM product_variant WHERE sku='A002'"
        ).fetchone()[0] == 190000


def test_confirm_recovers_if_shop_write_finished_before_agent_commit(client, shop_db_path):
    proposal = client.post("/api/v1/proposals/price-change", json={
        "sku": "A001", "new_price_vnd": 120000,
    }).json()["data"]

    with client.app.state.session_factory() as session:
        stored = session.get(ActionProposal, proposal["id"])
        stored.status = "executing"
        session.commit()
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute("UPDATE product_variant SET price=120000 WHERE sku='A001'")

    recovered = client.post(f"/api/v1/proposals/{proposal['id']}/confirm")
    assert recovered.status_code == 200
    assert recovered.json()["data"]["status"] == "approved"
    assert recovered.json()["data"]["idempotent"] is True
    with client.app.state.session_factory() as session:
        assert session.query(ActionAudit).count() == 1


def test_invalid_price_and_missing_sku_do_not_create_proposal(client):
    assert client.post("/api/v1/proposals/price-change", json={
        "sku": "A001", "new_price_vnd": 0,
    }).status_code == 422
    assert client.post("/api/v1/proposals/price-change", json={
        "sku": "UNKNOWN", "new_price_vnd": 100000,
    }).status_code == 404


def test_proposal_id_cannot_target_another_product_or_leak_approved_data(client):
    proposal = client.post('/api/v1/proposals/price-change', json={'sku':'P001','new_price_vnd':99000}).json()['data']
    for state in ('pending', 'approved', 'rejected'):
        with client.app.state.session_factory() as session:
            record = session.get(ActionProposal, proposal['id'])
            record.product_id = 99999
            record.status = state
            session.commit()
        assert client.post(f"/api/v1/proposals/{proposal['id']}/confirm").status_code == 404
        assert client.post(f"/api/v1/proposals/{proposal['id']}/reject").status_code == 404
        with client.app.state.session_factory() as session:
            assert session.get(ActionProposal, proposal['id']).status == state
