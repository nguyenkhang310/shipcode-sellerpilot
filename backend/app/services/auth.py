"""Existing seller credentials; opaque, hashed and revocable API sessions."""
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text, update
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.db.session import get_session
from app.integrations.ute_mall import ShopDatabaseError
from app.models.auth import SellerSession, LoginAttempt

DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(32), method='pbkdf2:sha256:600000')
bearer_session = HTTPBearer(auto_error=False, scheme_name='SellerSession')


def hash_token(value):
    return hashlib.sha256(value.encode()).hexdigest()


def denied(code='not_authenticated', message='Vui lòng đăng nhập để truy cập shop.'):
    return HTTPException(401, detail={'code': code, 'message': message}, headers={'WWW-Authenticate':'Bearer'})


def seller_user(shop, *, user_id=None, login_id=None):
    try:
        with shop._connect() as connection:
            if login_id is not None:
                rows = connection.execute('SELECT id,username,email,password_hash,role FROM user WHERE lower(username)=? OR lower(email)=? LIMIT 2', (login_id.lower(), login_id.lower())).fetchall()
                user = rows[0] if len(rows) == 1 else None
            else:
                user = connection.execute('SELECT id,username,email,password_hash,role FROM user WHERE id=?', (user_id,)).fetchone()
            if not user or user['role'] == 'demo_reviewer': return None
            member = connection.execute('''SELECT s.slug,s.name,m.role FROM shop_member m
                JOIN shop s ON s.id=m.shop_id WHERE m.user_id=? AND s.slug=? AND s.status='active' ''',
                (user['id'], shop.seller_shop_slug)).fetchone()
            return {**dict(user), 'membership': dict(member) if member else None}
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot verify seller account') from error


def identity(user, expires_at):
    return {'user': {'id': user['id'], 'username': user['username'], 'email': user['email']},
            'shop': {'slug': user['membership']['slug'], 'name': user['membership']['name'], 'role': user['membership']['role']},
            'expires_at': expires_at.isoformat() + 'Z'}


def throttle(session, login_id, host):
    now = datetime.utcnow()
    # Serialize counters before doing expensive password verification. The
    # project ledger is SQLite; the lock is released before hashing passwords.
    if session.bind.dialect.name == 'sqlite': session.execute(text('BEGIN IMMEDIATE'))
    blocked = False
    for name, limit in [('login:' + login_id.casefold(), 10), ('host:' + host, 60)]:
        key = hash_token(name)
        row = session.get(LoginAttempt, key)
        if row is None:
            session.add(LoginAttempt(key=key, started_at=now, count=1))
        elif now - row.started_at >= timedelta(minutes=15):
            row.started_at, row.count = now, 1
        else:
            row.count += 1
            blocked = blocked or row.count > limit
    session.commit()
    if blocked:
        raise HTTPException(429, detail={'code':'login_rate_limited','message':'Bạn đã thử đăng nhập nhiều lần. Vui lòng thử lại sau 15 phút.'}, headers={'Retry-After':'900'})


def login(request, session, login_id, password):
    throttle(session, login_id, request.client.host if request.client else 'unknown')
    shop = request.app.state.shop_repository
    try:
        user = seller_user(shop, login_id=login_id)
        valid = check_password_hash(user['password_hash'] if user else DUMMY_HASH, password)
    except ShopDatabaseError as error:
        raise HTTPException(503, detail='Chưa kết nối được hệ thống tài khoản. Vui lòng thử lại.') from error
    except (ValueError, TypeError):
        valid = False
    if not valid or not user:
        raise denied('invalid_credentials', 'Tên đăng nhập hoặc mật khẩu chưa đúng.')
    if not user['membership']:
        raise HTTPException(403, detail='Tài khoản chưa có quyền quản lý shop đang liên kết.')
    token = secrets.token_urlsafe(32)
    now, expires = datetime.utcnow(), datetime.utcnow() + timedelta(days=7)
    session.add(SellerSession(token_hash=hash_token(token), user_id=user['id'], shop_slug=shop.seller_shop_slug,
        credential_tag=hash_token(user['password_hash']), created_at=now, expires_at=expires))
    session.commit()
    return {**identity(user, expires), 'token': token}


def require_seller(request: Request, session: Session = Depends(get_session),
                   credentials: HTTPAuthorizationCredentials | None = Depends(bearer_session)):
    if not credentials or not 30 <= len(credentials.credentials) <= 128:
        raise denied()
    record = session.get(SellerSession, hash_token(credentials.credentials))
    if not record or record.revoked_at or record.expires_at <= datetime.utcnow():
        raise denied('session_expired', 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
    shop = request.app.state.shop_repository
    try:
        user = seller_user(shop, user_id=record.user_id)
    except ShopDatabaseError as error:
        raise HTTPException(503, detail='Chưa kiểm tra được quyền truy cập shop.') from error
    if (record.shop_slug != shop.seller_shop_slug or not user or not user['membership']
            or not secrets.compare_digest(record.credential_tag, hash_token(user['password_hash']))):
        raise denied('session_revoked', 'Quyền truy cập đã thay đổi. Vui lòng đăng nhập lại.')
    request.state.seller_session = record
    return identity(user, record.expires_at)


def revoke(session, record, all_sessions=False):
    query = update(SellerSession).where(SellerSession.user_id == record.user_id, SellerSession.shop_slug == record.shop_slug)
    if not all_sessions: query = query.where(SellerSession.token_hash == record.token_hash)
    session.execute(query.values(revoked_at=datetime.utcnow()))
    session.commit()
