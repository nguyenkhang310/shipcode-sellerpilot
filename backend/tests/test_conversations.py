import sqlite3
from uuid import uuid4
import pytest
from app.ai.contracts import ClassificationResult, ParsedCommand
from app.models.agent_run import AgentRun


def chat(client, message, conversation=None):
    result = client.post('/api/v1/chat', json={'message': message, 'conversation_id': conversation})
    assert result.status_code == 200, result.text
    return result.json()['data']


def test_followup_references_tool_sku_and_requires_confirmation(client, shop_db_path):
    first = chat(client, 'SKU A001 còn bao nhiêu?')
    proposal = chat(client, 'Đổi giá mã này thành 120k', first['conversation_id'])
    assert proposal['conversation_id'] == first['conversation_id']
    assert proposal['proposal']['sku'] == 'A001'
    assert proposal['proposal']['new_price_vnd'] == 120000
    assert proposal['proposal']['status'] == 'pending'
    agreed = chat(client, 'Đồng ý, xác nhận', first['conversation_id'])
    assert agreed['proposal'] is None
    assert 'thẻ đề xuất' in agreed['answer']
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute("SELECT price FROM product_variant WHERE sku='A001'").fetchone()[0] == 150000
    fresh = chat(client, 'Đổi giá mã này thành 120k')
    assert fresh['proposal'] is None
    assert 'sku' in fresh['facts']['missing_fields']


def test_clarification_accepts_price_and_sku_next_turn(client):
    missing_price = chat(client, 'Đổi giá SKU A001')
    filled = chat(client, '125k', missing_price['conversation_id'])
    assert filled['proposal']['new_price_vnd'] == 125000
    missing_sku = chat(client, 'Đổi giá thành 130k')
    filled = chat(client, 'SKU A002', missing_sku['conversation_id'])
    assert filled['proposal']['sku'] == 'A002'
    assert filled['proposal']['new_price_vnd'] == 130000


def test_search_then_ordinal_followup_uses_actual_list(client):
    found = chat(client, 'Tìm kiếm sản phẩm Áo thun')
    assert found['tool'] == 'search_products'
    assert len(found['facts']['items']) == 1
    followup = chat(client, 'Sản phẩm đầu tiên còn bao nhiêu?', found['conversation_id'])
    assert followup['facts']['sku'] == 'P001'
    assert followup['facts']['stock'] == 4
    assert chat(client, "Tìm %' OR 1=1 --")['facts']['total'] == 0


def test_history_keeps_current_proposal_status_and_is_tenant_scoped(client):
    first = chat(client, 'Đổi giá SKU A001 thành 120k')
    client.post(f"/api/v1/proposals/{first['proposal']['id']}/reject")
    detail = client.get('/api/v1/conversations/' + first['conversation_id']).json()['data']
    assert detail['turns'][0]['response']['proposal']['status'] == 'rejected'
    assert client.get('/api/v1/conversations').json()['data']['items'][0]['turns'] == 1
    with client.app.state.session_factory() as session:
        run = session.get(AgentRun, first['run_id'])
        run.shop_slug = 'other-shop'
        session.commit()
    assert client.get('/api/v1/conversations').json()['data']['items'] == []
    assert client.get('/api/v1/conversations/' + first['conversation_id']).status_code == 404
    unrelated = chat(client, 'Đổi giá mã này thành 100k', first['conversation_id'])
    assert unrelated['proposal'] is None
    assert client.get('/api/v1/conversations/' + str(uuid4())).status_code == 404
    assert client.get('/api/v1/conversations/invalid').status_code == 422


def test_model_cannot_invent_sku_or_apply_plain_text_confirmation(client):
    class ConfusedAI:
        async def classify(self, message, *, today):
            return ClassificationResult(command=ParsedCommand(intent='change_price', sku='A001', new_price_vnd=120000), model='test')
    client.app.state.ai_provider = ConfusedAI()
    result = chat(client, 'Thay mức giá thành 120k')
    assert result['proposal'] is None
    assert 'sku' in result['facts']['missing_fields']
    greeting = chat(client, 'Xin chào')
    assert greeting['intent'] == 'unknown'
    assert greeting['proposal'] is None
    assert 'ShipCode' in greeting['answer']


def test_advice_gets_shop_facts_and_prior_messages(client):
    first = chat(client, 'SKU A001 còn bao nhiêu?')
    class AdviceAI:
        async def classify(self, message, *, today):
            return ClassificationResult(command=ParsedCommand(intent='sales_advice'), model='test')
        async def respond(self, message, *, history, facts):
            assert facts['selected_product']['sku'] == 'A001'
            assert facts['selected_product']['stock'] == 3
            assert history[0]['content'] == 'SKU A001 còn bao nhiêu?'
            return 'Mẫu này còn 3 sản phẩm. Bạn nên kiểm tra kế hoạch nhập hàng.'
    client.app.state.ai_provider = AdviceAI()
    result = chat(client, 'Tư vấn cho sản phẩm này', first['conversation_id'])
    assert result['mode'] == 'ai'
    assert result['tool'] == 'get_shop_insights'
    assert '3 sản phẩm' in result['answer']


def test_generated_reply_cannot_claim_unexecuted_write(client):
    class HallucinatingAI:
        async def classify(self, message, *, today):
            return ClassificationResult(command=ParsedCommand(intent='sales_advice'), model='test')
        async def respond(self, *args, **kwargs):
            return 'Mình đã đăng sản phẩm lên shop cho bạn.'
    client.app.state.ai_provider = HallucinatingAI()
    result = chat(client, 'Tư vấn việc cần làm')
    assert result['mode'] == 'fallback'
    assert result['fallback_reason'] == 'invalid_response'
    assert 'đã đăng' not in result['answer']
    assert result['proposal'] is None


