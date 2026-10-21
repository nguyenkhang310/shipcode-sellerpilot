import sqlite3
import pytest
from werkzeug.security import check_password_hash
from app.scripts.reset_password import reset_password
from test_auth import secured, sign_in, PASSWORD


def test_owner_recovery_preserves_orders_and_rejects_old_session(secured):
    client, path = secured
    token = sign_in(client).json()['data']['token']
    with sqlite3.connect(path) as db:
        count = db.execute('SELECT count(*) FROM "order"').fetchone()[0]
    new_password = 'A-new-private-password!'
    assert reset_password(client.app.state.shop_repository, 'seller', new_password, new_password) == 'seller'
    assert sign_in(client).status_code == 401
    assert sign_in(client, password=new_password).status_code == 200
    assert client.get('/api/v1/auth/me', headers={'Authorization': 'Bearer '+token}).status_code == 401
    with sqlite3.connect(path) as db:
        digest = db.execute('SELECT password_hash FROM user WHERE id=1').fetchone()[0]
        assert check_password_hash(digest, new_password) and digest != new_password
        assert db.execute('SELECT count(*) FROM "order"').fetchone()[0] == count


@pytest.mark.parametrize('username,password,confirmation', [('buyer',PASSWORD,PASSWORD),('reviewer',PASSWORD,PASSWORD),('seller','short','short'),('seller',PASSWORD,'different')])
def test_invalid_recovery_leaves_credentials_unchanged(secured, username, password, confirmation):
    client, _ = secured
    with pytest.raises(ValueError): reset_password(client.app.state.shop_repository, username, password, confirmation)
    assert sign_in(client).status_code == 200
