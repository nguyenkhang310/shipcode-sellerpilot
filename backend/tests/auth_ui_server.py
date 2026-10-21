"""Disposable real-auth server for login UI; never opens the working shop."""
import sqlite3
import tempfile
from pathlib import Path
import uvicorn
from werkzeug.security import generate_password_hash
from fastapi import Request
from sqlalchemy import update
from datetime import datetime, timedelta
from test_product_drafts import make_client
from chat_reliability_server import qa_provider
from app.models.auth import SellerSession
import app.main

if __name__ == '__main__':
    app.main.create_provider = qa_provider
    with tempfile.TemporaryDirectory(prefix='sellerpilot-auth-ui-') as temporary:
        client, path, _ = make_client(Path(temporary))
        application = client.app
        application.dependency_overrides.clear()
        application.state.settings.cors_origins += ['http://127.0.0.1:5174']
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE user(id INTEGER PRIMARY KEY,username TEXT,email TEXT,password_hash TEXT,role TEXT); CREATE TABLE shop_member(id INTEGER PRIMARY KEY,user_id INTEGER,shop_id INTEGER,role TEXT);')
            db.execute('INSERT INTO user VALUES(1,?,?,?,?)',('qa-seller','qa@example.test',generate_password_hash('SellerPilot-QA!2026',method='pbkdf2:sha256:600000'),'user'))
            db.execute("INSERT INTO shop_member VALUES(1,1,1,'owner')")
        @application.get('/qa/identity')
        def qa_identity(): return {'temporary_shop':True,'real_auth':True}
        @application.post('/qa/expire')
        def expire(request: Request):
            with request.app.state.session_factory() as session:
                session.execute(update(SellerSession).values(expires_at=datetime.utcnow()-timedelta(seconds=1)));session.commit()
            return {'ok':True}
        uvicorn.run(application,host='127.0.0.1',port=8124,log_level='warning')
