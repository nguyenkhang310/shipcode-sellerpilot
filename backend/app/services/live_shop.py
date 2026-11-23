"""Read-only shop grounding for Gemini Live, using the same queries as chat."""
from datetime import date, datetime, timedelta

from app.ai.contracts import ParsedCommand
from app.ai.fallback import extract_sku, normalize_text, parse_fallback
from app.ai.quick_reads import english_sales_text, quick_read, read_text, sales_metric_followup, sales_period_followup
from app.services.advisor import read_memory
from app.services.business_advisor import attach_business_brief, planning_fallback, planning_request
from app.services.chat import execute_command
from app.services.chat_reports import build_chat_report
from app.services.marketplace_performance import EXPERIMENTS
from app.services.conversations import (
    ASK_PRODUCT, contextual_read, conversation_memory, conversation_product, has_product_reference, history_messages,
    refers_to_published_product,
)
from app.services.order_assistant import order_answer
from app.services.seller_voice import summary_reply


def is_sales_question(message, *, timezone):
    today = datetime.now(timezone).date()
    if command := quick_read(message, today=today):
        return command.intent == 'shop_summary'
    text = english_sales_text(read_text(message))
    return bool(sales_period_followup(text, today=today) or sales_metric_followup(text, today=today))


def english_sales_answer(facts, *, today):
    end = date.fromisoformat(facts['to_date'])
    start = date.fromisoformat(facts['from_date'])
    if start != end:
        period = f'From {start:%d %b} to {end:%d %b %Y}'
    elif end == today:
        period = 'Today'
    elif end == today - timedelta(days=1):
        period = 'Yesterday'
    else:
        period = f'On {end:%d %b %Y}'

    status_labels = {'pending': 'awaiting confirmation', 'paid': 'awaiting pickup', 'shipped': 'in transit',
                     'delivered': 'delivered', 'cancelled': 'cancelled', 'returned': 'returned'}
    metric = facts.get('sales_metric')
    def orders(count):
        return f'{count:,} order' if count == 1 else f'{count:,} orders'

    if 'all_order_status_counts' in facts:
        count = facts['all_order_status_counts'].get(metric, 0)
        return f'Your shop currently has {orders(count)} {status_labels[metric]}.'

    def snapshot(label, prefix=''):
        count = facts[f'{prefix}order_count']
        value = facts[f'{prefix}{"value_vnd" if prefix else "order_value_vnd"}']
        if metric in status_labels:
            count = facts[f'{prefix}order_status_counts'].get(metric, 0)
            answer = f'{label}, {orders(count)} placed in the shop were {status_labels[metric]}.' if count != 1 else (
                f'{label}, {orders(count)} placed in the shop was {status_labels[metric]}.')
            if metric == 'delivered':
                answer += f' The delivered order value was {facts[f"{prefix}delivered_value_vnd"]:,} dong.'
            return answer
        if metric == 'units':
            units = facts[f'{prefix}units_sold']
            covered = facts[f'{prefix}orders_with_item_quantity']
            if covered == count:
                return f'{label}, your shop sold {units:,} units.'
            if covered:
                return f'{label}, I could count {units:,} units across {covered:,} of {count:,} valid orders.'
            return f'{label}, the order records lack item quantities, so I can’t count units sold.'
        if metric == 'orders':
            return f'{label}, your shop had {count:,} valid {"order" if count == 1 else "orders"}.'
        if metric == 'order_value':
            return f'{label}, total order value was {value:,} dong.'
        if metric == 'delivered_value':
            return f'{label}, delivered orders were worth {facts[f"{prefix}delivered_value_vnd"]:,} dong.'
        if metric == 'average_order':
            average = round(value / count) if prefix and count else facts['average_order_vnd']
            return (f'{label}, the average order was worth {average:,} dong.' if count
                    else f'{label}, there were no valid orders to calculate an average.')
        return f'{label}, your shop had {count:,} valid {"order" if count == 1 else "orders"} worth {value:,} dong.'

    answer = snapshot(period)
    if facts.get('compare_yesterday'):
        answer += ' ' + snapshot('By the same time yesterday', 'previous_')
    if metric == 'collected':
        answer = 'I don’t have the payout records to verify how much cash the shop received. ' + answer
    return answer


