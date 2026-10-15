"""Read-only seller advice, evidence-backed memory and exact price arithmetic."""
import json
import re
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from pydantic import ValidationError
from sqlalchemy import delete, select, func
from sqlalchemy.dialects.sqlite import insert

from app.ai.advisor_contracts import AdviceExtraction
from app.ai.contracts import AIProviderError
from app.ai.fallback import PRICE_RE, extract_sku, normalize_text, parse_money
from app.integrations import management
from app.integrations.ute_mall import ShopItemNotFoundError
from app.models.assistant_memory import AssistantMemory

MONEY_FIELDS = {'unit_cost_vnd', 'packaging_vnd', 'shipping_subsidy_vnd', 'ads_per_order_vnd',
                'other_cost_vnd', 'target_profit_vnd', 'selling_price_vnd'}
ORDER_COST_FIELDS = ('packaging_vnd', 'shipping_subsidy_vnd', 'ads_per_order_vnd', 'other_cost_vnd')
COST_LABELS = {'unit_cost_vnd': 'giá vốn', 'packaging_vnd': 'đóng gói',
               'shipping_subsidy_vnd': 'phần shop hỗ trợ vận chuyển',
               'ads_per_order_vnd': 'quảng cáo mỗi đơn', 'other_cost_vnd': 'chi phí khác',
               'fee_percent': 'tổng phí theo giá bán'}


def is_forget_request(message):
    text = normalize_text(message)
    if re.search(r'\b(?:nếu|giả sử|có nên|làm sao|neu|gia su|co nen|lam sao)\b', text):
        return False
    return bool(re.search(r'^(?:(?:bạn|hãy|vui lòng|mình muốn|tôi muốn|giúp mình|ban|hay)\s+)*(?:quên|xóa|xoá|quen|xoa).{0,25}(?:bộ nhớ|ghi nhớ|thông tin đã nhớ|thong tin da nho|bo nho|ghi nho)', text))


def memory_rows(session, shop, scope=None):
    query = select(AssistantMemory).where(AssistantMemory.shop_slug == (shop.seller_shop_slug or 'local'))
    if scope is not None:
        query = query.where(AssistantMemory.scope == scope)
    else:
        query = query.where(AssistantMemory.scope != 'system')
    return session.scalars(query.order_by(AssistantMemory.updated_at.desc())).all()


def read_memory(session, shop, scope):
    values = {row.key: json.loads(row.value_json) for row in memory_rows(session, shop, scope)}
    tenant = shop.seller_shop_slug or 'local'
    for operation, data in session.info.get('advisor_writes', []):
        if data['shop_slug'] != tenant:
            continue
        if operation == 'save' and data['scope'] == scope:
            values[data['key']] = json.loads(data['value_json'])
        elif operation == 'delete' and (data['scopes'] is None or scope in data['scopes']):
            if data['keys'] is None:
                values.clear()
            else:
                for key in data['keys']:
                    values.pop(key, None)
    return values


def forget_memory(session, shop):
    tenant = shop.seller_shop_slug or 'local'
    count = session.scalar(select(func.count(AssistantMemory.id)).where(
        AssistantMemory.shop_slug == tenant, AssistantMemory.scope != 'system'))
    _delete_memory(session, shop)
    # Keep only a non-personal reset timestamp so old chat text cannot silently
    # restore forgotten information after a reset from the settings/API.
    _save(session, shop, 'system', 'reset_at', datetime.utcnow().isoformat(), 'User-requested memory reset')
    return count


def _save(session, shop, scope, key, value, evidence):
    values = dict(shop_slug=shop.seller_shop_slug or 'local', scope=scope, key=key,
                  value_json=json.dumps(value, ensure_ascii=False), evidence=evidence,
                  updated_at=datetime.utcnow())
    if session.info.get('defer_advisor_writes'):
        session.info.setdefault('advisor_writes', []).append(('save', values))
        return
    _write_memory(session, values)


def _write_memory(session, values):
    session.execute(insert(AssistantMemory).values(**values).on_conflict_do_update(
        index_elements=['shop_slug', 'scope', 'key'],
        set_={key: values[key] for key in ('value_json', 'evidence', 'updated_at')},
    ))


