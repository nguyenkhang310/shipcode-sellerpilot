import json
import logging
import re
from uuid import uuid4
from datetime import date, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.ai.contracts import AIProvider, AIProviderError, ParsedCommand
from app.ai.fallback import (
    extract_price,
    extract_sku,
    extract_threshold,
    normalize_text,
    parse_fallback,
    reporting_days,
)
from app.ai.money import money_mentions, plain
from app.ai.catalog_query import catalog_lookup
from app.ai.quick_reads import quick_read, read_text, sales_period, sales_text, simple_pricing_read
from app.ai.text import conversational_text, reply_format_issue
from app.ai.small_talk import social_reply
from app.integrations.ute_mall import ShopItemNotFoundError, UTEMallRepository
from app.integrations import management
from app.services.conversations import (
    ASK_PRODUCT, contextual_read, conversation_memory, conversation_product, has_product_reference, history_messages,
    refers_to_published_product, resolve_message,
)
from app.models.agent_run import AgentRun
from app.models.action import ActionProposal
from app.services.advisor import (enrich_advice, forget_memory, is_forget_request,
                                  read_memory, pricing_reply, shop_context)
from app.services.seller_tools import (
    PriceUnchangedError,
    create_price_proposal,
    proposal_to_dict,
)
from app.services.seller_voice import ORDER_STATUS_TEXT, read_reply
from app.services.order_assistant import order_answer
from app.services.chat_reports import build_chat_report
from app.services.business_advisor import (attach_business_brief, planning_fallback, complete_business_reply,
                                          business_reply_issue, business_correction, planning_request)
from app.services.marketplace_performance import marketplace_for_plan

logger = logging.getLogger(__name__)


def reply_issue(answer: str, facts: dict | None = None, *, seller_context: str = '') -> str | None:
    format_issue = reply_format_issue(answer)
    if format_issue:
        return format_issue
    if re.search(r'đạt giới hạn số bước|hết bước xử lý|maximum steps reached', answer, re.I):
        return 'internal_agent_message'
    for match in re.finditer(r"\bđã\s+(?:cập nhật|đổi giá|thay đổi giá|đăng bán|đăng sản phẩm|đăng video|lên lịch|"
                             r"chạy quảng cáo|gửi tin|xác nhận đơn|hủy đơn|(?:xóa|gỡ) (?:sản phẩm|khỏi gian hàng)|"
                             r"lưu (?:đơn hàng|thay đổi))", answer, re.IGNORECASE):
        prefix = answer[:match.start()].rstrip()
        # "Nếu bạn đã đăng sản phẩm..." is a condition, not an executed write.
        if not re.search(r'\b(?:nếu|khi|sau khi)(?:\s+(?:bạn|mình|shop|chủ shop))?\s*$', prefix, re.IGNORECASE):
            return 'unexecuted_write_claim'
    if re.search(r"không cần (?:xử lý|xác nhận|gửi).{0,20}lại|lớn nhất trong tasks", answer, re.IGNORECASE):
        return 'unsupported_fulfillment_claim'
    if facts and not facts.get('shop', {}).get('created_at') and not re.search(
            r'mới\s+(?:mở|thành lập|hoạt động)|shop\s+mới', seller_context, re.I):
        for match in re.finditer(r'(?:shop|gian hàng)\s+(?:của bạn\s+)?mới\s+(?:mở|thành lập|hoạt động|nên)', answer, re.I):
            if not re.search(r'(?:nếu|khi|giả sử)(?:\s+đây là)?\s*$', answer[:match.start()], re.I):
                return 'unsupported_shop_age'
    pricing = facts.get('pricing_analysis') if facts else None
    if pricing:
        # Keep stated profit tied to Decimal calculations while allowing the
        # model to explain fee deductions and discuss hypothetical sale prices.
        allowed_profit = {item['profit_per_unit_vnd'] for key in ('at_selling_price', 'after_discount', 'target_price')
                          if (item := pricing.get(key)) and 'profit_per_unit_vnd' in item}
        text = normalize_text(answer.replace('*', '').replace('`', ''))
        for mention in money_mentions(text):
            prefix = text[max(0, mention.start - 70):mention.start]
            states_profit = re.search(r'(?:tiền lời|lợi nhuận|lời|lãi)(?:\s+(?:gộp|ròng|ước tính|còn|khoảng|là|mỗi máy|mỗi sản phẩm|mỗi đơn|mỗi cái))*[\s:≈~=>-]*$', prefix)
            if mention.explicit and states_profit and mention.value not in allowed_profit:
                return 'unsupported_pricing_amount'
    return None


