import sqlite3
from datetime import date

import pytest

from app.ai.catalog_query import catalog_lookup
from app.ai.fallback import parse_fallback
from app.integrations import management


@pytest.mark.parametrize('message,query,minimum,maximum', [
    ('còn chuột máy tính có sản phẩm nào dưới 1tr k', 'chuột máy tính', None, 999999),
    ('Shop có chuột máy tính không?', 'chuột máy tính', None, None),
    ('Bạn có chuột máy tính không?', 'chuột máy tính', None, None),
    ('Shop có bán bàn phím nào dưới 500k không?', 'bàn phím', None, 499999),
    ('Chuột máy tính có không?', 'chuột máy tính', None, None),
    ('Tìm bàn phím dưới 500k', 'bàn phím', None, 499999),
    ('Shop có áo thun từ 100k đến 200k không?', 'áo thun', 100000, 200000),
    ('Tìm giày thể thao trên 150k', 'giày thể thao', 150001, None),
    ('Xem laptop giá tối đa 15 triệu', 'laptop', None, 15000000),
    ('Shop có bàn phím dưới 500.000đ không?', 'bàn phím', None, 499999),
    ('Tìm chuột máy tính dưới 1 triệu đồng', 'chuột máy tính', None, 999999),
    ('Shop có sữa bột không?', 'sữa bột', None, None),
    ('Tìm tủ lạnh', 'tủ lạnh', None, None),
    ('Shop có đèn bàn dưới 500k không?', 'đèn bàn', None, 499999),
    ('Tim tinh dau', 'tinh dau', None, None),
    ('vậy thì cáp sạc dành cho iphone', 'cáp sạc dành cho iphone', None, None),
    ('Shop có bàn phím từ 100k tới 200k không?', 'bàn phím', 100000, 200000),
])
def test_natural_catalog_questions_extract_subject_and_price(message, query, minimum, maximum):
    result = catalog_lookup(message)
    assert result == {'query': query, 'min_price_vnd': minimum, 'max_price_vnd': maximum}
    command = parse_fallback(message, today=date(2026, 10, 19))
    assert command.intent == 'product_search'
    assert command.query == query


@pytest.mark.parametrize('message', [
    'Đổi giá chuột thành 500k', 'Tôi muốn xóa chuột khỏi kho',
    'Giá vốn chuột 100k, bán 150k có lời không?', 'Shop có bao nhiêu đơn hôm nay?',
    'Chào bạn', 'Tìm chuột dưới một mức giá hợp lý',
    'Shop có chuột dưới 1tr và bàn phím dưới 500k không?',
    'Phân tích doanh thu và gợi ý bán chuột', 'Tồn kho còn bao nhiêu?',
    'Còn khoảng 10 trái', 'Kho còn 20 cái', 'Shop có hàng tồn thấp không?',
    'Còn hôm nay thì sao?', 'Vậy còn tuần này?', 'Còn tháng trước?',
    'Còn cái đó thì sao?', 'Shop hôm nay bán được mấy đơn?',
    'Tìm dưới 500k', 'Tìm đèn 50k', 'Tìm tủ 100k',
])
def test_complex_and_mutating_requests_keep_their_existing_paths(message):
    assert catalog_lookup(message) is None


@pytest.mark.parametrize('message', ['Tìm đèn 50k', 'Tìm dưới 500k', 'Tìm chuột dưới 1tr và bàn phím dưới 500k'])
def test_incomplete_budget_queries_cannot_fall_back_to_a_literal_fast_search(message):
    from app.services.chat import is_exact_fact_question
    command = parse_fallback(message, today=date(2026, 10, 19))
    assert command.intent != 'product_search'
    assert not is_exact_fact_question(message, command)


def test_classifier_cannot_invent_a_price_filter_but_explicit_budget_is_preserved():
    from app.ai.contracts import ParsedCommand
    from app.services.chat import enrich_ai_command
    model = ParsedCommand(intent='product_search', query='chuột', min_price_vnd=100, max_price_vnd=1000)
    command = enrich_ai_command(model, message='Có loại chuột nào phù hợp để làm việc?', today=date(2026, 10, 19))
    assert command.min_price_vnd is None and command.max_price_vnd is None
    command = enrich_ai_command(model, message='Tìm chuột từ 100k tới 200k', today=date(2026, 10, 19))
    assert (command.min_price_vnd, command.max_price_vnd) == (100000, 200000)