def _delete_memory(session, shop, scopes=None, keys=None):
    data = {'shop_slug': shop.seller_shop_slug or 'local', 'scopes': scopes, 'keys': keys}
    if session.info.get('defer_advisor_writes'):
        session.info.setdefault('advisor_writes', []).append(('delete', data))
    else:
        _apply_memory_delete(session, data)


def _apply_memory_delete(session, data):
    query = delete(AssistantMemory).where(AssistantMemory.shop_slug == data['shop_slug'])
    if data['scopes'] is not None:
        query = query.where(AssistantMemory.scope.in_(data['scopes']))
    if data['keys'] is not None:
        query = query.where(AssistantMemory.key.in_(data['keys']))
    session.execute(query)


def flush_memory_writes(session):
    # Keep SQLite free of write locks while waiting for remote inference.
    for operation, data in session.info.pop('advisor_writes', []):
        if operation == 'save':
            _write_memory(session, data)
        else:
            _apply_memory_delete(session, data)


def _valid_evidence(evidence, message):
    return normalize_text(evidence) in normalize_text(message)


def _grounded_number(update, message):
    if not _valid_evidence(update.evidence, message):
        return False
    value = update.value
    if update.field in {'fee_percent', 'target_margin_percent', 'target_markup_percent', 'discount_percent'}:
        values = [Decimal(raw.replace(',', '.')) for raw in re.findall(r'(\d+(?:[.,]\d+)?)\s*%', update.evidence)]
        limit = 10_000 if update.field == 'target_markup_percent' else 100
        return 0 <= value <= limit and value in values
    if update.field == 'units_per_order':
        return (value == value.to_integral_value() and 1 <= value <= 10_000
                and str(int(value)) in re.findall(r'\b\d+\b', update.evidence))
    values = [parse_money(raw, unit) for raw, unit in PRICE_RE.findall(normalize_text(update.evidence))]
    return value == value.to_integral_value() and int(value) in values


def _valid_preference(update, message):
    evidence = normalize_text(update.evidence)
    return (_valid_evidence(update.evidence, message)
            and normalize_text(update.value) in evidence
            and not re.search(r'\b(?:nếu|giả sử|neu|gia su)\b', normalize_text(message))
            and not re.search(r'mật khẩu|số điện thoại|bỏ qua|password|system|confirm|xác nhận', evidence)
            and bool(re.search(r'\b(?:mình|tôi|em|shop|trả lời|tra loi|minh|toi|khách mục tiêu|mục tiêu|ngân sách|ngắn gọn|nói|giọng)\b', normalize_text(message))))


def shop_context(shop, days=7):
    stats = management.dashboard(shop, days)
    today = stats if days == 1 else management.dashboard(shop, 1)
    period_keys = ('days', 'from_date', 'to_date', 'order_count', 'order_value_vnd',
                   'average_order_vnd', 'delivered_value_vnd', 'change_percent', 'cancelled_count')
    facts = {'shop': stats['shop'], 'period': {k: stats[k] for k in period_keys if k in stats},
             'today': {k: today[k] for k in ('to_date', 'order_count', 'order_value_vnd')},
             'tasks': stats['tasks'], 'top_products': stats['top_products'],
             'top_products_sales_scope': 'all_time_catalog_sold_count',
             'inventory': shop.inventory_overview(),
             'low_stock_sample': shop.low_stock(5, 5),
             'data_limits': ['Chưa có lượt xem, tỷ lệ chuyển đổi hay giá đối thủ.',
                             'Không có giá vốn hoặc phí thực tế nếu chủ shop chưa cung cấp.',
                             'Giá trị đơn và giá trị đơn đã giao không đồng nghĩa tiền thực thu.']}
    return facts


def _ceil(value):
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def _profit(price, cost, fee):
    return Decimal(price) * (1 - fee) - cost