ENGLISH_PERIOD_MESSAGES = {
    'invalid_date': 'That date looks invalid. Which day would you like to check?',
    'multiple_periods': 'Which period should I check first? I can also compare today with the same time yesterday.',
    'range_limit': 'Choose a range of up to 30 days, or a calendar month.',
    'future_period': 'That period hasn’t started. Which past period would you like to check?',
}


def strategy_summary(brief, *, language='vi'):
    if language == 'en':
        focus = (brief.get('focus_product') or {}).get('name')
        return (f'Start with one small test for {focus}. I put the full plan in our chat.'
                if focus else 'Start with one small test. The full plan and what to measure are in our chat.')
    if funnel := brief.get('marketplace_funnel'):
        priority = funnel.get('priority')
        action = EXPERIMENTS[priority][0] if priority else 'Bạn có thể bắt đầu từ những tỷ lệ đã tính được.'
    elif brief.get('mode') == 'measurement_plan':
        action = 'Đặt mã cho từng video rồi theo dõi chúng trong cùng một khoảng thời gian.'
    elif brief.get('mode') == 'video_script' and (shots := brief.get('shot_list')):
        action = f"Mở video bằng câu này: {shots['hooks'][0]}"
    else:
        action = brief.get('execution', {}).get('first_action', '')
        if len(action.split()) > 26:
            action = 'Bắt đầu với việc ưu tiên mình đánh dấu ở đầu kế hoạch.'
    return (action + ' Mình để phần chi tiết trong cuộc trò chuyện để bạn xem lại.').strip()


def inspect_shop(session, shop, question, spoken='', *, conversation_id=None, sales_only=False, language='vi'):
    today = datetime.now(shop.timezone).date()
    # A complete spoken read carries the seller's actual date, SKU and stock
    # threshold. The Live model's tool description can paraphrase those slots.
    runs, since = conversation_memory(session, shop, conversation_id)
    request = spoken or question
    direct = quick_read(request, today=today) or contextual_read(request, runs, today=today)
    if sales_only and direct is None:
        period = sales_period_followup(english_sales_text(read_text(request)), today=today)
        if period is not None:
            direct = ParsedCommand(intent='shop_summary', **period)
    if sales_only and (not direct or direct.intent != 'shop_summary'):
        return None
    command = direct or parse_fallback(question, today=today)
    order = None if direct or command.intent == 'shop_summary' else order_answer(shop, question, runs)
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

    if spoken and not direct and command.intent == 'shop_summary':
        spoken_command = parse_fallback(spoken, today=today)
        if spoken_command.intent == 'shop_summary':
            # The model can expand "hôm nay" into a full date that also
            # contains "tháng 11". Use the seller's actual reporting period.
            command = spoken_command
    history = history_messages(runs)
    planning_message = spoken if not direct and planning_request(spoken, history) else question
    planning = not direct and planning_request(planning_message, history)
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
    preferences = read_memory(session, shop, 'shop')
    result = execute_command(session, shop, command, preferences=preferences)
    facts = result['facts']
    facts.update(product_context)
    answer = result['answer']
    spoken_summary = None
    if command.intent == 'shop_summary':
        if result['tool'] == 'get_shop_summary':
            answer = (english_sales_answer(facts, today=today) if language == 'en'
                      else summary_reply(facts, today=today, concise=True, focused=True))
            spoken_summary = answer.replace('**', '').replace('\n', ' ')
        elif language == 'en':
            issue = command.sales_period_issue or 'future_period'
            answer = ENGLISH_PERIOD_MESSAGES[issue]

    if command.intent == 'sales_advice':
        brief = attach_business_brief(shop, facts, message=planning_message, history=history, preferences=preferences)
        if brief:
            answer = planning_fallback(facts) or answer
            spoken_summary = strategy_summary(brief)
            if brief.get('marketplace_funnel'):
                return {'answer': answer, 'facts': {'business_advisory': brief}, 'report': None, 'spoken_summary': spoken_summary}
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

    output = {'answer': answer, 'facts': compact, 'report': build_chat_report(result['tool'], facts),
              'spoken_summary': spoken_summary}
    if result['tool'] == 'get_shop_summary':
        output['sales_context'] = {key: facts[key] for key in ('to_date', 'days', 'calendar_period', 'sales_metric',
                                                             'compare_yesterday', 'all_order_status_counts')
                                   if key in facts}
    return output