def reply_correction(issue):
    return business_correction(issue) or {
        'empty_answer': 'Trả lời thẳng vào câu hỏi bằng câu tiếng Việt hoàn chỉnh.',
        'invalid_answer_envelope': 'Chỉ viết câu trả lời người bán cần đọc. Bỏ JSON và các khối mã chứa câu trả lời.',
        'raw_tool_payload': 'Chuyển dữ kiện công cụ thành câu tiếng Việt. Bỏ tên trường và JSON.',
        'internal_agent_message': 'Bỏ thông báo kỹ thuật và trả lời việc người bán vừa hỏi.',
        'unexecuted_write_claim': 'Chỉ nói việc đã được công cụ xác nhận. Viết bước còn lại dưới dạng đề xuất hoặc yêu cầu xác nhận.',
        'unsupported_fulfillment_claim': 'Dùng trạng thái hiện tại. Gợi ý hành động chỉ khi có dữ kiện rõ ràng.',
        'unsupported_shop_age': 'Bỏ nhận định về tuổi của shop nếu dữ liệu không có ngày thành lập.',
        'unsupported_pricing_amount': 'Dùng kết quả tiền lời từ pricing_analysis và nêu khoản phí còn thiếu nếu có.',
    }.get(issue, 'Trả lời gọn và chỉ dùng dữ kiện đã kiểm tra.')


def fallback_explanation(reason: str | None) -> str:
    if reason == 'invalid_response':
        return 'Mình chưa có câu trả lời đủ tin cậy cho lượt này. Bạn thử gửi lại nhé.'
    if reason == 'provider_timeout':
        return 'Lượt này xử lý lâu quá. Bạn thử gửi lại câu vừa rồi nhé.'
    if reason == 'provider_rate_limited':
        return 'Mình đang chạm giới hạn lượt xử lý. Bạn thử lại sau ít phút nhé.'
    if reason == 'tool_not_allowed':
        return 'Mình đã dừng yêu cầu trước khi thay đổi dữ liệu. Bạn cho mình biết phần cụ thể muốn chỉnh nhé.'
    return 'Mình chưa xử lý xong yêu cầu này. Bạn thử lại sau một chút nhé.'