def calculate_pricing(values):
    """Fees are % of gross selling price; margin is profit / selling price."""
    missing = [label for key, label in COST_LABELS.items() if key not in values]
    result = {'inputs': values, 'unaccounted_costs': missing,
              'basis': 'Ước tính trên các chi phí đã khai báo, chưa phải lợi nhuận ròng kế toán.',
              'assumptions': ['Mỗi đơn có 1 sản phẩm.'] if 'units_per_order' not in values else [],
              'formula': 'Lời mỗi sản phẩm = giá bán × (1 − tỷ lệ phí) − giá vốn − chi phí mỗi đơn / số sản phẩm mỗi đơn.'}
    if 'unit_cost_vnd' not in values:
        result.update(status='missing_cost', question='Giá vốn mỗi sản phẩm của bạn là bao nhiêu?')
        return result
    units = Decimal(str(values.get('units_per_order', 1)))
    fee = Decimal(str(values.get('fee_percent', 0))) / 100
    cost = Decimal(str(values['unit_cost_vnd'])) + sum(
        (Decimal(str(values.get(key, 0))) for key in ORDER_COST_FIELDS), Decimal(0)) / units
    if fee >= 1:
        result.update(status='infeasible', question='Tổng phí đã bằng hoặc vượt 100% giá bán. Bạn kiểm tra lại tỷ lệ phí nhé.')
        return result
    result.update(status='calculated', known_cost_per_unit_vnd=_ceil(cost),
                  break_even_price_vnd=_ceil(cost / (1 - fee)),
                  is_conditional=bool(missing))
    price = values.get('selling_price_vnd')
    if price is not None and price > 0:
        profit = _profit(price, cost, fee)
        result['at_selling_price'] = {'price_vnd': price,
            'profit_per_unit_vnd': int(profit.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            'margin_percent': float((100 * profit / Decimal(price)).quantize(Decimal('.01')))}
        if 'discount_percent' in values:
            discounted = int((Decimal(price) * (1 - Decimal(str(values['discount_percent'])) / 100)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            profit = _profit(discounted, cost, fee)
            result['after_discount'] = {'discount_percent': values['discount_percent'],
                'price_vnd': discounted,
                'profit_per_unit_vnd': int(profit.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
                'margin_percent': float((100 * profit / discounted).quantize(Decimal('.01'))) if discounted else None}
    candidates = []
    if 'target_profit_vnd' in values:
        candidates.append((cost + Decimal(str(values['target_profit_vnd']))) / (1 - fee))
    if 'target_markup_percent' in values:
        profit = Decimal(str(values['unit_cost_vnd'])) * Decimal(str(values['target_markup_percent'])) / 100
        candidates.append((cost + profit) / (1 - fee))
    if 'target_margin_percent' in values:
        margin = Decimal(str(values['target_margin_percent'])) / 100
        if fee + margin >= 1:
            result.update(status='infeasible_target', question='Biên lời mục tiêu cộng tỷ lệ phí phải thấp hơn 100%. Bạn muốn điều chỉnh mục tiêu nào?')
            return result
        candidates.append(cost / (1 - fee - margin))
    if candidates:
        price = _ceil(max(candidates) / 1000) * 1000
        profit = _profit(price, cost, fee)
        result['target_price'] = {'price_vnd': price,
            'profit_per_unit_vnd': int(profit.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            'margin_percent': float((100 * profit / price).quantize(Decimal('.01'))) if price else 0}
    else:
        result['comparison_scenarios'] = [
            {'assumed_margin_percent': margin,
             'price_vnd': _ceil(cost / (1 - fee - Decimal(margin) / 100) / 1000) * 1000}
            for margin in (10, 20, 30) if fee + Decimal(margin) / 100 < 1]
        result['question'] = 'Bạn muốn lời bao nhiêu tiền mỗi sản phẩm, hoặc biên lời bao nhiêu % trên giá bán?'
    if 'discount_percent' in values and not price:
        result['question'] = 'Bạn muốn giảm từ mức giá bán nào để mình tính lại tiền lời?'
    return result


def pricing_reply(pricing):
    if pricing['status'] in {'missing_cost', 'infeasible'}:
        return pricing['question']
    fmt = lambda value: f"{value:,}".replace(',', '.') + 'đ'
    answer = f"Với các chi phí bạn đã cho, mức hòa vốn ước tính là **{fmt(pricing['break_even_price_vnd'])}/sản phẩm**."
    if pricing.get('at_selling_price'):
        item = pricing['at_selling_price']
        answer += f"\n\nBán {fmt(item['price_vnd'])}: lời ước tính **{fmt(item['profit_per_unit_vnd'])}**, biên lời **{item['margin_percent']}%**."
    if pricing.get('target_price'):
        item = pricing['target_price']
        answer += f"\n\nĐể đạt mục tiêu đã nêu, bạn có thể cân nhắc **{fmt(item['price_vnd'])}**, lời ước tính {fmt(item['profit_per_unit_vnd'])}/sản phẩm."
    if pricing.get('after_discount'):
        item = pricing['after_discount']
        answer += f"\n\nGiảm {item['discount_percent']}% còn **{fmt(item['price_vnd'])}**: lời ước tính **{fmt(item['profit_per_unit_vnd'])}**/sản phẩm."
    if pricing['unaccounted_costs']:
        answer += '\n\nChưa tính phần bạn chưa cung cấp: ' + ', '.join(pricing['unaccounted_costs']) + '.'
    if pricing.get('question'):
        answer += '\n\n' + pricing['question']
    return answer


async def enrich_advice(session, shop, provider, *, message, resolved, conversation_id, runs, history):
    previous = next((json.loads(run.facts_json).get('pricing_context') for run in reversed(runs)
                     if json.loads(run.facts_json).get('pricing_context')), {}) or {}
    preferences = read_memory(session, shop, 'shop')
    extraction = AdviceExtraction()
    analysis_error = None
    if callable(getattr(provider, 'analyze_advice', None)):
        try:
            raw = await provider.analyze_advice(message, history=history, context={
                'seller_preferences': preferences, 'previous_pricing': previous,
                'previous_cost_inputs': read_memory(session, shop, previous['scope']) if previous.get('scope') else {}})
            raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.I)
            extraction = AdviceExtraction.model_validate_json(raw)
        except (AIProviderError, ValidationError, ValueError, TypeError, AttributeError) as error:
            analysis_error = getattr(error, 'reason', 'invalid_response')

    selected = None
    sku = extract_sku(normalize_text(message))
    if not sku and not extraction.new_scenario and not extraction.product_query:
        sku = extract_sku(normalize_text(resolved)) or previous.get('sku')
    candidates = []
    if extraction.product_query and not sku:
        candidates = management.products(shop, extraction.product_query, limit=4)['items']
        if len(candidates) == 1:
            sku = candidates[0]['sku']
    if sku:
        try:
            selected = shop.get_item_by_sku(sku)
        except ShopItemNotFoundError:
            selected = {'sku': sku, 'found': False}
    scope = 'sku:' + sku if selected and selected.get('found') is not False else 'conversation:' + conversation_id
    scenario_scope = scope + '@' + conversation_id
    if extraction.new_scenario and scope.startswith('conversation:'):
        _delete_memory(session, shop, scopes=[scope, scenario_scope])
    # Never carry one generic scenario's costs into a newly selected product.
    economics = read_memory(session, shop, scope)
    economics.update(read_memory(session, shop, scenario_scope))
    saved = []
    for update in extraction.preferences:
        if _valid_preference(update, message):
            _save(session, shop, 'shop', update.field, update.value, update.evidence)
            preferences[update.field] = update.value
            saved.append(update.field)
    valid_updates = [update for update in extraction.economics if _grounded_number(update, message)]
    if any(update.field == 'selling_price_vnd' for update in valid_updates):
        _delete_memory(session, shop, scopes=[scenario_scope], keys=['discount_percent'])
        economics.pop('discount_percent', None)
    targets = {'target_profit_vnd', 'target_margin_percent', 'target_markup_percent'}
    if any(update.field in targets for update in valid_updates):
        _delete_memory(session, shop, scopes=[scope], keys=list(targets))
        for key in targets:
            economics.pop(key, None)
    for update in valid_updates:
        value = int(update.value) if update.field in MONEY_FIELDS or update.field == 'units_per_order' else float(update.value)
        _save(session, shop, scenario_scope if update.field in {'selling_price_vnd', 'discount_percent'} else scope,
              update.field, value, update.evidence)
        economics[update.field] = value

    pricing = None
    if extraction.topic == 'pricing' or extraction.economics:
        values = dict(economics)
        if selected and selected.get('found') is not False and 'selling_price_vnd' not in values:
            values['selling_price_vnd'] = selected['price_vnd']
        pricing = calculate_pricing(values)
    return {'seller_preferences': preferences, 'memory_updates_saved': saved,
            'selected_product': selected, 'candidate_products': candidates if len(candidates) > 1 else [],
            'pricing_context': {'scope': scope, 'sku': sku, 'topic': extraction.topic} if pricing else None,
            'pricing_analysis': pricing, 'context_extraction_error': analysis_error}
