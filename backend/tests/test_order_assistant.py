import sqlite3
from test_order_management import ledger, patch
from test_advisor import chat
from app.services.order_assistant import order_reference, is_order_question
from test_advisor import AdvisorAI


def test_order_read_refreshes_real_state_without_calling_ai(ledger):
    client, _ = ledger
    first = chat(client, 'đơn #1 sao rồi?')
    assert first['tool'] == 'get_order_tracking'
    assert first['provider'] == 'deterministic_parser' and first['fallback_reason'] is None
    assert first['facts']['order_lookup']['status'] == 'pending'
    assert patch(client, status='paid').status_code == 200
    again = chat(client, 'còn đơn đó sao rồi?', first['conversation_id'])
    assert again['facts']['order_lookup']['status'] == 'paid'
    assert 'Chờ lấy hàng' in again['answer']
    assert 'shipping_phone' not in again['facts']['order_lookup']


def test_missing_id_is_asked_once_and_bare_reply_resolves(ledger):
    client, _ = ledger
    first = chat(client, 'xem trạng thái đơn hàng')
    assert first['facts']['order_lookup']['missing_id']
    next = chat(client, '#1', first['conversation_id'])
    assert next['facts']['order_action']['id'] == 1


def test_foreign_order_and_new_conversation_never_reuse_selection(ledger):
    client, _ = ledger
    missing = chat(client, 'theo dõi đơn #2')
    assert missing['facts']['order_lookup']['found'] is False
    assert 'order_action' not in missing['facts']
    assert 'Private' not in missing['answer']
    chat(client, 'đơn #1 sao rồi?')
    fresh = chat(client, 'còn mã vận đơn?')
    assert fresh['facts']['order_lookup']['missing_id']


def test_chat_cancellation_does_not_execute_and_history_keeps_action(ledger):
    client, path = ledger
    result = chat(client, 'hủy đơn #1')
    assert 'xem lại và xác nhận' in result['answer']
    assert result['facts']['order_action']['id'] == 1
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status FROM "order" WHERE id=1').fetchone()[0] == 'pending'
        assert db.execute('SELECT COUNT(*) FROM sellerpilot_order_event').fetchone()[0] == 0
    restored = client.get('/api/v1/conversations/' + result['conversation_id']).json()['data']
    assert restored['turns'][-1]['response']['facts']['order_action']['id'] == 1


def test_order_query_does_not_become_a_product_title(ledger):
    client, _ = ledger
    draft = chat(client, 'đăng sản phẩm lên shop')
    assert draft['product_draft']
    result = chat(client, 'kiểm tra đơn #1', draft['conversation_id'])
    assert result['tool'] == 'get_order_tracking'
    assert result['product_draft'] is None


def test_order_grammar_never_treats_prices_quantities_or_multiple_ids_as_one_order():
    assert order_reference('bán 1 đơn giá 123k') is None
    assert order_reference('5 xị') is None
    assert order_reference('so sánh đơn #1 với đơn #2') is None
    assert not is_order_question('tồn kho còn 123')


def test_complex_order_advice_uses_one_generation_with_current_order_facts(ledger):
    client, _ = ledger
    class OrderAI(AdvisorAI):
        async def analyze_advice(self, *_args, **_kwargs):
            raise AssertionError('Order advice does not need pricing extraction')
        async def respond(self, message, *, history, facts):
            assert facts['order_lookup']['status'] == 'pending'
            self.answers.append(facts)
            return 'Đơn #1 đang chờ xác nhận. Bạn nên kiểm tra hàng và xác nhận trước khi chuẩn bị giao.'
    ai = OrderAI([]); client.app.state.ai_provider = ai
    result = chat(client, 'Vì sao đơn #1 chưa giao, cần làm gì?')
    assert result['mode'] == 'ai' and len(ai.answers) == 1
    assert result['facts']['order_action']['id'] == 1


def test_batch_order_lookup_never_leaks_foreign_order_or_chooses_one_silently(ledger):
    client, _ = ledger
    result = chat(client, 'so sánh đơn #1 với đơn #2')
    assert [row['id'] for row in result['facts']['order_comparison']] == [1, 2]
    assert result['facts']['order_comparison'][1]['found'] is False
    assert 'Private' not in result['answer']
