import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert

from app.integrations.product_edits import editable_product, apply_product_edit, StaleProductEditError
from app.integrations.product_management import archive_product, product_detail, ProductConflictError
from app.models.product_edit import ProductEditProposal, ProductEditAudit
from app.schemas.product_edits import ProductChanges
from app.schemas.product_management import ProductArchive
from app.services.seller_tools import ProposalConflictError, ProposalNotFoundError


def create_product_edit(session,shop,*,sku,changes):
    changes = ProductChanges.model_validate(changes).model_dump(exclude_none=True)
    item = editable_product(shop,sku)
    if product_detail(shop, item['product_id'])['status'] == 'archived':
        raise ProposalConflictError('Sản phẩm đã được xóa khỏi gian hàng.')
    if item['target_kind'] == 'product' and item['variant_count'] and ({'stock','price_vnd'} & changes.keys()):
        raise ProposalConflictError('Sản phẩm có phân loại. Bạn chọn SKU phân loại cụ thể để sửa giá/tồn nhé.')
    before = {key:item[key] for key in ('name','description','price_vnd','stock')}
    before['_has_variants']=bool(item['variant_count'])
    changed = {key:value for key,value in changes.items() if before[key] != value}
    if not changed:
        raise ProposalConflictError('Các giá trị này đã giống dữ liệu trên shop.')
    proposal = ProductEditProposal(operation_id=str(uuid4()),shop_slug=shop.seller_shop_slug or 'local',
        sku=item['sku'],product_id=item['product_id'],variant_id=item['variant_id'],
        target_kind=item['target_kind'],status='pending',before_json=json.dumps(before,ensure_ascii=False),
        after_json=json.dumps(changed,ensure_ascii=False))
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


def create_product_archive(session, shop, product_id):
    item = product_detail(shop, product_id)
    if item['status'] == 'archived':
        raise ProposalConflictError('Sản phẩm đã được xóa khỏi gian hàng.')
    before = {'name': item['name'], 'status': item['status'], '_version': item['version']}
    proposal = ProductEditProposal(operation_id=str(uuid4()), shop_slug=shop.seller_shop_slug or 'local',
        sku=item['sku'] or '', product_id=item['id'], target_kind='product', status='pending',
        before_json=json.dumps(before, ensure_ascii=False), after_json='{"status":"archived"}')
    session.add(proposal)
    session.commit()
    return proposal


def _get(session,shop,proposal_id):
    proposal = session.get(ProductEditProposal,proposal_id)
    if proposal is None or proposal.shop_slug != (shop.seller_shop_slug or 'local'):
        raise ProposalNotFoundError(proposal_id)
    return proposal


def decide_product_edit(session,shop,proposal_id,*,approve):
    proposal = _get(session,shop,proposal_id)
    if proposal.status == ('approved' if approve else 'rejected'):
        return proposal,True
    if proposal.status not in (('pending','executing') if approve else ('pending',)):
        raise ProposalConflictError('Đề xuất đã được xử lý hoặc dữ liệu đã thay đổi.')
    if approve:
        proposal.status = 'executing'
        session.commit()
        try:
            if json.loads(proposal.after_json).get('status') == 'archived':
                payload = ProductArchive(request_id=proposal.operation_id,
                    expected_version=json.loads(proposal.before_json)['_version'])
                repeated = archive_product(shop, proposal.product_id, payload)['replayed']
            else:
                repeated = apply_product_edit(shop,proposal)
        except (StaleProductEditError, ProductConflictError) as error:
            proposal.status='conflict'
            proposal.decided_at=datetime.utcnow()
            session.commit()
            raise ProposalConflictError(str(error)) from error
        session.execute(insert(ProductEditAudit).values(proposal_id=proposal.id,
            shop_slug=proposal.shop_slug,sku=proposal.sku,before_json=proposal.before_json,
            after_json=proposal.after_json,created_at=datetime.utcnow()).on_conflict_do_nothing(index_elements=['proposal_id']))
        proposal.status='approved'
    else:
        repeated=False
        proposal.status='rejected'
    proposal.decided_at=datetime.utcnow()
    session.commit()
    session.refresh(proposal)
    return proposal,repeated


def edit_to_dict(proposal,*,idempotent=False):
    before,after=json.loads(proposal.before_json),json.loads(proposal.after_json)
    deleting = after.get('status') == 'archived'
    return {'id':proposal.id,'sku':proposal.sku,'product_name':before['name'],
        'target_kind':proposal.target_kind,'status':proposal.status,
        'action': 'archive' if deleting else 'edit',
        'changes':[] if deleting else [{'field':key,'before':before[key],'after':value} for key,value in after.items()],
        'shared_content':bool(before.get('_has_variants') and ({'name','description'} & after.keys())),
        'created_at':proposal.created_at,'decided_at':proposal.decided_at,'idempotent':idempotent}
