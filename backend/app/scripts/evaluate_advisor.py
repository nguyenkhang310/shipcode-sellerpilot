"""Evaluate the configured AI provider using synthetic shop data only.

Run from backend: .venv/bin/python -m app.scripts.evaluate_advisor
"""
import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.factory import create_provider
from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.integrations.ute_mall import UTEMallRepository
from app.services.chat import handle_chat
import app.models  # noqa: F401


def synthetic_shop(path):
    """No reads or copies from the real shop database."""
    with sqlite3.connect(path) as db:
        db.executescript('''
            CREATE TABLE shop (id INTEGER PRIMARY KEY, slug TEXT, name TEXT, status TEXT);
            CREATE TABLE product (id INTEGER PRIMARY KEY, sku TEXT, name TEXT, price REAL,
                old_price REAL, stock INTEGER, status TEXT, shop_id INTEGER, sold_count INTEGER, rating REAL);
            CREATE TABLE product_variant (id INTEGER PRIMARY KEY, product_id INTEGER, sku TEXT,
                title TEXT, size TEXT, color TEXT, price REAL, stock INTEGER, is_active INTEGER);
            CREATE TABLE "order" (id INTEGER PRIMARY KEY, shop_id INTEGER, total_amount REAL, status TEXT, created_at TEXT);
            CREATE TABLE order_item (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, price REAL);
            INSERT INTO shop VALUES (1, 'synthetic-demo', 'Shop công nghệ giả lập', 'active');
            INSERT INTO product VALUES
                (1, 'DEMO-KB-001', 'Bàn phím Demo 75', 150000, NULL, 3, 'active', 1, 12, 4.5),
                (2, 'DEMO-MS-001', 'Chuột Demo M1', 90000, NULL, 20, 'active', 1, 8, 4.6);
        ''')
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(1, 13):
            created = now - timedelta(hours=12 * i)
            status = 'pending' if i <= 3 else 'delivered'
            db.execute('INSERT INTO "order" VALUES (?,1,?,?,?)', (i, 150000, status, created.isoformat(sep=' ')))


async def main():
    settings = Settings()
    results = []
    with tempfile.TemporaryDirectory(prefix='sellerpilot-advisor-check-') as directory:
        root = Path(directory)
        synthetic_shop(root / 'shop.db')
        shop = UTEMallRepository(root / 'shop.db', 'Asia/Ho_Chi_Minh', 'synthetic-demo')
        engine = build_engine('sqlite:///' + str(root / 'agent.db'))
        Base.metadata.create_all(engine)
        messages = [
            'Mình bán cho sinh viên, muốn bán bền vững, không đua giảm giá. Trả lời ngắn gọn giúp mình. Gợi ý hướng đi cho shop nhé.',
            'Mình tính thử một sản phẩm chưa đăng: giá vốn 100k, đóng gói 5k mỗi đơn, tổng phí sàn 10% giá bán, hỗ trợ ship 0đ, quảng cáo mỗi đơn 0đ, chi phí khác 0đ. Mỗi đơn 1 sản phẩm. Bán 150k thì lời bao nhiêu, muốn biên lợi nhuận 20% trên giá bán thì nên bán giá nào?',
            'Nếu giảm giá 10% thì lời còn bao nhiêu?',
            'Dựa trên khách mục tiêu và định hướng của mình, đề xuất 2 việc ưu tiên tuần tới và cách đo hiệu quả nhé.',
        ]
        async with create_provider(settings) as ai:
            with Session(engine) as session:
                conversation_id = None
                for i, message in enumerate(messages):
                    result = await handle_chat(session, shop, ai, message=message,
                        conversation_id=None if i == 3 else conversation_id)
                    conversation_id = result['conversation_id']
                    results.append({'message': message, 'answer': result['answer'],
                        'mode': result['mode'], 'model': result['model'],
                        'fallback_reason': result['fallback_reason'], 'facts': result['facts']})
                    print(json.dumps(results[-1], ensure_ascii=False), flush=True)
                    assert result['proposal'] is None
                    assert result['mode'] == 'ai', result['fallback_reason']
                assert 'sinh viên' in results[0]['facts']['seller_preferences']['target_audience']
                pricing = results[1]['facts']['pricing_analysis']
                assert pricing['at_selling_price']['profit_per_unit_vnd'] == 30000
                assert pricing['target_price']['price_vnd'] == 150000
                assert results[2]['facts']['pricing_analysis']['after_discount']['profit_per_unit_vnd'] == 16500
                assert 'sinh viên' in results[3]['facts']['seller_preferences']['target_audience']
                assert 'pricing_analysis' not in results[3]['facts']
        engine.dispose()
    report = Path(__file__).resolve().parents[3] / 'docs' / 'ADVISOR_LIVE_EVALUATION.json'
    report.write_text(json.dumps({'cases': results, 'passed': True}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS: {report}', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
