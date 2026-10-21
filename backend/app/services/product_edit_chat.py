"""Natural seller commands -> preview, never a write to the storefront."""
import json
import re
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

from app.ai.contracts import AIProviderError
from app.ai.edit_contracts import ProductEditCopy
from app.ai.fallback import extract_sku
from app.ai.listing_contracts import ListingCopy
from app.ai.money import NUMBER, money_mentions, plain
from app.ai.small_talk import social_reply
from app.ai.quick_reads import read_text
from app.ai.quantities import quantity_value
from app.integrations import management
from app.integrations.product_edits import editable_product
from app.integrations.ute_mall import ShopItemNotFoundError
from app.models.agent_run import AgentRun
from app.services.business_advisor import planning_request, business_reply_issue
from app.services.conversations import recent_runs, history_messages, resolve_message
from app.services.product_edits import create_product_edit, edit_to_dict
from app.services.seller_tools import ProposalConflictError

LABELS={'name':'tiêu đề','description':'mô tả','price_vnd':'giá bán','stock':'tồn kho','sku':'SKU'}


def is_product_edit_request(message):
    text=plain(message).lower()
    if planning_request(message) or re.search(r'\b(?:co nen|neu|gia su|tu van|nen sua|nen doi)\b',text):
        return False
    if re.search(r'\b(?:khong|dung|chua)\s+(?:(?:can|muon)\s+)?(?:sua|doi|cap nhat|toi uu|viet lai)\b',text):
        return False
    return bool(re.search(r'\b(?:sua|doi|cap nhat|toi uu|viet lai|soan lai)\b',text)
        and re.search(r'\b(?:tieu de|ten san pham|doi ten|sua ten|cap nhat ten|mo ta|ton(?: kho)?|so luong(?: ton)?)\b',text))


def _text_value(message,label):
    match=re.search(label+r'(?:\s+(?:cho|của|cua))?(?:\s+sku\s+[a-z0-9._-]+)?\s*(?:thành|thanh|là|la|[:=])\s*',message,re.I)
    if not match:
        return None
    quoted=re.match(r'["“]([\s\S]*?)["”]',message[match.end():])
    if quoted:
        return quoted[1].strip()
    boundary=rf'(?:\n|[,;])\s*(?=(?:(?:giá(?: bán| mới)?|gia(?: ban| moi)?|tồn(?: kho)?|ton(?: kho)?|số lượng|so luong)\s*(?:(?:[:=]|thành|thanh|là|la|còn|con)\s*)?{NUMBER}\b|(?:mô tả|mo ta|tiêu đề|tieu de|tên sản phẩm|ten san pham)\s*(?:[:=]|thành|thanh|là|la)))'
    value=re.split(boundary,message[match.end():],maxsplit=1,flags=re.I)[0]
    value=value.strip().strip('"“”')
    return value if value else None


def _mask_content(message,changes):
    for field in ('name','description'):
        value=changes.get(field)
        if value:
            message=message.replace(value,' '*len(value),1)
    return message


def local_changes(message):
    changes={}
    for field,label in (('name',r'(?:tiêu đề|tieu de|tên(?: sản phẩm)?|ten(?: san pham)?|đổi tên|doi ten)'),('description',r'(?:mô tả|mo ta)')):
        value=_text_value(message,label)
        if value is not None:
            changes[field]=value
    commerce=_mask_content(message,changes)
    for match in re.finditer(r'(?:giá|gia)(?:\s+(?:bán|ban|mới|moi))?(?:\s+sku\s+[a-z0-9._-]+)?\s*(?:(?::|=|thành|thanh|là|la|xuống|xuong|lên|len|còn|con)\s*)?',commerce,re.I):
        mentions=money_mentions(commerce[match.end():])
        if mentions and mentions[0].start==0 and mentions[0].value is not None:
            changes['price_vnd']=mentions[0].value
    stock=re.search(r'(?:tồn(?: kho)?|ton(?: kho)?|số lượng(?: tồn)?|so luong(?: ton)?)(?:\s+sku\s+[a-z0-9._-]+)?\s*(?:(?::|=|thành|thanh|là|la|còn|con)\s*)?',commerce,re.I)
    if stock:
        tail=re.split(r'[\n;]|\s*,\s*(?=[^\W\d_])',commerce[stock.end():],maxsplit=1)[0]
        value=quantity_value(read_text(tail))
        if value is not None:
            changes['stock']=value
    return changes


