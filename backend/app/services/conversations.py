import json
import re
from datetime import datetime

from sqlalchemy import select

from app.ai.fallback import extract_price, extract_sku, normalize_text
from app.ai.context import bounded_history
from app.ai.text import assistant_text
from app.ai.money import money_mentions
from app.ai.small_talk import social_reply
from app.ai.money import plain
from app.integrations.ute_mall import ShopItemNotFoundError
from app.models.action import ActionProposal
from app.models.agent_run import AgentRun
from app.models.product_draft import ProductDraft
from app.services.product_drafts import draft_to_dict
from app.services.seller_tools import proposal_to_dict
from app.models.product_edit import ProductEditProposal
from app.services.product_edits import edit_to_dict
from app.services.chat_reports import build_chat_report
from app.services.advisor import read_memory


PRODUCT_REFERENCE = re.compile(
    r'\b(?:(?:san pham|mon|mau|mat hang|hang|cai) (?:nay|do|vua dang)|'
    r'(?:moi|vua) dang(?! (?:ky|nhap)\b)|(?:this|that) (?:product|item)|(?:just|recently) listed)\b'
)
ASK_PRODUCT = 'Bạn muốn tư vấn cho sản phẩm nào? Cho mình tên hoặc mã SKU nhé.'


def recent_runs(session, shop, conversation_id, limit=12):
    if not conversation_id:
        return []
    rows = session.scalars(select(AgentRun).where(
        AgentRun.conversation_id == str(conversation_id),
        AgentRun.shop_slug == (shop.seller_shop_slug or "local"),
    ).order_by(AgentRun.id.desc()).limit(limit)).all()
    return list(reversed(rows))


def conversation_memory(session, shop, conversation_id):
    reset = read_memory(session, shop, 'system').get('reset_at')
    since = datetime.fromisoformat(reset) if reset else None
    runs = recent_runs(session, shop, conversation_id, limit=24)
    if since:
        runs = [run for run in runs if run.created_at >= since]
    for index in range(len(runs) - 1, -1, -1):
        if runs[index].tool_name == 'forget_assistant_memory':
            return runs[index + 1:], runs[index].created_at
    return runs, since


def has_product_reference(message):
    return bool(PRODUCT_REFERENCE.search(plain(message).casefold()) or re.search(r'\bnó\b', message.casefold()))


def conversation_product(session, shop, conversation_id, runs, since=None, *, published_only=False):
    """Resolve one product from documented selections or this thread's listings."""
    if not conversation_id:
        return {}
    statuses = ('published',) if published_only else ('collecting', 'ready', 'published')
    query = select(ProductDraft).where(
        ProductDraft.conversation_id == str(conversation_id),
        ProductDraft.shop_slug == (shop.seller_shop_slug or 'local'),
        ProductDraft.status.in_(statuses),
    )
    if since:
        query = query.where(ProductDraft.updated_at >= since)
    draft = session.scalar(query.order_by(ProductDraft.updated_at.desc(), ProductDraft.id.desc()).limit(1))

    if not published_only:
        for run in reversed(runs):
            if draft and run.created_at <= draft.updated_at:
                break
            if run.product_draft_id:
                continue
            facts = json.loads(run.facts_json)
            selection = facts.get('live_product_selection') or facts
            selected = selection.get('selected_product') or selection
            sku = selected.get('sku')
            if 'items' in selection and not sku:
                items = selection['items']
                if len(items) != 1:
                    return {}
                sku = items[0].get('sku')
            if sku:
                return {'selected_product': product_by_sku(shop, sku)}

    if draft and draft.status == 'published' and draft.sku:
        return {'selected_product': product_by_sku(shop, draft.sku)}
    if draft:
        return {'draft_context': {'name': draft.name, 'description': draft.description,
                                  'category': draft.category_name, 'selling_price_vnd': draft.price_vnd,
                                  'stock': draft.stock, 'published': False}}
    return {}


def product_by_sku(shop, sku):
    try:
        return shop.get_item_by_sku(sku)
    except ShopItemNotFoundError:
        return {'sku': sku, 'found': False}


def refers_to_published_product(message):
    return bool(re.search(r'\b(?:vua dang|moi dang|just listed|recently listed)\b', plain(message).casefold()))


