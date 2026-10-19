import asyncio
import json
import sqlite3
from uuid import uuid4
from datetime import datetime, timezone

import httpx
import pytest

from app.ai.advisor_contracts import AdvicePreparation
from app.ai.client import response_prompt
from app.ai.contracts import AIProviderError
from app.ai.fallback import parse_fallback
from app.ai.gemini import GeminiClient
from app.integrations.business import business_snapshot
from app.integrations.ute_mall import UTEMallRepository, ShopDatabaseError
from app.services.business_advisor import attach_business_brief, planning_request, business_reply_issue
from app.services.chat import reply_issue
from app.models.product_draft import ProductDraft
from test_shop_tenant_scope import build_marketplace

NOW = datetime(2026, 10, 19, 5, tzinfo=timezone.utc)


def seed_performance(path):
    with sqlite3.connect(path) as connection:
        connection.executescript('DELETE FROM order_item; DELETE FROM "order";')
        connection.executemany('INSERT INTO "order" VALUES (?, ?, ?, ?)', [
            (1, 900000, 'delivered', '2026-10-19 04:00:00'),
            (2, 100000, 'pending', '2026-10-18 04:00:00'),
            (3, 999000, 'cancelled', '2026-10-19 04:00:00'),
            (4, 999000, 'returned', '2026-10-19 04:00:00'),
            (5, 888000, 'paid', '2026-10-20 04:00:00'),
            (6, 500000, 'delivered', '2026-10-11 04:00:00'),
            (7, 999000, 'delivered', '2026-10-12 06:00:00'),
            (8, 200000, 'paid', '2026-10-19 04:00:00'),
        ])
        connection.executemany('INSERT INTO order_item VALUES (?, ?, ?, ?, ?)', [
            (1, 1, 1, 2, 100000), (2, 1, 2, 1, 700000), (3, 2, 1, 1, 100000),
            (4, 3, 2, 99, 1000), (5, 4, 2, 99, 1000), (6, 5, 2, 99, 1000),
            (7, 6, 2, 2, 250000), (8, 7, 2, 99, 1000), (9, 8, 999, 1, 200000),
        ])
        connection.execute('UPDATE product SET stock=999 WHERE id=2')


def test_snapshot_uses_period_purchased_prices_and_equal_duration_not_catalog_sales(shop_db_path):
    seed_performance(shop_db_path)
    shop = UTEMallRepository(shop_db_path, 'Asia/Ho_Chi_Minh')
    snapshot = business_snapshot(shop, 7, now=NOW)
    assert snapshot['current']['order_count'] == 3
    assert snapshot['current']['order_value_vnd'] == 1200000
    assert snapshot['current']['average_order_vnd'] == 400000
    assert snapshot['current']['delivered_value_vnd'] == 900000
    assert snapshot['current']['cancelled_rate_percent'] == 20
    assert snapshot['current']['returned_rate_percent'] == 20
    assert snapshot['previous']['order_value_vnd'] == 500000
    assert snapshot['comparison']['order_value_change_percent'] == 140
    assert snapshot['comparison']['previous_through'] == '2026-10-12T05:00:00+00:00'
    first, second = snapshot['period_top_products']
    assert (first['sku'], first['units_sold'], first['item_sales_value_vnd']) == ('P001', 3, 300000)
    assert second['previous_units_sold'] == 2
    assert second['available_stock'] == 13  # variants, not mirrored parent stock
    assert snapshot['promotion_candidates'][0]['sku'] == 'P002'
    assert snapshot['attribution']['unmatched_current_item_lines'] == 1
    assert snapshot['attribution']['catalog_sold_count_used'] is False
    assert sum(row['order_value_vnd'] for row in snapshot['daily_sales']) == 1200000


def test_no_order_items_is_unknown_attribution_not_fake_product_ranking(shop_db_path):
    shop = UTEMallRepository(shop_db_path, 'Asia/Ho_Chi_Minh')
    snapshot = business_snapshot(shop, 1, now=NOW)
    assert snapshot['comparison']['order_value_change_percent'] is None
    assert snapshot['period_top_products'] == []
    assert snapshot['attribution']['available'] is False
    assert all(item['stock_cover_days_estimate'] is None for item in snapshot['promotion_candidates'])


def test_snapshot_blocks_cross_tenant_metadata_and_corrupted_line_references(tmp_path):
    path = tmp_path / 'mall.db'
    build_marketplace(path)
    with sqlite3.connect(path) as connection:
        connection.execute('INSERT INTO order_item VALUES (1, 1, 1, 2, 100000)')
        connection.execute('INSERT INTO order_item VALUES (2, 1, 2, 80, 100000)')
        connection.execute('INSERT INTO order_item VALUES (3, 2, 2, 90, 100000)')
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    snapshot = business_snapshot(shop, 7, now=NOW)
    assert snapshot['current']['order_value_vnd'] == 700000
    assert len(snapshot['period_top_products']) == 1
    assert snapshot['period_top_products'][0]['units_sold'] == 2
    assert 'OTHER' not in json.dumps(snapshot)
    assert snapshot['attribution']['unmatched_current_item_lines'] == 1
    with sqlite3.connect(path) as connection:
        connection.execute('ALTER TABLE "order" RENAME COLUMN shop_id TO missing_shop_id')
    with pytest.raises(ShopDatabaseError):
        business_snapshot(shop, 7, now=NOW)