def test_sql_filters_full_catalog_before_pagination_and_matches_reordered_terms(client, shop_db_path):
    with sqlite3.connect(shop_db_path) as db:
        for index in range(3, 15):
            db.execute('INSERT INTO product VALUES (?, ?, ?, ?, NULL, ?, ?)',
                       (index, f'MOUSE-{index}', 'Chuột AmazonBasics máy tính',
                        863000 if index == 3 else 1500000, 47, 'active'))
    result = management.products(client.app.state.shop_repository, 'chuot may tinh',
                                 limit=1, max_price_vnd=999999)
    assert result['total'] == 1
    assert result['items'][0]['sku'] == 'MOUSE-3'
    assert result['items'][0]['stock'] == 47
    assert management.products(client.app.state.shop_repository, '%')['total'] == 0


def test_chat_uses_fresh_catalog_facts_instead_of_prior_product_context(client, shop_db_path):
    class WrongAI:
        provider = 'gemini'
        prefer_direct_facts = True
        natural_responses = True

        async def respond(self, *args, **kwargs):
            raise AssertionError('A catalogue read must not ask the model to guess availability')

        async def classify(self, *args, **kwargs):
            raise AssertionError('A complete catalogue question already has a safe local intent')

    with sqlite3.connect(shop_db_path) as db:
        db.execute("INSERT INTO product VALUES (3,'MOUSE-3','Chuột máy tính AmazonBasics',863000,NULL,47,'active')")
        db.execute("INSERT INTO product VALUES (4,'MOUSE-4','Chuột máy tính cao cấp',1500000,NULL,10,'active')")
    client.app.state.ai_provider = WrongAI()
    first = client.post('/api/v1/chat', json={'message': 'Tìm áo thun'}).json()['data']
    response = client.post('/api/v1/chat', json={
        'conversation_id': first['conversation_id'],
        'message': 'còn chuột máy tính có sản phẩm nào dưới 1tr k',
    })
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['tool'] == 'search_products'
    assert data['facts']['total'] == 1
    assert data['facts']['items'][0]['sku'] == 'MOUSE-3'
    assert '863.000đ' in data['answer'] and '47' in data['answer']
    assert 'MOUSE-4' not in data['answer']
    assert data['proposal'] is None
    empty = client.post('/api/v1/chat', json={
        'conversation_id': first['conversation_id'],
        'message': 'Shop có chuột máy tính dưới 100k không?',
    }).json()['data']
    assert empty['facts']['total'] == 0
    assert 'khoảng giá' in empty['answer']


def test_budget_boundaries_are_inclusive_only_when_requested(client):
    shop = client.app.state.shop_repository
    assert management.products(shop, 'áo thun', max_price_vnd=149999)['total'] == 0
    assert management.products(shop, 'áo thun', max_price_vnd=150000)['total'] == 1


def test_price_search_remains_scoped_to_current_seller(tmp_path):
    from test_shop_tenant_scope import build_marketplace
    from app.integrations.ute_mall import UTEMallRepository

    path = tmp_path / 'shops.db'
    build_marketplace(path)
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    assert management.products(shop, 'keyboard', max_price_vnd=450000)['total'] == 0
    found = management.products(shop, 'keyboard', max_price_vnd=500000)
    assert [item['sku'] for item in found['items']] == ['UT-P1']


def test_advice_receives_total_and_price_filtered_catalog_not_only_samples(client, shop_db_path):
    from test_advisor import AdvisorAI

    with sqlite3.connect(shop_db_path) as db:
        for index in range(3, 10):
            db.execute('INSERT INTO product VALUES (?, ?, ?, ?, NULL, ?, ?)',
                       (index, f'MOUSE-{index}', 'Chuột máy tính AmazonBasics',
                        863000 if index < 9 else 1500000, 47, 'active'))
    provider = AdvisorAI([{'product_query': 'chuột máy tính dưới 1tr'}])
    client.app.state.ai_provider = provider
    response = client.post('/api/v1/chat', json={
        'message': 'Tư vấn giúp mình về chuột máy tính dưới 1tr',
    })
    assert response.status_code == 200, response.text
    facts = provider.answers[-1]['facts']
    assert facts['catalog_search']['total'] == 6
    assert len(facts['catalog_search']['items']) == 4
    assert facts['catalog_search']['max_price_vnd'] == 999999
    assert all(item['price_vnd'] < 1000000 for item in facts['candidate_products'])
