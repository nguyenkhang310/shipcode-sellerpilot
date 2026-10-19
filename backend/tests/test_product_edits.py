import json
import sqlite3

import pytest

from app.ai.edit_contracts import ProductEditCopy
from app.integrations.product_edits import apply_product_edit
from app.models.product_edit import ProductEditAudit, ProductEditProposal
from app.services.product_edit_chat import is_product_edit_request, local_changes


@pytest.fixture
def edit_client(client,shop_db_path):
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('ALTER TABLE product ADD COLUMN description TEXT')
        connection.execute("UPDATE product SET description='Mô tả ban đầu'")
    return client


def propose(client,changes,sku='A001'):
    response=client.post('/api/v1/product-edits',json={'sku':sku,'changes':changes})
    assert response.status_code==201,response.text
    return response.json()['data']


def test_multi_field_edit_requires_confirmation_updates_store_and_audits_once(edit_client,shop_db_path):
    proposal=propose(edit_client,{'name':'Giày thể thao màu đen','description':'Thông tin do người bán cung cấp.\nSize 40.',
                                  'price_vnd':120000,'stock':20})
    assert proposal['shared_content'] is True
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute('SELECT name,description FROM product WHERE id=2').fetchone()==('Giày thể thao','Mô tả ban đầu')
    result=edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm")
    assert result.status_code==200,result.text
    assert result.json()['data']['status']=='approved'
    assert edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm").json()['data']['idempotent'] is True
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute('SELECT name,price,stock FROM product WHERE id=2').fetchone()==('Giày thể thao màu đen',120000,30)
        assert connection.execute('SELECT price,stock FROM product_variant WHERE id=1').fetchone()==(120000,20)
        assert connection.execute('SELECT price,stock FROM product_variant WHERE id=2').fetchone()==(200000,10)
        assert connection.execute('SELECT COUNT(*) FROM sellerpilot_product_edit_receipt').fetchone()[0]==1
    with edit_client.app.state.session_factory() as session:
        assert session.query(ProductEditAudit).count()==1


def test_stale_edit_cannot_partially_overwrite_content_or_commerce(edit_client,shop_db_path):
    proposal=propose(edit_client,{'name':'Giày thể thao mới','price_vnd':120000,'stock':20})
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('UPDATE product_variant SET stock=2 WHERE id=1')
    response=edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm")
    assert response.status_code==409
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute('SELECT name FROM product WHERE id=2').fetchone()[0]=='Giày thể thao'
        assert connection.execute('SELECT price,stock FROM product_variant WHERE id=1').fetchone()==(150000,2)


def test_receipt_recovers_store_commit_before_agent_commit(edit_client):
    proposal=propose(edit_client,{'description':'Thông tin mới do người bán xác nhận.'})
    with edit_client.app.state.session_factory() as session:
        stored=session.get(ProductEditProposal,proposal['id'])
        stored.status='executing'
        session.commit()
        assert apply_product_edit(edit_client.app.state.shop_repository,stored) is False
    result=edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm")
    assert result.status_code==200,result.text
    assert result.json()['data']['idempotent'] is True
    with edit_client.app.state.session_factory() as session:
        assert session.query(ProductEditAudit).count()==1


def test_reject_and_tenant_isolation(edit_client,shop_db_path):
    proposal=propose(edit_client,{'stock':0})
    shop=edit_client.app.state.shop_repository
    original=shop.seller_shop_slug
    shop.seller_shop_slug='other-shop'
    assert edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm").status_code==404
    assert edit_client.post(f"/api/v1/product-edits/{proposal['id']}/reject").status_code==404
    shop.seller_shop_slug=original
    assert edit_client.post(f"/api/v1/product-edits/{proposal['id']}/reject").json()['data']['status']=='rejected'
    assert edit_client.post(f"/api/v1/product-edits/{proposal['id']}/confirm").status_code==409
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute('SELECT stock FROM product_variant WHERE id=1').fetchone()[0]==3