@pytest.mark.parametrize('days', [0, 31, True, '7'])
def test_snapshot_rejects_invalid_reporting_windows(shop_db_path, days):
    with pytest.raises(ValueError):
        business_snapshot(UTEMallRepository(shop_db_path, 'Asia/Ho_Chi_Minh'), days, now=NOW)


def test_plan_horizon_followups_and_video_intent_are_read_only():
    request = planning_request('Phân tích 7 ngày qua và lập kế hoạch 30 ngày tới')
    assert request['horizon_days'] == 30
    assert planning_request('Lập kế hoạch 30 ngày tới')['horizon_days'] == 30
    assert planning_request('Lập kế hoạch 7 ngày qua')['horizon_days'] == 7
    assert planning_request('Cụ thể hơn', [{'role':'user','content':'Viết kịch bản TikTok cho SKU A001'}])['mode'] == 'video_script'
    assert planning_request('Cụ thể hơn', [{'role':'user','content':'Xin chào'}]) is None
    assert planning_request('SKU A001 còn bao nhiêu?') is None
    command = parse_fallback('Quay video TikTok cho SKU A001, giá 5 xị', today=NOW.date())
    assert command.intent == 'sales_advice' and command.new_price_vnd is None


def test_brief_keeps_requested_sku_does_not_substitute_and_has_video_measurement(client):
    shop = client.app.state.shop_repository
    facts = {'period':{'days':7}, 'tasks':{}, 'selected_product':shop.get_item_by_sku('A001')}
    brief = attach_business_brief(shop, facts, message='Lập kế hoạch quay TikTok cho SKU A001')
    assert brief['focus_product']['sku'] == 'A001'
    assert brief['focus_product']['available_stock'] == 3
    assert brief['commercial_constraints']['tiktok_shop_connected'] is False
    assert 'attributed_orders' in brief['measurement']['manual_fields']
    assert len(brief['video_production']['structure']) == 4
    missing = {'period':{'days':7}, 'selected_product':{'sku':'MISSING001','found':False}}
    assert attach_business_brief(shop, missing, message='Lập kế hoạch cho SKU MISSING001')['focus_product'] is None


class PlanningAI:
    provider = 'gemini'
    model = 'gemini-3.5-flash-lite'
    natural_responses = True
    prefer_direct_facts = True

    def __init__(self, fail=False):
        self.seen = []
        self.fail = fail

    async def prepare_advice(self, message, *, history, context, facts):
        self.seen.append(facts.copy())
        if self.fail:
            raise AIProviderError('provider_rate_limited')
        return AdvicePreparation.model_validate({'extraction':{'topic':'strategy'},
            'answer':'**Ngày 1:** kiểm tra trang sản phẩm. **Ngày 2–3:** quay hai hook, đo nhấp và đơn có nguồn.'})

    async def respond(self, *args, **kwargs):
        raise AIProviderError('provider_rate_limited')


def test_chat_prepares_with_business_evidence_keeps_plan_context_and_never_writes(client):
    provider = PlanningAI()
    client.app.state.ai_provider = provider
    first = client.post('/api/v1/chat', json={'message':'Phân tích số liệu và lập kế hoạch 7 ngày'}).json()['data']
    assert first['mode'] == 'ai'
    assert first['proposal'] is None
    assert provider.seen[0]['business_analysis']['period']['days'] == 7
    assert provider.seen[0]['business_advisory']['mode'] == 'business_plan'
    second = client.post('/api/v1/chat', json={'message':'Cụ thể hơn','conversation_id':first['conversation_id']}).json()['data']
    assert second['facts']['business_advisory']['followup'] is True
    assert second['facts']['business_advisory']['horizon_days'] == 7


def test_outage_keeps_actionable_plan_and_is_labeled_fallback(client):
    client.app.state.ai_provider = PlanningAI(fail=True)
    result = client.post('/api/v1/chat', json={'message':'Lập kế hoạch kinh doanh 7 ngày'}).json()['data']
    assert result['mode'] == 'fallback'
    assert '0–3s' in result['answer']
    assert 'giá trị' in result['answer']
    assert result['proposal'] is None


def test_detailed_prompt_and_output_budget_only_apply_to_plans():
    assert 'CẦM ĐI QUAY' not in response_prompt({})
    facts = {'business_advisory': {'mode':'business_plan'}}
    assert 'CẦM ĐI QUAY' in response_prompt(facts)
    seen = []
    async def run():
        def handler(request):
            seen.append(json.loads(request.content)['generationConfig']['maxOutputTokens'])
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'Kế hoạch thử nghiệm.'}]}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            provider = GeminiClient(http, 'synthetic', advice_max_tokens=4096)
            await provider.respond('Xin chào', history=[], facts={})
            await provider.respond('Lập kế hoạch', history=[], facts=facts)
    asyncio.run(run())
    assert seen == [2048,4096]
    assert reply_issue('Mình đã đăng video và chạy quảng cáo.', facts) == 'unexecuted_write_claim'
    assert reply_issue('Nếu bạn đã đăng video, hãy ghi số lượt nhấp.', facts) is None


