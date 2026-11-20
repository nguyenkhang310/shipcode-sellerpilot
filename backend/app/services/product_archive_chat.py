"""Prepare one confirmed catalog removal from an explicit seller request."""
import json
import re
from unicodedata import normalize
from uuid import uuid4

from app.ai.fallback import extract_sku
from app.ai.money import plain
from app.integrations import management
from app.integrations.ute_mall import ShopItemNotFoundError
from app.models.agent_run import AgentRun
from app.services.conversations import conversation_memory, conversation_product
from app.services.product_edits import create_product_archive, edit_to_dict
from app.services.seller_tools import ProposalConflictError


DELETE = re.compile(r'^(?:(?:ban|hay|vui long|minh muon|toi muon|giup minh|giup toi) )*'
                    r'(?:xoa(?: khoi gian hang)?|go khoi gian hang|bo khoi shop) '
                    r'(?:san pham|mat hang|mon|sku|(?:cai|mau)(?= (?:nay|do)\b))\b'
                    r'|^(?:please )?(?:delete|remove) (?:this product|the product|product|sku)\b')


def is_product_archive_request(message):
    text = plain(message).casefold().strip()
    return bool(DELETE.match(text) and '?' not in message and not re.search(
        r'\b(?:neu|co nen|tat ca|all products|how to|cach xoa|(?:va|hoac) (?:xoa|san pham|sku))\b', text))


def prepare_product_removal(session, shop, message, conversation_id):
    conversation_id = conversation_id or str(uuid4())
    runs, since = conversation_memory(session, shop, conversation_id)
    message = normalize('NFC', message)
    prefix = DELETE.match(plain(message).casefold().strip())
    target = (message.strip()[prefix.end():] if prefix else message).strip(' .,:!"“”')
    target = re.sub(r'\s+(?:ra |khỏi )(?:gian hàng|shop)|\s+(?:giúp mình|giúp tôi|nha|nhé|from the shop)$',
                    '', target, flags=re.I).strip()
    sku = extract_sku(message.casefold()) or (extract_sku('sku ' + target.lower())
        if not prefix or prefix.group().endswith('sku') else None)
    item = proposal = None
    if sku:
        try:
            item = shop.get_item_by_sku(sku)
        except ShopItemNotFoundError:
            pass
    elif plain(target).casefold() in ('nay', 'do', 'vua dang') or plain(message.strip()).casefold().startswith(
            ('delete this product', 'remove this product')):
        item = conversation_product(session, shop, conversation_id, runs, since).get('selected_product')
    elif target:
        search = management.products(shop, target, limit=2)
        if search['total'] == 1:
            item = {'product_id': search['items'][0]['id']}
    if item and item.get('product_id'):
        try:
            proposal = create_product_archive(session, shop, item['product_id'])
        except ProposalConflictError as error:
            answer = str(error)
        else:
            data = edit_to_dict(proposal)
            answer = f"Mình đã tìm thấy **{data['product_name']}**. Bạn xem lại rồi xác nhận xóa khỏi gian hàng nhé."
    else:
        answer = 'Bạn muốn xóa sản phẩm nào? Cho mình tên đầy đủ hoặc mã SKU của một sản phẩm nhé.'
    facts = {'product_archive_needs_target': not (item and item.get('product_id'))}
    run = AgentRun(conversation_id=conversation_id, shop_slug=shop.seller_shop_slug or 'local',
        product_edit_proposal_id=proposal.id if proposal else None, message=message, answer=answer,
        intent='delete_product', mode='ai', status='completed', provider='deterministic_parser',
        tool_name='prepare_product_archive', elapsed_ms=0, facts_json=json.dumps(facts))
    session.add(run)
    session.commit()
    return {'run_id': run.id, 'conversation_id': conversation_id, 'answer': answer,
            'intent': run.intent, 'mode': run.mode, 'provider': run.provider, 'tool': run.tool_name,
            'facts': facts, 'model': None, 'fallback_reason': None, 'proposal': None,
            'product_edit_proposal': edit_to_dict(proposal) if proposal else None}


def archive_target_reply(message, runs):
    if not runs or runs[-1].tool_name != 'prepare_product_archive':
        return False
    if not json.loads(runs[-1].facts_json).get('product_archive_needs_target'):
        return False
    return bool(re.fullmatch(r'sku\s*[:#-]?\s*[\w.-]+|[A-Z0-9]+(?:-[A-Z0-9]+)+', message.strip(' .!'), re.I))
