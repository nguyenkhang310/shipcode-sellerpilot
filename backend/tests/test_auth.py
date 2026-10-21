import sqlite3
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from app.models.auth import SellerSession
from test_product_drafts import make_client, OfflineProvider

PASSWORD = 'Correct-Password-2026!'


@pytest.fixture
def secured(tmp_path):
    client, path, _ = make_client(tmp_path)
    client.app.dependency_overrides.clear()  # Exercise the real security boundary.
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE user(id INTEGER PRIMARY KEY,username TEXT,email TEXT,password_hash TEXT,role TEXT);
            CREATE TABLE shop_member(id INTEGER PRIMARY KEY,user_id INTEGER,shop_id INTEGER,role TEXT);''')
        digest = generate_password_hash(PASSWORD, method='pbkdf2:sha256:600000')
        db.executemany('INSERT INTO user VALUES(?,?,?,?,?)', [(1,'seller','seller@example.test',digest,'user'),(2,'buyer','buyer@example.test',digest,'user'),(3,'reviewer','reviewer@example.test',digest,'demo_reviewer')])
        db.executemany('INSERT INTO shop_member VALUES(?,?,1,?)', [(1,1,'owner'),(2,3,'owner')])
    with client:
        client.app.state.ai_provider = OfflineProvider()
        yield client, path


def sign_in(client, login='seller', password=PASSWORD):
    return client.post('/api/v1/auth/login', json={'login_id': login, 'password': password})


@pytest.mark.parametrize('method,path,body', [
    ('GET','/management/dashboard',None), ('GET','/management/products',None),('GET','/management/orders',None),
    ('GET','/inventory/SEED-PHONE',None),('GET','/shop/summary',None),('GET','/conversations',None),
    ('GET','/product-drafts/1/image',None), ('POST','/chat',{'message':'xem doanh thu'}),
    ('POST','/proposals/1/reject',None), ('PATCH','/management/orders/1',{}),
])
def test_all_business_routes_reject_unauthenticated_access(secured, method, path, body):
    client, _ = secured
    result = client.request(method,'/api/v1'+path,json=body)
    assert result.status_code == 401, result.text
    assert result.headers['cache-control'] == 'no-store'


def test_existing_seller_credentials_create_hashed_session_and_logout_revokes_it(secured):
    client, _ = secured
    response = sign_in(client, 'SELLER@EXAMPLE.TEST')
    assert response.status_code == 200, response.text
    data = response.json()['data']; token = data['token']
    assert 'password' not in response.text and 'password_hash' not in response.text
    headers={'Authorization':'Bearer '+token}
    assert client.get('/api/v1/management/products',headers=headers).status_code == 200
    assert client.get('/api/v1/auth/me',headers=headers).json()['data']['user']['id'] == 1
    with client.app.state.session_factory() as session:
        stored=session.scalar(select(SellerSession))
        assert stored.token_hash != token and len(stored.token_hash) == 64
    assert client.post('/api/v1/auth/logout',headers=headers).status_code == 200
    assert client.get('/api/v1/management/products',headers=headers).status_code == 401


def test_buyer_reviewer_and_wrong_password_cannot_open_shop(secured):
    client, _ = secured
    assert sign_in(client, password='wrong').status_code == 401
    assert sign_in(client, login='missing').status_code == 401
    assert sign_in(client, login='buyer').status_code == 403
    assert sign_in(client, login='reviewer').status_code == 401


@pytest.mark.parametrize('change', ['password','membership','expiry'])
def test_changed_credentials_removed_membership_and_expiry_invalidate_session(secured, change):
    client, path = secured
    token=sign_in(client).json()['data']['token']
    if change == 'expiry':
        with client.app.state.session_factory() as session:
            session.scalar(select(SellerSession)).expires_at=datetime.utcnow()-timedelta(seconds=1);session.commit()
    else:
        with sqlite3.connect(path) as db:
            if change == 'password': db.execute("UPDATE user SET password_hash='changed' WHERE id=1")
            else: db.execute('DELETE FROM shop_member WHERE user_id=1')
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+token}).status_code == 401


def test_login_throttle_is_durable_and_case_insensitive(secured):
    client, _ = secured
    for _ in range(10): assert sign_in(client,password='wrong').status_code == 401
    blocked=sign_in(client,login='SELLER',password='wrong')
    assert blocked.status_code == 429 and blocked.headers['retry-after'] == '900'


def test_unpublished_upload_is_not_available_from_public_static_mount(secured, tmp_path):
    client, path = secured
    folder = client.app.state.settings.shop_static_dir/'uploads/sellerpilot'
    assert tmp_path in folder.parents
    folder.mkdir(parents=True)
    (folder/'private.png').write_bytes(b'private draft')
    assert client.get('/store-static/uploads/sellerpilot/private.png').status_code == 404
    with sqlite3.connect(path) as db:
        db.execute("UPDATE product SET image_url='/static/uploads/sellerpilot/private.png' WHERE id=1")
    assert client.get('/store-static/uploads/sellerpilot/private.png').content == b'private draft'