def test_business_reply_checks_product_claims_stock_units_and_script_completeness():
    facts = {'business_advisory': {'mode':'video_script', 'focus_product':{'name':'Bàn phím Nova K75 màu trắng'}},
             'tasks':{'low_stock_products':1}}
    assert business_reply_issue('Hook: Bàn phím cơ gõ êm.',facts) == 'unsupported_product_feature'
    assert business_reply_issue('Chữ: Layout gọn, phím bấm êm.',facts) == 'unsupported_product_feature'
    assert business_reply_issue('Có **3 sản phẩm** sắp hết hàng.',facts) == 'product_count_vs_stock_units'
    assert business_reply_issue('Một mẫu còn 3 chiếc.',facts) is None
    assert business_reply_issue('Cảnh 1: cận sản phẩm, Caption: xem hàng.',facts,
        message='Viết kịch bản với lời thoại') == 'incomplete_video_script'
    assert business_reply_issue('Thoại: xem mẫu này. Thoại: mình quay cận nhé. Caption: xem gian hàng.',facts,
        message='Viết kịch bản với lời thoại') is None
    facts['business_advisory']['mode'] = 'measurement_plan'
    assert business_reply_issue('So sánh với đơn hàng phát sinh trong cùng ngày.',facts) == 'unattributed_video_orders'
    assert business_reply_issue('Lượt xem thấp: hook chưa đủ thu hút.',facts) == 'unsupported_marketing_cause'
    assert business_reply_issue('Giả thuyết: hook chưa đủ thu hút, cần thử A/B.',facts) is None


def test_measurement_followup_keeps_explicit_product_instead_of_promotion_ranking(client):
    shop = client.app.state.shop_repository
    facts = {'period':{'days':7}}
    brief = attach_business_brief(shop, facts, message='Cụ thể hơn cách đo hiệu quả 2 video',
        history=[{'role':'user','content':'Viết kịch bản cho SKU A001'}])
    assert brief['mode'] == 'measurement_plan'
    assert brief['focus_product']['sku'] == 'A001'


@pytest.mark.parametrize('corrected', [True, False])
def test_unsupported_advertising_claim_is_corrected_or_replaced_before_saving(client, corrected):
    class FaultyPlanningAI(PlanningAI):
        def __init__(self):
            super().__init__()
            self.corrections = []

        async def prepare_advice(self, *args, **kwargs):
            return AdvicePreparation.model_validate({'extraction': {'topic':'strategy'},
                'answer':'Quay bàn phím cơ gõ êm để bán hàng.'})

        async def respond(self, message, *, history, facts):
            self.corrections.append(facts['reply_correction'])
            return ('Ngày 1 kiểm tra sản phẩm; ngày 2 quay thao tác thực tế và ghi số liệu.'
                    if corrected else 'Bàn phím cơ gõ êm chắc chắn bán được.')

    provider = FaultyPlanningAI()
    client.app.state.ai_provider = provider
    result = client.post('/api/v1/chat',json={'message':'Lập kế hoạch kinh doanh 7 ngày'}).json()['data']
    assert len(provider.corrections) == 1
    assert provider.corrections[0]['reason'] == 'unsupported_product_feature'
    assert result['mode'] == ('ai' if corrected else 'fallback')
    assert 'bàn phím cơ' not in result['answer'].lower()
    stored = client.get('/api/v1/conversations/' + result['conversation_id']).json()['data']
    assert 'bàn phím cơ' not in json.dumps(stored, ensure_ascii=False).lower()


def test_video_with_caption_does_not_edit_an_active_listing_draft(client):
    conversation = str(uuid4())
    with client.app.state.session_factory() as session:
        draft = ProductDraft(conversation_id=conversation,
            shop_slug=client.app.state.shop_repository.seller_shop_slug or 'local', status='collecting',
            image_filename='synthetic.png', image_url='/synthetic.png', image_mime='image/png',
            image_bytes=10, name='Túi laptop màu xám', description='Mô tả đang giữ',
            price_vnd=150000, stock=None)
        session.add(draft)
        session.commit()
        draft_id = draft.id
    client.app.state.ai_provider = PlanningAI()
    result = client.post('/api/v1/chat',json={'conversation_id':conversation,
        'message':'Lập kế hoạch đăng video TikTok cho sản phẩm này, viết caption đi kèm'}).json()['data']
    assert result['product_draft'] is None
    assert result['facts']['business_advisory']['focus_product']['status'] == 'draft'
    assert result['facts']['business_advisory']['focus_product']['name'] == 'Túi laptop màu xám'
    with client.app.state.session_factory() as session:
        draft = session.get(ProductDraft, draft_id)
        assert draft.description == 'Mô tả đang giữ'
        assert draft.price_vnd == 150000 and draft.stock is None