def test_context_survives_acknowledgement_and_advice(client):
    first = chat(client, 'SKU A001 còn bao nhiêu?')
    chat(client, 'Cảm ơn', first['conversation_id'])
    advice = chat(client, 'Tư vấn cho sản phẩm này', first['conversation_id'])
    assert advice['facts']['selected_product']['sku'] == 'A001'
    changed = chat(client, 'Đổi giá mã này thành 130k', first['conversation_id'])
    assert changed['proposal']['sku'] == 'A001'
    assert changed['proposal']['new_price_vnd'] == 130000


def test_opencode_style_provider_skips_classifier_for_obvious_casual_chat(client):
    class NaturalAI:
        provider = 'opencode'
        model = 'glm-5.3-flash-free'
        natural_responses = True
        prefer_model_intent = True

        async def classify(self, message, *, today):
            raise AssertionError('casual chat must not spend a classifier round-trip')

        async def respond(self, message, *, history, facts):
            assert facts['supported_intents']
            return 'Mình ở đây, bạn cứ kể mình nghe nhé.'

    client.app.state.ai_provider = NaturalAI()
    result = chat(client, 'Hôm nay mình hơi mệt, nói chuyện với mình chút nhé')
    assert result['intent'] == 'unknown'
    assert result['provider'] == 'opencode'
    assert result['answer'] == 'Mình ở đây, bạn cứ kể mình nghe nhé.'


def test_opencode_style_provider_uses_tool_facts_with_one_model_call(client):
    class NaturalAI:
        provider = 'opencode'
        model = 'glm-5.3-flash-free'
        natural_responses = True
        prefer_model_intent = True

        async def classify(self, message, *, today):
            raise AssertionError('explicit inventory query is already deterministic')

        async def respond(self, message, *, history, facts):
            assert facts['sku'] == 'A001'
            assert facts['stock'] == 3
            return 'SKU A001 hiện còn 3 sản phẩm.'

    client.app.state.ai_provider = NaturalAI()
    result = chat(client, 'SKU A001 còn bao nhiêu hàng?')
    assert result['tool'] == 'get_inventory'
    assert result['provider'] == 'opencode'
    assert result['answer'] == 'SKU A001 hiện còn 3 sản phẩm.'


def test_invalid_response_is_not_reported_as_lost_muse_connection(client):
    from app.ai.contracts import AIProviderError
    class InvalidReply:
        natural_responses = True
        provider = 'opencode'
        model = 'glm-5.3-flash-free'
        async def respond(self, *_args, **_kwargs):
            raise AIProviderError('invalid_response', stage='incomplete_reply')
    client.app.state.ai_provider = InvalidReply()
    result = chat(client, 'Sao vậy, không kết nối được à?')
    assert result['mode'] == 'fallback' and result['fallback_reason'] == 'invalid_response'
    assert 'chưa vượt qua kiểm tra' in result['answer']
    assert 'chưa kết nối' not in result['answer']


def test_unsafe_copy_is_rewritten_once_without_repeating_shop_actions(client, shop_db_path):
    class CorrectedReply:
        natural_responses = True
        provider = 'opencode'
        model = 'glm-5.3-flash-free'
        calls = 0
        async def respond(self, message, *, history, facts):
            self.calls += 1
            if self.calls == 1:
                return 'Mình đã cập nhật giá cho shop.'
            assert facts['reply_correction']['reason'] == 'unexecuted_write_claim'
            return 'Đề xuất: rà soát tồn kho và nội dung sản phẩm trong 7 ngày tới.'
    provider = CorrectedReply()
    client.app.state.ai_provider = provider
    result = chat(client, 'Lập kế hoạch hành động 7 ngày cho shop')
    assert provider.calls == 2 and result['mode'] == 'ai' and result['fallback_reason'] is None
    assert 'Đề xuất:' in result['answer']
    assert 'reply_correction' not in result['facts']
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute("SELECT price FROM product_variant WHERE sku='A001'").fetchone()[0] == 150000
    with client.app.state.session_factory() as session:
        from sqlalchemy import func, select
        from app.models.action import ActionProposal
        assert session.scalar(select(func.count()).select_from(AgentRun)) == 1
        assert session.scalar(select(func.count()).select_from(ActionProposal)) == 0


def test_price_clarification_accepts_slang_units(client):
    first = chat(client, 'Đổi giá SKU A001')
    assert first['proposal'] is None
    result = chat(client, '5 xị', first['conversation_id'])
    assert result['proposal']['new_price_vnd'] == 500000
    assert result['proposal']['status'] == 'pending'


@pytest.mark.parametrize('position', [0, 2, 999])
def test_invalid_ordinal_never_selects_the_only_product(client, position):
    first = chat(client, 'Tìm áo thun')
    assert len(first['facts']['items']) == 1
    result = chat(client, f'Đổi giá sản phẩm thứ {position} thành 125k', first['conversation_id'])
    assert result['proposal'] is None
    assert 'sku' in result['facts']['missing_fields']


def test_price_clarification_survives_social_turns_without_becoming_cost_input(client):
    first = chat(client, 'Đổi giá SKU A001')
    chat(client, 'cảm ơn', first['conversation_id'])
    chat(client, 'ok nhé', first['conversation_id'])
    result = chat(client, '5 xị', first['conversation_id'])
    assert result['proposal']['sku'] == 'A001'
    assert result['proposal']['new_price_vnd'] == 500000