async def handle_chat(
    session: Session,
    shop: UTEMallRepository,
    ai_provider: AIProvider,
    *,
    message: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    started_at = perf_counter()
    today = datetime.now(shop.timezone).date()
    mode = "ai"
    provider_name = getattr(ai_provider, "provider", "ollama")
    natural_responses = bool(getattr(ai_provider, "natural_responses", False))
    model_name: str | None = None
    fallback_reason: str | None = None
    prepared_answer = None
    runs, since = conversation_memory(session, shop, conversation_id)
    conversation_id = str(conversation_id or uuid4())
    known_read = quick_read(message, today=today) or contextual_read(message, runs, today=today)
    resolved = resolve_message(message, runs)
    # A complete shop-wide read must not inherit a SKU merely because its
    # wording contains "giá trị" after a previous product discussion.
    current_command = parse_fallback(message, today=today)
    if known_read or current_command.intent == 'shop_summary' or is_exact_fact_question(message, current_command):
        resolved = message
    history = history_messages(runs)
    order_read = None if known_read else order_answer(shop, message, runs)
    plan = planning_request(message, history) if not order_read else None
    manual_funnel = marketplace_for_plan(plan, message, history)
    contextual_plan = plan and not manual_funnel and has_product_reference(message)
    product_context = {}
    if contextual_plan:
        if extract_sku(normalize_text(message)):
            resolved = message
        else:
            product_context = conversation_product(session, shop, conversation_id, runs, since,
                published_only=refers_to_published_product(message))
            selected = product_context.get('selected_product')
            resolved = f"{message}\nSKU {selected['sku']}" if selected else message
            if not product_context:
                product_context = {'product_reference_missing': True}
    order_generation = order_read.pop('_generate', False) if order_read else False
    simple = simple_reply(session, message, runs)
    classifier_input = resolved
    if history:
        classifier_input = ("Lịch sử tham khảo:\n" + "\n".join(row["role"] + ": " + row["content"][:240] for row in history[-4:])
                            + "\n\nTIN NHẮN HIỆN TẠI:\n" + resolved)

    direct = known_read or parse_fallback(resolved, today=today)
    if contextual_plan or (plan and direct.intent in ('unknown', 'product_search')) or (manual_funnel and direct.intent == 'shop_summary'):
        direct = ParsedCommand(intent='sales_advice', sku=extract_sku(normalize_text(resolved)),
                               days=reporting_days(message))
    forgetting = is_forget_request(message)
    catalog_read = direct.intent == 'product_search' and catalog_lookup(message) is not None
    skip_classifier = bool(known_read or direct.sales_period_issue or order_read or plan and direct.intent == 'sales_advice') or bool(simple) or catalog_read or callable(getattr(ai_provider, "respond", None)) and (
        direct.intent == "sales_advice"
        or natural_responses and direct.intent in (
            "shop_summary", "inventory_query", "product_search"
        )
        or natural_responses and direct.intent == "unknown"
    )
    if skip_classifier:
        # Strong local matches need one grounded generation, not a second model
        # round-trip merely to rediscover their intent.
        command = direct
        model_name = getattr(ai_provider, "model", None)
    else:
        try:
            classification = await ai_provider.classify(classifier_input, today=today)
            command = enrich_ai_command(
                classification.command, message=resolved, today=today,
                prefer_model_intent=bool(getattr(ai_provider, "prefer_model_intent", False)),
            )
            provider_name = classification.provider
            model_name = classification.model
        except AIProviderError as error:
            command = direct
            mode = "fallback"
            provider_name = "deterministic_parser"
            fallback_reason = error.reason

    if simple:
        command = ParsedCommand(intent="unknown")
    if order_read:
        command = ParsedCommand(intent='unknown')
    direct_reply = bool(known_read or command.sales_period_issue or simple) or bool(order_read and not order_generation) or catalog_read or bool(getattr(ai_provider, 'prefer_direct_facts', False)) and (
        is_exact_fact_question(message, command)
    )
    if command.intent in ('sales_advice', 'unknown') and not command.days:
        days = reporting_days(message)
        if not days:
            for prior in reversed(runs):
                previous_facts = json.loads(prior.facts_json)
                days = previous_facts.get('period', {}).get('days') or previous_facts.get('days')
                if isinstance(days, int) and 1 <= days <= 30:
                    break
                days = None
        if days:
            command = command.model_copy(update={'days': days})
    preferences = read_memory(session, shop, 'shop')
    result = ({**order_read, 'proposal': None} if order_read else
              execute_command(session, shop, command, preferences=preferences))
    result['facts'].update(product_context)
    if preferences:
        result['facts']['seller_preferences'] = preferences
    if command.intent == 'sales_advice' and not order_read:
        # Evidence and reports are useful even without an available LLM.
        brief = attach_business_brief(shop, result['facts'], message=message, history=history,
                                      preferences=preferences)
        if brief:
            result['answer'] = planning_fallback(result['facts'])
    if forgetting:
        forget_memory(session, shop)
        command = ParsedCommand(intent='unknown')
        result = response('Mình đã xóa bộ nhớ cá nhân hóa và các chi phí đã ghi nhớ của shop. Lịch sử chat vẫn còn; từ giờ mình sẽ hỏi lại thông tin cần thiết.',
                          'forget_assistant_memory', {}, {'seller_preferences': {}})
    elif product_context.get('product_reference_missing'):
        result['answer'] = ASK_PRODUCT
        direct_reply = True
    elif result['facts'].get('business_advisory', {}).get('marketplace_funnel'):
        direct_reply = True
    elif not order_read and callable(getattr(ai_provider, 'respond', None)) and command.intent in ('sales_advice', 'unknown') and not simple and not is_casual_message(message):
        if command.intent == 'unknown':
            result['facts'].pop('supported_intents', None)
            result['facts'].update(shop_context(shop, command.days or 7))
        connection_question = len(message) < 140 and re.search(r'kết nối|ket noi|offline|mất mạng|mat mang', message, re.I)
        if not connection_question:
            attach_business_brief(shop, result['facts'], message=message, history=history,
                                  preferences=preferences)
            advisor = await enrich_advice(session, shop, ai_provider, message=message,
                resolved=resolved, conversation_id=conversation_id, runs=runs, history=history,
                facts=result['facts'])
            asks_for_math = bool(re.search(
                r'\b(?:gia von|hoa von|tinh (?:lai|loi|gia|bien loi)|(?:lai|loi) (?:bao nhieu|moi don)|'
                r'bien loi|bien loi nhuan)\b', read_text(message)))
            if plan and not asks_for_math:
                # A question about the price's effect on sales is a diagnosis.
                # A speculative model topic cannot replace it with a margin form.
                advisor['pricing_analysis'] = None
                advisor['pricing_context'] = None
            prepared_answer = advisor.pop('_prepared_answer', None)
            result['facts'].update({key: value for key, value in advisor.items() if value is not None})
            if contextual_plan and (product_context.get('selected_product') or direct.sku):
                result['facts'].pop('draft_context', None)
            result['facts'].update(product_context)
            prior_focus = result['facts'].get('business_advisory', {}).get('focus_product')
            brief = attach_business_brief(shop, result['facts'], message=message, history=history,
                                          preferences=advisor['seller_preferences'])
            if brief:
                if prior_focus != brief.get('focus_product'):
                    prepared_answer = None
                result['answer'] = planning_fallback(result['facts'])
                if command.intent == 'unknown':
                    command = command.model_copy(update={'intent': 'sales_advice'})
            if advisor['pricing_analysis']:
                command = ParsedCommand(intent='sales_advice')
                simple_price = simple_pricing_read(message)
                asks_profit = simple_price and bool(re.search(r'\b(?:loi|lai) bao nhieu\b', read_text(message)))
                result.update(answer=pricing_reply(advisor['pricing_analysis'], selling_profit_first=asks_profit), tool='calculate_pricing',
                              tool_arguments=advisor['pricing_analysis']['inputs'])
                if (getattr(ai_provider, 'prefer_direct_pricing', False)
                        and not advisor.get('context_extraction_error') and simple_price):
                    direct_reply = True
    can_generate = command.intent in ("sales_advice", "unknown") or (
        natural_responses and command.intent != "change_price"
    )
    report = build_chat_report(result['tool'], result['facts'])
    if direct_reply:
        if simple:
            result['answer'] = simple
        mode, provider_name, model_name, fallback_reason = 'ai', 'deterministic_parser', None, None
    elif can_generate and not forgetting and callable(getattr(ai_provider, 'respond', None)) and mode == 'ai':
        try:
            response_facts = {**result['facts'], **({'report_available': True} if report else {})}
            seller_context = '\n'.join([row['content'] for row in history if row['role'] == 'user'] + [message])
            for attempt in range(2):
                generated = (prepared_answer if attempt == 0 and prepared_answer is not None else
                             await ai_provider.respond(message, history=history, facts=response_facts))
                generated = conversational_text(generated)
                issue = reply_issue(generated, result['facts'], seller_context=seller_context)
                issue = issue or business_reply_issue(generated, result['facts'], message=message,
                                                      seller_context=seller_context)
                if not issue:
                    break
                business = result['facts'].get('business_advisory', {})
                if issue == 'incomplete_video_script' and business.get('shot_list') and not business.get('detailed_video'):
                    generated = result['answer']
                    break
                logger.warning('AI reply needs correction: reason=%s attempt=%s', issue, attempt + 1)
                if attempt:
                    raise AIProviderError('invalid_response', stage=issue)
                response_facts = {**response_facts, 'reply_correction': {
                    'reason': issue,
                    'requirements': reply_correction(issue),
                }}
            generated = re.sub(r"\s*\((?:pending_orders|packing_orders|shipping_orders)\)", "", generated)
            generated = re.sub(r"\bstock\s*[=:]?\s*(\d+)", r"còn \1", generated, flags=re.IGNORECASE)
            result["answer"] = complete_business_reply(generated, result['facts'])
            provider_name = getattr(ai_provider, 'response_provider', provider_name)
            model_name = getattr(ai_provider, 'response_model', model_name)
        except AIProviderError as error:
            logger.warning('Chat used grounded fallback: reason=%s stage=%s', error.reason, error.stage or 'unknown')
            mode, provider_name, fallback_reason = "fallback", "deterministic_parser", error.reason
    if mode == "fallback" and natural_responses and command.intent == "unknown" and not simple and not forgetting and not order_read:
        result["answer"] = fallback_explanation(fallback_reason)
    if forgetting:
        mode, provider_name, model_name, fallback_reason = 'ai', 'deterministic_parser', None, None
    result["suggestions"] = ([] if simple else ["Còn mã vận đơn?", "Còn đơn đó sao rồi?"]
                             if order_read and result['facts'].get('order_action') else suggestions_for(command, result))
    if order_read and result['facts'].get('order_comparison'):
        result['suggestions'] = [f"Theo dõi đơn #{item['id']}" for item in result['facts']['order_comparison'] if item.get('found')][:3]
    elapsed_ms = max(0, int(round((perf_counter() - started_at) * 1_000)))

    run = AgentRun(
        conversation_id=conversation_id,
        shop_slug=shop.seller_shop_slug or "local",
        proposal_id=result["proposal"]["id"] if result["proposal"] else None,
        product_draft_id=None,
        message=message,
        answer=result["answer"],
        intent=command.intent,
        mode=mode,
        status="completed" if mode == "ai" else "fallback",
        provider=provider_name,
        model=model_name,
        fallback_reason=fallback_reason,
        tool_name=result["tool"],
        tool_arguments_json=json.dumps(result.pop("tool_arguments"), ensure_ascii=False),
        facts_json=json.dumps(result["facts"], ensure_ascii=False, default=str),
        elapsed_ms=elapsed_ms,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    return {
        "run_id": run.id,
        "conversation_id": conversation_id,
        "intent": command.intent,
        "mode": mode,
        "provider": provider_name,
        "model": model_name,
        "fallback_reason": fallback_reason,
        "integration_mode": "local_store",
        **result,
        "report": report,
        "product_draft": None,
    }


def enrich_ai_command(
    command: ParsedCommand,
    *,
    message: str,
    today: date,
    prefer_model_intent: bool = False,
) -> ParsedCommand:
    """Verify exact identifiers and amounts from the original seller message."""

    fallback = parse_fallback(message, today=today)
    if fallback.intent != "unknown" and (not prefer_model_intent or fallback.intent == "change_price"):
        # Exact business instructions outrank a mistaken classifier prediction.
        command = fallback
    data = command.model_dump()
    normalized_message = normalize_text(message)
    exact_sku = extract_sku(normalized_message)

    # Never let model transcription change an explicit SKU or monetary value.
    # An invented model SKU must never choose a product for an action.
    data["sku"] = exact_sku
    # Price filters must be grounded in the seller's current wording too. A
    # classifier-supplied budget must not silently hide matching catalogue items.
    data['min_price_vnd'] = None
    data['max_price_vnd'] = None
    if command.intent == "change_price":
        exact_price = extract_price(normalized_message, sku=exact_sku or data["sku"])
        data["new_price_vnd"] = exact_price

    if fallback.intent == command.intent:
        if fallback.inventory_scope is not None:
            data["inventory_scope"] = fallback.inventory_scope

    if command.intent == "shop_summary":
        data.update(day=today, days=None, calendar_period=None, sales_metric=None, compare_yesterday=False,
                    sales_period_issue=None)
        data.update(sales_period(sales_text(read_text(message)), today=today))
        if fallback.intent == 'shop_summary':
            data['sales_metric'] = fallback.sales_metric
    if fallback.intent == "product_search":
        data["query"] = fallback.query
        data['min_price_vnd'] = fallback.min_price_vnd
        data['max_price_vnd'] = fallback.max_price_vnd
    if command.intent == "inventory_query" and data["inventory_scope"] == "low_stock":
        data["low_stock_threshold"] = (fallback.low_stock_threshold if fallback.low_stock_threshold is not None
                                       else extract_threshold(normalized_message))

    return ParsedCommand.model_validate(data)


def execute_command(
    session: Session,
    shop: UTEMallRepository,
    command: ParsedCommand,
    *,
    preferences: dict | None = None,
) -> dict[str, Any]:
    today = datetime.now(shop.timezone).date()

    def read(tool, arguments, facts):
        result = response('', tool, arguments, facts)
        result['answer'] = read_reply(result, today=today, preferences=preferences or {})
        return result

    if command.intent == "shop_summary":
        if command.sales_period_issue:
            explanation = {
                'invalid_date': 'Ngày bạn nhập không hợp lệ. Bạn gửi lại theo dạng ngày/tháng/năm nhé.',
                'multiple_periods': 'Bạn muốn xem kỳ nào trước? Mình có thể xem từng kỳ hoặc so hôm nay với cùng giờ hôm qua.',
                'range_limit': 'Bạn chọn từ 1 đến 30 ngày hoặc một tháng lịch để mình xem số liệu nhé.',
                'future_period': 'Kỳ này chưa diễn ra. Bạn chọn hôm nay hoặc một kỳ trước đó để xem số liệu nhé.',
            }
            return response(explanation[command.sales_period_issue], None, {}, {})
        anchor = command.day or today
        if anchor > today:
            return response('Ngày này chưa diễn ra. Bạn chọn hôm nay hoặc một ngày trước đó để xem số liệu nhé.',
                            None, {}, {'requested_date': anchor.isoformat()})
        days = ((anchor.weekday() + 1 if command.calendar_period == 'week' else anchor.day)
                if command.calendar_period else command.days or 1)
        # Text, charts and follow-ups use the same scoped snapshot.
        include_units = command.sales_metric == 'units'
        stats = management.dashboard(shop, days, selected_date=anchor, include_units=include_units,
                                     calendar_period=command.calendar_period,
                                     include_previous_units=include_units and command.compare_yesterday)
        facts = {key: stats[key] for key in (
            'days', 'from_date', 'to_date', 'order_value_vnd', 'order_count', 'average_order_vnd',
            'delivered_value_vnd', 'change_percent', 'previous_value_vnd', 'series',
            'order_status_counts', 'updated_at', 'timezone')}
        facts['includes_partial_today'] = anchor == today
        if command.calendar_period:
            facts['calendar_period'] = command.calendar_period
        if command.sales_metric:
            facts['sales_metric'] = command.sales_metric
        if command.compare_yesterday:
            facts.update(compare_yesterday=True, previous_order_count=stats['previous_order_count'],
                         previous_order_status_counts=stats['previous_order_status_counts'],
                         previous_delivered_value_vnd=stats['previous_delivered_value_vnd'])
        if command.day is None and command.days is None and not command.calendar_period and command.sales_metric in ORDER_STATUS_TEXT:
            facts['all_order_status_counts'] = stats['all_order_status_counts']
        if include_units:
            facts.update(units_sold=stats['units_sold'], orders_with_item_quantity=stats['orders_with_item_quantity'])
            if command.compare_yesterday:
                facts.update(previous_units_sold=stats['previous_units_sold'],
                             previous_orders_with_item_quantity=stats['previous_orders_with_item_quantity'])
        if days == 1 and not command.calendar_period:
            facts.update(date=anchor.isoformat(), status_counts=stats['order_status_counts'],
                         pending_count=stats['order_status_counts'].get('pending', 0),
                         cancelled_count=stats['order_status_counts'].get('cancelled', 0))
        arguments = {'days': days} if days > 1 or command.calendar_period else {'date': facts['date']}
        if command.calendar_period:
            arguments['calendar_period'] = command.calendar_period
        return read('get_shop_summary', arguments, facts)

    if command.intent == "inventory_query" and command.inventory_scope == "low_stock":
        threshold = (
            command.low_stock_threshold
            if command.low_stock_threshold is not None
            else 5
        )
        items = shop.low_stock(threshold, 50)
        compact_items = [{
            "sku": item["sku"],
            "product_name": item["product_name"],
            "variant_title": item["variant_title"],
            "stock": item["stock"],
            "price_vnd": item["price_vnd"],
        } for item in items]
        return read("get_low_stock", {"threshold": threshold, "limit": 50},
                    {"threshold": threshold, "count": len(compact_items), "items": compact_items})

    if command.intent == "inventory_query" and command.inventory_scope == "overview":
        return read("get_inventory_overview", {}, shop.inventory_overview(low_stock_threshold=5))

    if command.intent == "inventory_query":
        if not command.sku:
            return response(
                "Bạn muốn kiểm tra sản phẩm nào? Gửi mình mã SKU, hoặc tên để mình tìm trong shop.",
                None,
                {},
                {"missing_fields": ["sku"]},
            )
        try:
            item = shop.get_item_by_sku(command.sku)
        except ShopItemNotFoundError:
            return read("get_inventory", {"sku": command.sku}, {"sku": command.sku, "found": False})
        return read("get_inventory", {"sku": item["sku"]}, item)

    if command.intent == "change_price":
        missing_fields = []
        if not command.sku:
            missing_fields.append("sku")
        if command.new_price_vnd is None:
            missing_fields.append("new_price_vnd")
        if missing_fields:
            return response(
                ("Bạn muốn đặt giá mới bao nhiêu cho mã " + command.sku + "?" if command.sku else
                 "Bạn muốn đổi giá sản phẩm nào? Gửi mình SKU để chọn đúng hàng."),
                None,
                {},
                {"missing_fields": missing_fields, "sku": command.sku},
            )
        if command.new_price_vnd <= 0 or command.new_price_vnd > 1_000_000_000:
            return response(
                "Giá mới phải lớn hơn 0 và không vượt quá 1.000.000.000đ.",
                None,
                {},
                {"sku": command.sku, "new_price_vnd": command.new_price_vnd, "valid": False},
            )
        try:
            proposal = create_price_proposal(
                session,
                shop,
                sku=command.sku,
                new_price_vnd=command.new_price_vnd,
            )
        except ShopItemNotFoundError:
            return response(
                f"Không tìm thấy SKU {command.sku}; mình chưa tạo đề xuất nào.",
                "get_inventory",
                {"sku": command.sku},
                {"sku": command.sku, "found": False},
            )
        except PriceUnchangedError:
            return response(
                f"SKU {command.sku} đã có giá {format_vnd(command.new_price_vnd)}, nên không cần cập nhật.",
                "get_inventory",
                {"sku": command.sku},
                {"sku": command.sku, "current_price_vnd": command.new_price_vnd, "unchanged": True},
            )
        proposal_data = proposal_to_dict(proposal)
        facts = {
            "sku": proposal.sku,
            "product_name": proposal.product_name,
            "current_price_vnd": proposal.old_price_vnd,
            "new_price_vnd": proposal.new_price_vnd,
        }
        answer = (
            f"Mình tìm thấy SKU {proposal.sku} — {proposal.product_name}. "
            f"Mức giá bạn đề xuất là **{format_vnd(proposal.new_price_vnd)}**, "
            f"hiện tại **{format_vnd(proposal.old_price_vnd)}**. "
            "Mình chưa thay đổi giá. Bạn kiểm tra và xác nhận ở thẻ bên dưới nhé."
        )
        return response(
            answer,
            "create_price_proposal",
            {"sku": proposal.sku, "new_price_vnd": proposal.new_price_vnd},
            facts,
            proposal_data,
        )

    if command.intent == "product_search":
        query = (command.query or "").strip()
        if not query:
            return response("Bạn đang tìm sản phẩm nào? Cho mình tên hoặc loại hàng nhé.", None, {}, {"missing_fields": ["query"]})
        filters = {'min_price_vnd': command.min_price_vnd, 'max_price_vnd': command.max_price_vnd}
        found = management.products(shop, query, limit=8, **filters)
        found.update(query=query, **filters)
        return read("search_products", {"query": query, "limit": 8, **filters}, found)

    if command.intent == "sales_advice":
        facts = shop_context(shop, command.days or 7)
        facts.update(period_days=facts['period']['days'],
                     order_value_vnd=facts['period']['order_value_vnd'],
                     order_count=facts['period']['order_count'])
        if command.sku:
            try: facts["selected_product"] = shop.get_item_by_sku(command.sku)
            except ShopItemNotFoundError: facts["selected_product"] = {"sku": command.sku, "found": False}
        tasks = facts['tasks']
        priorities = []
        if pending := tasks['pending_orders']:
            priorities.append(f"Xác nhận **{pending} đơn** đang chờ.")
        if low := tasks['low_stock_products']:
            priorities.append(f"Rà lại **{low} sản phẩm** còn không quá 5 trước khi chạy ưu đãi.")
        if reviews := tasks['unanswered_reviews']:
            priorities.append(f"Trả lời **{reviews} đánh giá** đang chờ phản hồi.")
        answer = ('Những việc cần ưu tiên lúc này:\n\n' + '\n'.join(f'• {item}' for item in priorities)
                  if priorities else 'Hiện chưa có đơn chờ xác nhận, cảnh báo tồn thấp hay đánh giá cần phản hồi. '
                  'Nếu bạn đang muốn tăng đơn, cho mình tên món bạn muốn tập trung để cùng xem bước tiếp theo.')
        return response(answer, "get_shop_insights", {"days": command.days or 7}, facts)

    return response(
        "Mình chưa rõ phần bạn muốn mình xử lý. Bạn nói thêm một chút nhé.",
        None,
        {},
        {"supported_intents": ["shop_summary", "inventory_query", "change_price", "product_search", "sales_advice"]},
    )


def simple_reply(session, message, runs):
    text = read_text(message)
    confirmation = re.sub(r'[,;]\s*', ' ', text)
    if re.fullmatch(r'(?:(?:minh|toi) )?(?:xac nhan(?: doi gia)?|dong y(?: xac nhan| doi gia)?|confirm|ok|oke|okie)', confirmation):
        last = next((run for run in reversed(runs) if run.tool_name or not social_reply(run.message)), None)
        if last and last.proposal_id:
            proposal = session.get(ActionProposal, last.proposal_id)
            if proposal is not None and proposal.status == 'pending':
                return (f'Bạn bấm **Xác nhận đổi giá** trên thẻ đề xuất để lưu mức '
                        f'**{format_vnd(proposal.new_price_vnd)}** cho mã **{proposal.sku}** nhé.')
    return social_reply(message, ongoing=bool(runs))


def is_exact_fact_question(message, command):
    return (quick_read(message, today=command.day or date.today()) is not None
            or command.intent == 'product_search' and catalog_lookup(message) is not None)


def is_casual_message(message):
    """Recognize obvious conversation without treating day words as shop reports."""
    text = normalize_text(message)
    return any(phrase in text for phrase in (
        "nói chuyện", "noi chuyen", "tâm sự", "tam su", "hơi mệt", "hoi met",
        "mệt quá", "met qua", "buồn quá", "buon qua", "chán quá", "chan qua",
        "bạn khỏe không", "ban khoe khong", "bạn là ai", "ban la ai",
    ))


def suggestions_for(command, result):
    pricing = result['facts'].get('pricing_analysis')
    if pricing:
        if pricing['status'] == 'missing_cost':
            return ['Mình cần cung cấp những chi phí nào để tính giá?', 'Biên lợi nhuận khác lời trên giá vốn thế nào?']
        return ['Nếu giảm giá 10% thì lời còn bao nhiêu?', 'Gợi ý cách tăng lợi nhuận mà không tăng giá']
    if command.intent == 'sales_advice':
        brief = result['facts'].get('business_advisory')
        if brief:
            focus = brief.get('focus_product')
            sku = focus.get('sku') if focus else None
            return ([f"Viết kịch bản TikTok ngắn cho SKU {sku}" if sku else "Chọn sản phẩm nào để quay video trước?",
                     "Cụ thể hơn", "Lập kế hoạch 7 ngày với một người thực hiện"]
                    if brief['mode'] != 'video_script' else
                    ["Viết thêm 2 câu mở đầu khác để thử", "Hướng dẫn đo hiệu quả từng video", "Lập kế hoạch nội dung 7 ngày"])
        return ['Lập kế hoạch hành động 7 ngày cho shop', 'Đề xuất nào phù hợp với ngân sách nhỏ?', 'Giải thích rõ hơn phần quan trọng nhất']
    sku = result["facts"].get("sku")
    if command.intent == "inventory_query" and sku and result["facts"].get("found") is not False:
        return [f"Viết mô tả bán hàng cho SKU {sku}", "Shop có sản phẩm nào sắp hết?"]
    if command.intent == "product_search" and result["facts"].get("items"):
        return [f"SKU {result['facts']['items'][0]['sku']} còn bao nhiêu?", "Hôm nay shop bán hàng thế nào?"]
    if command.intent == "change_price":
        return ["Kiểm tra lại giá và tồn kho mã này", "Tình hình shop hôm nay"]
    return ["Shop có sản phẩm nào sắp hết?", "Tư vấn việc cần ưu tiên hôm nay", "Tìm bàn phím"]


def response(
    answer: str,
    tool: str | None,
    tool_arguments: dict[str, Any],
    facts: dict[str, Any],
    proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "tool": tool,
        "tool_arguments": tool_arguments,
        "facts": facts,
        "proposal": proposal,
    }


def format_vnd(value: int) -> str:
    return format_number(value) + "đ"


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")
