"""Real provider, isolated synthetic shop; never opens the configured shop DB.

Run from backend: .venv/bin/python -m app.scripts.evaluate_business
Outputs synthetic answers for manual assessment, not a quality guarantee.
"""
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.ai.factory import create_provider
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.integrations.ute_mall import UTEMallRepository
from app.services.chat import handle_chat


def seed_shop(path):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            CREATE TABLE product (id INTEGER PRIMARY KEY, sku TEXT, name TEXT,
                price REAL, old_price REAL, stock INTEGER, status TEXT);
            CREATE TABLE product_variant (id INTEGER PRIMARY KEY, product_id INTEGER,
                sku TEXT, title TEXT, size TEXT, color TEXT, price REAL,
                old_price REAL, stock INTEGER, is_active INTEGER);
            CREATE TABLE "order" (id INTEGER PRIMARY KEY, total_amount REAL,
                status TEXT, created_at TEXT);
            CREATE TABLE order_item (id INTEGER PRIMARY KEY, order_id INTEGER,
                product_id INTEGER, quantity INTEGER, price REAL);
            INSERT INTO product VALUES
                (1,'DEMO-KB-001','Bàn phím Nova K75 màu trắng',500000,NULL,30,'active'),
                (2,'DEMO-MS-001','Chuột Nova M1 màu đen',200000,NULL,3,'active'),
                (3,'DEMO-BAG-001','Túi đựng laptop màu xám',150000,NULL,20,'active');
        ''')
        connection.executemany('INSERT INTO "order" VALUES (?,?,?,?)', [
            (1,1000000,'delivered',str(now-timedelta(days=1))),
            (2,500000,'pending',str(now-timedelta(days=2))),
            (3,200000,'cancelled',str(now-timedelta(days=1))),
            (4,500000,'delivered',str(now-timedelta(days=8))),
        ])
        connection.executemany('INSERT INTO order_item VALUES (?,?,?,?,?)', [
            (1,1,1,2,500000),(2,2,1,1,500000),(3,3,2,1,200000),(4,4,1,1,500000)])


async def main():
    settings = Settings()
    with TemporaryDirectory(prefix='sellerpilot-business-eval-') as directory:
        root = Path(directory)
        seed_shop(root/'synthetic-shop.db')
        shop = UTEMallRepository(root/'synthetic-shop.db', 'Asia/Ho_Chi_Minh')
        engine = build_engine('sqlite:///' + str(root/'synthetic-agent.db'))
        Base.metadata.create_all(engine)
        try:
            async with create_provider(settings) as provider:
                conversation = None
                cases = [
                    'Mình tự làm một mình, không có ngân sách quảng cáo. Phân tích 7 ngày qua và lập kế hoạch kinh doanh 7 ngày tới. Chọn mặt hàng ưu tiên, lịch làm, ý tưởng TikTok và cách đo kết quả. Làm chi tiết.',
                    'Viết kịch bản TikTok 25 giây cho SKU DEMO-KB-001: 2 hook A/B, từng cảnh, lời thoại, chữ trên màn hình, CTA và caption. Không tự thêm thông số chưa có.',
                    'Cụ thể hơn cách đo hiệu quả của 2 video, nếu chưa có đơn từ TikTok thì sao?',
                ]
                for index, message in enumerate(cases, 1):
                    started = perf_counter()
                    with Session(engine) as session:
                        result = await handle_chat(session, shop, provider, message=message, conversation_id=conversation)
                    conversation = result['conversation_id']
                    print(json.dumps({'case':index, 'synthetic_test_only':True,
                        'seconds':round(perf_counter()-started,2), 'mode':result['mode'],
                        'provider':result['provider'], 'model':result['model'],
                        'fallback_reason':result['fallback_reason'],
                        'reporting_days':result['facts'].get('period',{}).get('days'),
                        'advisory_mode':result['facts'].get('business_advisory',{}).get('mode'),
                        'answer':result['answer']}, ensure_ascii=False),flush=True)
        finally:
            engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