def test_parent_variant_price_is_not_silently_changed_and_text_scope_is_visible(edit_client):
    assert edit_client.post('/api/v1/product-edits',json={'sku':'P002','changes':{'price_vnd':100000}}).status_code==409
    assert propose(edit_client,{'name':'Giày thể thao bản cập nhật'},sku='P002')['shared_content'] is True


@pytest.mark.parametrize('changes',[{}, {'stock':-1},{'stock':True},{'price_vnd':500},{'name':'  '},{'sql':'DROP TABLE product'}])
def test_invalid_edits_rejected_before_proposal(edit_client,changes):
    assert edit_client.post('/api/v1/product-edits',json={'sku':'A001','changes':changes}).status_code==422


def test_chat_understands_multi_field_vietnamese_and_preserves_newlines(edit_client):
    message='Sửa tiêu đề SKU A001 thành Giày thể thao màu đen\nMô tả: Giày dành cho hoạt động hằng ngày.\nSize 40.\nGiá bán 5 xị\nTồn kho 20'
    result=edit_client.post('/api/v1/chat',json={'message':message}).json()['data']
    assert result['intent']=='update_product'
    assert result['product_edit_proposal'] is not None
    fields={item['field']:item['after'] for item in result['product_edit_proposal']['changes']}
    assert fields=={'name':'Giày thể thao màu đen','description':'Giày dành cho hoạt động hằng ngày.\nSize 40.','price_vnd':500000,'stock':20}
    history=edit_client.get('/api/v1/conversations/'+result['conversation_id']).json()['data']
    assert 'product_edit_proposal' in json.dumps(history)


def test_missing_sku_followup_does_not_append_sku_into_description(edit_client):
    result=edit_client.post('/api/v1/chat',json={'message':'Sửa mô tả thành Mô tả này do chủ shop tự viết.'}).json()['data']
    assert result['facts']['missing_fields']==['sku']
    result=edit_client.post('/api/v1/chat',json={'message':'SKU A001','conversation_id':result['conversation_id']}).json()['data']
    assert result['product_edit_proposal']['changes'][0]['after']=='Mô tả này do chủ shop tự viết.'


def test_money_inside_explicit_content_is_not_a_price_or_stock_edit(edit_client):
    result=edit_client.post('/api/v1/chat',json={'message':'Sửa mô tả SKU A001 thành "Mẫu này có giá bán 100k, tồn kho 20 theo nội dung minh họa."'}).json()['data']
    changes=result['product_edit_proposal']['changes']
    assert len(changes)==1 and changes[0]['field']=='description'
    assert 'giá bán 100k' in changes[0]['after']


class RewriteAI:
    provider='gemini'
    model='synthetic'
    async def compose_product_edit(self,message,*,history,product):
        return ProductEditCopy(description=product['name']+'. '+product['description'])


def test_ai_rewrite_only_changes_requested_field(edit_client):
    edit_client.app.state.ai_provider=RewriteAI()
    result=edit_client.post('/api/v1/chat',json={'message':'Tối ưu mô tả SKU A001 cho rõ ràng hơn'}).json()['data']
    assert [field['field'] for field in result['product_edit_proposal']['changes']]==['description']
    assert result['product_edit_proposal']['status']=='pending'
    assert result['proposal'] is None
    assert is_product_edit_request('Có nên đổi tiêu đề sản phẩm này?') is False
    assert is_product_edit_request('Lập kế hoạch đăng video, viết lại mô tả') is False
    assert is_product_edit_request('Đừng sửa tiêu đề SKU A001 thành tên này') is False


def test_unique_product_name_can_resolve_edit_without_asking_for_sku_again(edit_client):
    edit_client.app.state.ai_provider=RewriteAI()
    result=edit_client.post('/api/v1/chat',json={'message':'Tối ưu mô tả cho Áo thun trơn'}).json()['data']
    assert result['product_edit_proposal']['sku']=='P001'