def pending_edit(runs):
    for run in reversed(runs):
        if run.intent == 'unknown' and run.tool_name is None and social_reply(run.message):
            continue
        if run.intent == 'update_product':
            return json.loads(run.facts_json).get('pending_edit_message')
        break
    return None


def _target_query(message):
    match=re.search(r'(?:tiêu đề|mô tả|tên sản phẩm)\s+(?:cho|của)\s+(?:sản phẩm\s+)?(.+?)(?=\s+(?:thành|sao cho|cho rõ|cho hay)|[;\n]|$)',message,re.I)
    if not match:
        return None
    value=match[1].strip(' ."“”')
    return value if 2<=len(value)<=200 and not value.lower().startswith('sku') else None


async def handle_product_edit(session,shop,provider,*,message,conversation_id=None):
    started=perf_counter()
    conversation_id=conversation_id or str(uuid4())
    runs=recent_runs(session,shop,conversation_id)
    history=history_messages(runs)
    original=pending_edit(runs)
    cancelled=bool(original and re.fullmatch(
        r'(?:(?:minh|toi|em) )?(?:(?:thoi )?khong sua nua|huy (?:yeu cau sua|chinh sua)|bo chinh sua|'
        r'(?:dung|chua|khong)(?: can| muon)? (?:sua|doi|cap nhat|toi uu|viet lai)\b.*)',read_text(message)))
    instruction=(original+'\n'+message) if original else message
    bare_sku=extract_sku(message.lower()) if re.fullmatch(r'(?:sku\s*[:#-]?\s*)?[a-z0-9._-]+',message.strip(),re.I) else None
    if original and bare_sku:
        instruction=original
    resolved=resolve_message(instruction,runs)
    sku=bare_sku or extract_sku(resolved.lower())
    facts={}
    named_target=_target_query(instruction)
    if named_target and not re.search(r'\bsku\b',instruction,re.I):
        found=management.products(shop,named_target,limit=4)
        if len(found['items'])==1:
            sku=found['items'][0]['sku']
        elif found['items']:
            sku=None
            facts['items']=found['items']
    if not sku and original and not is_product_edit_request(message):
        found=management.products(shop,message,limit=4)
        if len(found['items'])==1:
            sku=found['items'][0]['sku']
            instruction=original
        elif found['items']:
            facts['items']=found['items']
    proposal=None
    mode,source,model,reason='ai','deterministic_parser',None,None
    if cancelled:
        answer='Mình đã bỏ yêu cầu sửa đang chờ. Sản phẩm trong shop vẫn giữ nguyên.'
    elif not sku:
        facts.update(missing_fields=['sku'],pending_edit_message=instruction)
        choices='\n'+'\n'.join(f"• {p['name']} — SKU {p['sku']}" for p in facts.get('items',[])) if facts.get('items') else ''
        answer='Bạn muốn sửa sản phẩm nào? Gửi SKU hoặc tên để mình tìm đúng món nhé.'+choices
    else:
        try:
            product=editable_product(shop,sku)
        except ShopItemNotFoundError:
            product=None
        if product is None:
            answer=f'Mình chưa tìm thấy SKU {sku} trong shop. Bạn kiểm tra lại mã nhé.'
            facts.update(missing_fields=['sku'],pending_edit_message=re.sub(r'\bsku\s*[:#-]?\s*'+re.escape(sku),'',instruction,flags=re.I))
        else:
            facts['selected_product']=product
            changes=local_changes(instruction)
            if original:
                # The new reply wins over a value in the unfinished request.
                # A bare count answers stock only when stock is what we asked.
                changes.update(local_changes(message))
                last_edit=next((run for run in reversed(runs) if run.intent=='update_product'),None)
                waiting=json.loads(last_edit.facts_json).get('missing_fields',[]) if last_edit else []
                count=quantity_value(read_text(message)) if waiting==['stock'] else None
                if count is not None:
                    changes['stock']=count
            request_text=plain(_mask_content(instruction,changes)).lower()
            requested={field for field,pattern in (
                ('name',r'tieu de|ten san pham|doi ten|sua ten|cap nhat ten'),('description',r'mo ta'),
                ('stock',r'\bton(?: kho)?\b|so luong(?: ton)?'),('price_vnd',r'gia ban|gia moi|doi gia|sua gia|gia\s*(?:[:=]|thanh|la)')) if re.search(pattern,request_text)}
            rewrite=bool(re.search(r'toi uu|viet lai|soan lai|tu viet|hay hon',plain(instruction).lower()))
            missing=requested-changes.keys()
            if missing & {'name','description'} and callable(getattr(provider,'compose_product_edit',None)):
                try:
                    copy=ProductEditCopy.model_validate(await provider.compose_product_edit(instruction,history=history,product=product))
                    for field in ('name','description'):
                        value=getattr(copy,field)
                        evidence=getattr(copy,field+'_evidence')
                        if field in requested and field not in changes and value is not None:
                            if rewrite or (evidence and evidence in instruction and value==evidence.strip()):
                                changes[field]=value
                    evidence_text=product['name']+'\n'+(product['description'] or '')+'\n'+instruction
                    ListingCopy.model_validate({key:changes.get(key) for key in ('name','description')},context={'seller_text':evidence_text})
                    issue=business_reply_issue(' '.join(str(changes.get(key,'')) for key in ('name','description')),
                        {'business_advisory':{'mode':'content_edit','focus_product':{'name':product['name']}},'selected_product':product},
                        seller_context=instruction)
                    if issue:
                        raise AIProviderError('invalid_response',stage=issue)
                    source=getattr(provider,'response_provider',getattr(provider,'provider','gemini'))
                    model=getattr(provider,'response_model',getattr(provider,'model',None))
                except (AIProviderError,ValidationError,ValueError,TypeError) as error:
                    mode,reason='fallback',getattr(error,'reason','invalid_response')
                    changes=local_changes(instruction)
            missing=requested-changes.keys()
            if missing or not changes:
                fields=sorted(missing or {'name','description'})
                answer='Mình cần '+', '.join(LABELS[field]+' mới' for field in fields)+' để tạo bản xem trước. Bạn gửi phần còn thiếu nhé.'
                facts.update(missing_fields=fields,pending_edit_message=instruction)
            else:
                try:
                    proposal=create_product_edit(session,shop,sku=sku,changes=changes)
                    answer='Mình đã chuẩn bị bản sửa '+', '.join(LABELS[field] for field in json.loads(proposal.after_json))+'. Bạn xem thay đổi bên dưới rồi xác nhận; shop chưa được cập nhật.'
                except (ProposalConflictError,ValidationError) as error:
                    answer=str(error) if isinstance(error,ProposalConflictError) else 'Giá trị mới chưa hợp lệ. Tiêu đề cần 3–200 ký tự, giá từ 1.000đ, tồn kho là số nguyên không âm.'
    run=AgentRun(conversation_id=conversation_id,shop_slug=shop.seller_shop_slug or 'local',
        product_edit_proposal_id=proposal.id if proposal else None,message=message,answer=answer,
        intent='update_product',mode=mode,status='completed' if mode=='ai' else 'fallback',
        provider=source,model=model,fallback_reason=reason,tool_name='prepare_product_edit',
        tool_arguments_json='{}',facts_json=json.dumps(facts,ensure_ascii=False,default=str),
        elapsed_ms=round((perf_counter()-started)*1000))
    session.add(run)
    session.commit()
    session.refresh(run)
    return {'run_id':run.id,'conversation_id':conversation_id,'intent':'update_product','mode':mode,
        'provider':source,'model':model,'fallback_reason':reason,'tool':'prepare_product_edit',
        'facts':facts,'answer':answer,'proposal':None,'product_draft':None,
        'product_edit_proposal':edit_to_dict(proposal) if proposal else None,
        'suggestions':['Tối ưu mô tả cho SKU '+sku] if sku and proposal else [],'integration_mode':'local_store'}
