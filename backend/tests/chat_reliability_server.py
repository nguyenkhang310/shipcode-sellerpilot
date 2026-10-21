"""Synthetic shop + delayed fake AI for deterministic browser reliability tests.

Run from backend: .venv/bin/python tests/chat_reliability_server.py
Never reads the connected shop or calls an external model.
"""
import asyncio
import json
import tempfile
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
import uvicorn
from app.ai.contracts import ProviderHealth
from test_product_drafts import make_client, OfflineProvider
import app.main

class QAProvider(OfflineProvider):
    provider = 'opencode'
    model = 'glm-5.3-flash-free'
    natural_responses = True
    prefer_model_intent = True
    async def check_health(self):
        return ProviderHealth(availability='available', model_available=True)
    async def analyze_advice(self, *args, **kwargs):
        return '{}'
    async def respond(self, message, *, history, facts):
        await asyncio.sleep(2)
        return 'Đã kiểm tra số liệu thử của shop. Bạn có thể tiếp tục trao đổi.'
    async def compose_listing(self, **kwargs):
        await asyncio.sleep(2)
        return json.dumps({'name':'Bàn phím thử nghiệm', 'description':'Bàn phím dành cho công việc và học tập trong dữ liệu kiểm thử.', 'category_id':4, 'clarification':None})

@asynccontextmanager
async def qa_provider(settings):
    yield QAProvider()
if __name__ == '__main__':
    app.main.create_provider = qa_provider
    with tempfile.TemporaryDirectory(prefix='sellerpilot-reliability-') as directory:
        client, _, _ = make_client(Path(directory))
        settings = client.app.state.settings
        settings.cors_origins.append('http://127.0.0.1:5174')
        public = Path(directory) / 'static' / 'catalog'
        public.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[2] / 'frontend/assets/shipcode-logo-app.png', public / 'sample.png')
        settings.shop_static_dir = public.parent
        with sqlite3.connect(settings.shop_database_path) as connection:
            connection.execute("UPDATE product SET image_url='/static/catalog/sample.png'")
            connection.execute("ALTER TABLE \"order\" ADD COLUMN shipping_name TEXT")
            for column in ['shipping_phone TEXT', 'shipping_address TEXT', 'note TEXT', 'payment_method TEXT', 'payment_status TEXT']:
                connection.execute('ALTER TABLE "order" ADD COLUMN ' + column)
            for number in range(1, 36):
                created = (datetime.utcnow() - timedelta(hours=number)).isoformat(sep=' ')
                state = ['pending', 'paid', 'shipped', 'delivered', 'cancelled'][number % 5]
                connection.execute('INSERT INTO \"order\" (id, shop_id, total_amount, status, created_at, shipping_name) VALUES (?,1,1000000,?,?,?)',
                    (number, state, created, 'Khách thử nghiệm ' + str(number)))
                connection.execute('INSERT INTO order_item (order_id, product_id, quantity, price) VALUES (?,1,1,1000000)', (number,))
            connection.execute("UPDATE \"order\" SET shipping_phone='0901234567', shipping_address='123 Đường Kiểm Thử', note='', payment_method='COD', payment_status='unpaid'")
        application = app.main.create_app(settings)
        from auth_fixture import authenticated_fixture
        authenticated_fixture(application)
        @application.get('/qa/identity')
        def qa_identity():
            return {'temporary_shop': True}
        uvicorn.run(application, host='127.0.0.1', port=8123, log_level='warning')