def resolve_message(message, runs):
    """Resolve references only from server-observed tools, never from LLM guesses."""
    text = normalize_text(message)
    if not runs:
        return message
    meaningful = [run for run in runs if not (run.intent == 'unknown' and run.tool_name is None and social_reply(run.message))]
    if not meaningful:
        return message
    last = meaningful[-1]
    facts = json.loads(last.facts_json)
    # Keep the last unambiguous tool selection through acknowledgements/advice.
    # A new search (including an empty search) replaces that selection.
    for prior in reversed(runs):
        prior_facts = json.loads(prior.facts_json)
        if "items" in prior_facts or "sku" in prior_facts or "selected_product" in prior_facts:
            facts = prior_facts
            break
    if facts.get("selected_product"):
        facts = {**facts, **facts["selected_product"]}
    selected_sku = None
    choice = re.search(r"(?:thứ|thu|số|so)\s*(\d+)", text)
    items = facts.get("items", [])
    if choice:
        if not 0 < int(choice.group(1)) <= len(items):
            return message  # An invalid selection must never default to another item.
        selected_sku = items[int(choice.group(1)) - 1].get("sku")
    elif any(word in text for word in ("đầu tiên", "dau tien")) and items:
        selected_sku = items[0].get("sku")
    elif len(items) == 1:
        selected_sku = items[0].get("sku")
    elif facts.get("sku") and facts.get("found") is not False:
        selected_sku = facts["sku"]

    explicit = extract_sku(text)
    reference = any(word in text for word in (
        "nó", "cái này", "mẫu này", "sản phẩm này", "mã này", "cai nay", "ma nay",
        "đổi giá", "doi gia", "giá", "gia", "tồn", "ton", "còn", "con", "thứ", "thu", "đầu tiên",
    ))
    if not explicit and selected_sku and reference:
        return message + "\nSKU " + selected_sku
    # A bare SKU or bare price can complete the immediately previous clarification.
    missing = facts.get("missing_fields", [])
    if last.intent == "change_price" and missing:
        if explicit and "sku" in missing:
            old_price = extract_price(normalize_text(last.message), sku=extract_sku(normalize_text(last.message)))
            return f"Đổi giá SKU {explicit}" + (f" thành {old_price}đ" if old_price is not None else "")
        money = money_mentions(text.strip(' .!?'))
        money_only = len(money) == 1 and money[0].start == 0 and money[0].end == len(text.strip(' .!?'))
        if "new_price_vnd" in missing and facts.get("sku") and money_only:
            return f"Đổi giá SKU {facts['sku']} thành {message}"
    return message


def history_messages(runs):
    last_reset = next((i for i in range(len(runs) - 1, -1, -1)
                       if runs[i].tool_name == 'forget_assistant_memory'), None)
    if last_reset is not None:
        runs = runs[last_reset + 1:]
    result = []
    for run in runs[-12:]:
        result.append({'role': 'user', 'content': run.message})
        # A failed generation is not evidence that the next generation is also
        # offline. Keep the seller's question without feeding error text back.
        if not (run.intent == 'unknown' and run.mode == 'fallback' and run.fallback_reason):
            result.append({'role': 'assistant', 'content': assistant_text(run.answer)})
    return bounded_history(result)


def run_data(session, run):
    proposal = session.get(ActionProposal, run.proposal_id) if run.proposal_id else None
    product_draft = session.get(ProductDraft, run.product_draft_id) if run.product_draft_id else None
    product_edit = session.get(ProductEditProposal,run.product_edit_proposal_id) if run.product_edit_proposal_id else None
    facts = json.loads(run.facts_json)
    draft_data = draft_to_dict(product_draft) if product_draft else None
    if draft_data and product_draft.status == 'collecting':
        draft_data['missing_fields'] = list(dict.fromkeys(facts.get('pending_fields', []) + draft_data['missing_fields']))
    return {
        "run_id": run.id, "conversation_id": run.conversation_id,
        "answer": assistant_text(facts.get('live_spoken_answer') or run.answer), "intent": run.intent, "mode": run.mode,
        "provider": run.provider, "model": run.model, "fallback_reason": run.fallback_reason,
        "tool": run.tool_name, "facts": facts,
        "proposal": proposal_to_dict(proposal) if proposal else None,
        "product_edit_proposal": edit_to_dict(product_edit) if product_edit else None,
        "product_draft": draft_data,
        "suggestions": [], "integration_mode": "local_store",
        "report": build_chat_report(run.tool_name, facts),
    }


def turn_data(session, run):
    response = run_data(session, run)
    return {'message': response['facts'].get('live_spoken_message') or run.message,
            'created_at': run.created_at.isoformat() + 'Z', 'response': response}
