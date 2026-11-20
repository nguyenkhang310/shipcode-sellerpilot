"""Read-only shop grounding for Gemini Live, using the same queries as chat."""
from datetime import datetime

from app.ai.fallback import extract_sku, normalize_text, parse_fallback
from app.services.advisor import read_memory
from app.services.business_advisor import attach_business_brief, planning_fallback, planning_request
from app.services.chat import execute_command
from app.services.chat_reports import build_chat_report
from app.services.conversations import (
    ASK_PRODUCT, conversation_memory, conversation_product, has_product_reference, history_messages,
    refers_to_published_product,
)
from app.services.order_assistant import order_answer


def inspect_shop(session, shop, question, spoken='', *, conversation_id=None):
    today = datetime.now(shop.timezone).date()
    command = parse_fallback(question, today=today)
    runs, since = conversation_memory(session, shop, conversation_id)
    order = None if command.intent == 'shop_summary' else order_answer(shop, question, runs)
    if order is not None:
        facts = order['facts']
        spoken = {}
        for key in ('order_lookup', 'order_comparison'):
            if key in facts:
                rows = facts[key] if key == 'order_comparison' else [facts[key]]
                # Tracking details stay in the order UI. Voice only needs
                # status, value and whether a tracking number exists.
                spoken[key] = [{field: row[field] for field in
                    ('id', 'found', 'status', 'total_vnd', 'shipping_carrier', 'missing_id')
                    if field in row} | {'has_tracking': bool(row.get('tracking_number'))} for row in rows]
        return {'answer': order['answer'], 'facts': spoken, 'order_id': facts.get('order_action', {}).get('id')}

    if spoken and command.intent == 'shop_summary':
        spoken_command = parse_fallback(spoken, today=today)
        if spoken_command.intent == 'shop_summary':
            # The model can expand "hôm nay" into a full date that also
            # contains "tháng 11". Use the seller's actual reporting period.
            command = spoken_command
    history = history_messages(runs)
    planning_message = spoken if planning_request(spoken, history) else question
    planning = planning_request(planning_message, history)
    product_context = {}
    if planning:
        sku = extract_sku(normalize_text(spoken))
        # Prefer the seller's reference over a SKU guessed while rephrasing it.
        referent = spoken if has_product_reference(spoken) else question
        if not sku and has_product_reference(referent):
            if planning_request(referent, history):
                planning_message = referent
            product_context = conversation_product(session, shop, conversation_id, runs, since,
                published_only=refers_to_published_product(referent))
            if not product_context or product_context.get('selected_product', {}).get('found') is False:
                return {'answer': ASK_PRODUCT, 'facts': {'product_reference_missing': True}, 'report': None}
            sku = product_context.get('selected_product', {}).get('sku')
        elif not sku:
            sku = command.sku
        command = command.model_copy(update={'intent': 'sales_advice', 'sku': sku})
    if command.intent not in {'shop_summary', 'inventory_query', 'product_search', 'sales_advice'}:
        return None
    result = execute_command(session, shop, command)
    facts = result['facts']
    facts.update(product_context)
    answer = result['answer']

    if command.intent == 'sales_advice':
        brief = attach_business_brief(shop, facts, message=planning_message, history=history,
                                      preferences=read_memory(session, shop, 'shop'))
        if brief:
            answer = planning_fallback(facts) or answer
        compact = {key: facts[key] for key in ('period', 'tasks', 'selected_product', 'data_limits')
                   if key in facts}
        if brief:
            compact['business_advisory'] = {key: brief[key] for key in (
                'mode', 'horizon_days', 'focus_product', 'focus_selection_reason', 'commercial_constraints',
            )}
        if 'period' in compact:
            compact['period'] = {key: value for key, value in compact['period'].items() if key != 'series'}
        compact['top_products'] = facts.get('top_products', [])[:3]
        comparison = facts.get('business_analysis', {}).get('comparison')
        if comparison:
            compact['comparison'] = comparison
    else:
        compact = {key: value for key, value in facts.items() if key != 'series'}
        if isinstance(compact.get('items'), list):
            compact['items'] = compact['items'][:5]

    return {'answer': answer, 'facts': compact, 'report': build_chat_report(result['tool'], facts)}
