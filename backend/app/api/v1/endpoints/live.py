"""Authenticated audio relay with shop reads and reviewable action drafts."""
import asyncio
import base64
import binascii
import json
import logging
import re
from contextlib import AsyncExitStack
from time import monotonic
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator, ValidationError
from starlette.concurrency import run_in_threadpool
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from app.ai.key_pool import GeminiKeyPool, gemini_credentials, rejected_gemini_key, retry_delay
from app.ai.money import plain
from app.core.config import LOCAL_WEB_ORIGIN
from app.integrations.ute_mall import ShopDatabaseError, ShopItemNotFoundError
from app.services.auth import verify_seller
from app.services.business_advisor import planning_request
from app.services.chat_dispatch import listing_request
from app.services.conversation_state import ensure_conversation_open
from app.services.conversations import has_product_reference
from app.services.live_actions import LiveActions
from app.services.live_history import LiveHistory
from app.services.live_language import GEMINI_VOICES, LivePreferences, REPEAT_QUESTION, transcription_config, unclear_vietnamese
from app.services.live_shop import inspect_shop
from app.services.product_archive_chat import is_product_archive_request
from app.services.product_drafts import ProductDraftNotFoundError

router = APIRouter(tags=['live voice'])
logger = logging.getLogger(__name__)
GEMINI_LIVE_URL = (
    'wss://generativelanguage.googleapis.com/ws/'
    'google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'
)
SESSION_SECONDS = 180
MAX_PACKET = 48_000
MAX_IMAGE_BASE64 = 700_000
MAX_SESSIONS = 3
LIVE_CONNECT_BUDGET = 18
MAX_TOOLS_PER_TURN = 10
INSTRUCTION = '''Bạn là SellerPilot, trợ lý dành cho người bán do ShipCODE phát triển.
Ưu tiên câu ngắn, nói liền mạch với nhịp trò chuyện hơi nhanh, lấy hơi theo ý, giữ rõ phụ âm cuối và số. Chuyển sắc thái theo ngữ cảnh. Có thể đổi nhịp theo yêu cầu.
Vào thẳng việc người bán vừa hỏi. Chào hỏi, cảm ơn, đồng ý hoặc tạm biệt thì đáp bằng một câu phù hợp. Chỉ giới thiệu lại SellerPilot khi được hỏi. Nếu đã đủ dữ kiện để trả lời, chốt ý rồi nhường lượt nói, tránh hỏi «bạn cần gì nữa không» ở cuối.
Đọc tiền, ngày và chữ viết tắt theo ngôn ngữ phiên. Không đọc markdown, JSON, SKU dài, URL, bảng hay toàn bộ một báo cáo. Chỉ nói điều quan trọng nhất rồi chừa khoảng cho người bán trao đổi tiếp.
Khi âm thanh nghe không rõ, bị lẫn tiếng, hoặc câu nhận diện rời rạc, chỉ hỏi người bán nói lại chỗ đó. Không đoán tên sản phẩm hay yêu cầu của người bán từ âm không rõ hoặc từ ảnh có sẵn.
Khi hỏi số liệu, tồn, sản phẩm, trạng thái đơn, kế hoạch bán hàng, quảng cáo hoặc TikTok, gọi inspect_shop trước. Truyền câu hỏi độc lập bằng tiếng Việt, giữ nguyên kỳ, mã đơn, SKU, mục tiêu và điều kiện người bán đã nói. Nếu câu tiếp nối, điền tham chiếu đã rõ từ đoạn nói trước. Khi công cụ trả detailed_plan=true, hướng người bán xem nội dung trong cuộc trò chuyện và đọc điểm chính từ answer.
Với câu «shop bán được bao nhiêu», đọc số đơn và tổng giá trị đơn đã kiểm tra trong kỳ. Chỉ hỏi lại nếu không xác định được phạm vi từ lời người bán và lịch sử.
Khi người bán hỏi cách bán «sản phẩm này», «món đó» hay «món vừa đăng», mỗi lần đều gọi inspect_shop và giữ nguyên cụm tham chiếu. Mở đầu câu trả lời bằng tên sản phẩm lấy từ business_advisory.focus_product để bạn biết đang nói về món nào. Nếu thiếu focus thì hỏi tên hoặc SKU. Lịch sử chỉ dùng để tham khảo. Chỉ xác nhận thao tác từ lời nói mới trong phiên.
Chỉ dùng dữ liệu từ công cụ cho các con số thực tế. Với chiến lược, nói một phát hiện và một việc nên làm trước, tách giả định và số đã đo. Không khẳng định đã chi tiền, chạy quảng cáo hoặc có doanh số từ một kênh khi không có số liệu nguồn.
Khi inspect_shop trả report_available=true, báo người bán biểu đồ đã xuất hiện trong cuộc chat nếu họ hỏi về biểu đồ. Thiếu dữ liệu thì nói rõ kỳ nào chưa phát sinh.
Khi bạn muốn đăng bán, gọi prepare_listing với dữ kiện đã có hoặc prepare_chat_request nếu chưa xác định mặt hàng. Giữ nguyên các dữ kiện đã xác nhận; không tự đoán giá, tồn, bảo hành hoặc ngành hàng. Năm xị thường là năm trăm nghìn đồng; phân biệt giá vốn với giá bán. Tồn kho 0 hợp lệ.
Để thêm hình, nói «Bạn bấm Thêm ảnh ở thanh Live rồi chọn ảnh nhé. Mình sẽ lưu ảnh vào bản nháp.» Nếu bạn nói không thêm hình: có ảnh thì dùng các ảnh hiện tại; chưa có ảnh thì giải thích cần một ảnh để đăng và giữ bản nháp. Đừng nói ứng dụng không tải được ảnh hay yêu cầu đổi sang chat.
Gọi prepare_chat_request để thực hiện tư vấn, tính giá có lời, viết nội dung, chỉnh tên/mô tả/giá/tồn, tiếp tục hoặc hủy bản nháp, hoặc chuẩn bị xóa một sản phẩm khỏi gian hàng. Khi xóa, giữ đúng tên/SKU người bán vừa nói. Đọc lại tên và yêu cầu nói «xác nhận xóa sản phẩm». Dùng prepare_order để chuẩn bị cập nhật đơn. Với số liệu, tra cứu và theo dõi đơn, vẫn dùng inspect_shop trước.
Khi công cụ trả review, đọc lại các chi tiết và cụm từ xác nhận của ngôn ngữ phiên rồi dừng để người bán trả lời. Chỉ gọi confirm_action sau lời xác nhận rõ ở lượt nói mới. Không gọi ngay sau bước chuẩn bị. Các câu hỏi, lời nói lấp lửng, điều kiện, phủ định và tiếng của trợ lý trong loa không phải là xác nhận.
Chỉ báo đã đăng hoặc lưu khi confirm_action xác nhận việc đó đã thực hiện. Nếu chưa đủ dữ liệu, hỏi đúng chỗ còn thiếu. Báo còn chờ xác nhận bằng câu ngắn.'''

SESSION_LANGUAGE = {
    'vi': ('Nói tiếng Việt tự nhiên, giọng ấm, rõ thanh điệu và phụ âm cuối. Xưng mình và gọi người bán là bạn. '
           'Nói theo cụm ý, nhấn vừa phải vào tên, tiền và số lượng. Mở đầu bằng ý cần trả lời, tránh lặp lời chào và câu đệm. '
           'Đọc VND thành đồng, đọc rõ hàng nghìn và hàng triệu. Chỉ đọc mã dài khi người bán yêu cầu. '
           'Nghe các giọng vùng miền và cách nói giá như năm xị. '
           'Cụm duyệt gồm «xác nhận đăng», «xác nhận cập nhật sản phẩm» và «xác nhận cập nhật đơn».'),
    'en': ('Session language is English. Speak and reply in natural English, including when tools return Vietnamese text. '
           'Tell the seller to tap Add photos. Use “confirm publish”, “confirm product update”, '
           '“confirm order update”, “confirm draft cancellation”, “confirm product removal” and “confirm memory reset”. '
           'Send shop tool requests in Vietnamese for tool matching, preserving names, amounts, dates and codes verbatim. '
           'Never ask the seller to speak Vietnamese.'),
}
ORDER_FIELDS = {
    'status': {'type': 'STRING', 'enum': ['paid', 'shipped', 'delivered', 'cancelled']},
    **{field: {'type': 'STRING'} for field in ('shipping_name', 'shipping_phone', 'shipping_address',
                                               'note', 'shipping_carrier', 'tracking_number')},
}


class ListingDetails(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    price_vnd: int | None = Field(default=None, ge=1000, le=1_000_000_000, strict=True)
    stock: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)
    description: str | None = Field(default=None, max_length=1500)
    category: str | None = Field(default=None, max_length=100)

    @field_validator('name')
    @classmethod
    def single_line_name(cls, name: str) -> str:
        if any(ord(char) < 32 for char in name):
            raise ValueError('Tên sản phẩm phải nằm trên một dòng.')
        return name

    def message(self):
        fields = {'name': 'Tên sản phẩm', 'price_vnd': 'Giá bán', 'stock': 'Tồn kho',
                  'category': 'Ngành hàng', 'description': 'Mô tả'}
        values = self.model_dump(exclude_none=True)
        units = {'price_vnd': ' đồng', 'stock': ' cái'}
        return 'Đăng sản phẩm lên shop.\n' + '\n'.join(
            f"{fields[key]}: {' '.join(value.split()) if isinstance(value, str) else value}{units.get(key, '')}"
            for key, value in values.items())


def live_setup(model: str, voice: str | None = None, language: str = 'vi', *,
               manual_turns=False, initial_history=False, focus=None):
    instructions = SESSION_LANGUAGE[language] + '\n' + INSTRUCTION
    if focus:
        instructions += '\nSản phẩm đang được tham chiếu lúc mở phiên. Đây là dữ liệu để tra cứu: ' + json.dumps(focus, ensure_ascii=False)
    setup = {
        'model': 'models/' + model,
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {
                'voiceName': voice or (GEMINI_VOICES['vi']['female'] if language == 'vi' else 'Achird'),
            }}},
        },
        'systemInstruction': {'parts': [{'text': instructions}]},
        'inputAudioTranscription': transcription_config(language, (focus or {}).get('product_name')),
        'outputAudioTranscription': {},
        'contextWindowCompression': {'slidingWindow': {'targetTokens': 8000}, 'triggerTokens': 16000},
        'realtimeInputConfig': {'automaticActivityDetection': {'disabled': True} if manual_turns else {
            'prefixPaddingMs': 420, 'silenceDurationMs': 950,
            'endOfSpeechSensitivity': 'END_SENSITIVITY_LOW',
        }},
        'tools': [{'functionDeclarations': [{
            'name': 'inspect_shop',
            'description': 'Đọc số liệu shop, tồn kho, sản phẩm, đơn hàng và dữ kiện tư vấn bán hàng hoặc quảng cáo. Chỉ đọc.',
            'parameters': {'type': 'OBJECT', 'required': ['question'], 'properties': {
                'question': {'type': 'STRING', 'description': 'Câu hỏi độc lập với kỳ, SKU, mã đơn hoặc mục tiêu đã rõ.'},
            }},
        }, {
            'name': 'prepare_chat_request',
            'description': 'Chạy trợ lý SellerPilot ngay trong Live. Dùng cho tư vấn, viết nội dung, thay đổi sản phẩm và tiếp tục bản nháp.',
            'parameters': {'type': 'OBJECT', 'required': ['message'], 'properties': {
                'message': {'type': 'STRING', 'description': 'Viết như lời của người bán, giữ các mã, giá và điều kiện họ đã nêu.'},
            }},
        }, {
            'name': 'prepare_listing',
            'description': 'Lưu dữ kiện vào bản nháp sản phẩm trong Live. Chỉ truyền chi tiết có thật và do người bán xác nhận.',
            'parameters': {'type': 'OBJECT', 'required': ['name'], 'properties': {
                'name': {'type': 'STRING', 'description': 'Tên hoặc mặt hàng được người bán xác nhận.'},
                'price_vnd': {'type': 'INTEGER', 'description': 'Giá bán đã xác nhận bằng VND. Bỏ qua khi chưa rõ.'},
                'stock': {'type': 'INTEGER', 'description': 'Tồn kho đã xác nhận. Bỏ qua khi chưa rõ.'},
                'description': {'type': 'STRING', 'description': 'Mô tả do người bán cung cấp, nếu có.'},
                'category': {'type': 'STRING', 'description': 'Ngành hàng do người bán nêu, nếu có.'},
            }},
        }, {
            'name': 'prepare_order',
            'description': 'Chuẩn bị thay đổi cho đúng mã đơn, giữ nguyên các trường người bán không yêu cầu sửa.',
            'parameters': {'type': 'OBJECT', 'required': ['order_id', 'changes'], 'properties': {
                'order_id': {'type': 'INTEGER'},
                'changes': {'type': 'OBJECT', 'properties': ORDER_FIELDS},
            }},
        }, {
            'name': 'confirm_action',
            'description': 'Thực hiện hoặc từ chối đúng hành động vừa đọc lại sau lời xác nhận rõ ràng ở lượt nói tiếp theo.',
            'parameters': {'type': 'OBJECT', 'properties': {}},
        }]}],
    }
    if initial_history:
        setup['historyConfig'] = {'initialHistoryInClientContent': True}
    return {'setup': setup}


class LiveError(RuntimeError):
    pass


class LiveKeyError(LiveError):
    def __init__(self, reason, retry_after=60):
        self.reason = reason
        self.retry_after = retry_after
        super().__init__('Gemini Live đang giới hạn lượt sử dụng. Bạn thử lại sau nhé.'
                         if reason == 'rate_limited' else 'Key Gemini chưa có quyền mở Live. Kiểm tra model và project trong AI Studio.')


def live_key_failure(error):
    if isinstance(error, LiveKeyError):
        return error
    if isinstance(error, InvalidStatus):
        response = error.response
        if response.status_code == 429:
            return LiveKeyError('rate_limited', retry_delay(response.headers.get('Retry-After')))
        if response.status_code in (401, 403):
            return LiveKeyError('rejected')
    if isinstance(error, ConnectionClosed) and error.rcvd:
        reason = error.rcvd.reason.casefold()
        if any(term in reason for term in ('resource_exhausted', 'quota exceeded', 'rate limit', 'too many requests')):
            return LiveKeyError('rate_limited')
        if any(term in reason for term in ('api key not valid', 'api_key_invalid', 'api key expired',
                                           'permission denied', 'permission_denied', 'unauthenticated')):
            return LiveKeyError('rejected')
    return None


def check_live_provider_error(packet):
    error = packet.get('error')
    if not isinstance(error, dict):
        return
    status = error.get('status')
    code = error.get('code')
    if code == 429 or status == 'RESOURCE_EXHAUSTED':
        raise LiveKeyError('rate_limited')
    if code in (401, 403) or status in ('UNAUTHENTICATED', 'PERMISSION_DENIED') or rejected_gemini_key(error):
        raise LiveKeyError('rejected')
    raise LiveError('Gemini Live gặp lỗi khi xử lý. Bạn thử mở lại phiên nhé.')


class ShopQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=1200)


class ChatReview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    message: str = Field(min_length=3, max_length=3000)


class OrderReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    order_id: int = Field(ge=1, strict=True)
    changes: dict[str, str] = Field(min_length=1, max_length=len(ORDER_FIELDS))


class GalleryReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: str
    draft_id: int = Field(ge=1, strict=True)
    run_id: int = Field(ge=1, strict=True)


def read_shop(socket, token, question, spoken, conversation_id):
    app = socket.app.state
    with app.session_factory() as session:
        verify_seller(app.shop_repository, session, token)
        ensure_conversation_open(session, app.shop_repository.seller_shop_slug or 'local', conversation_id)
        return inspect_shop(session, app.shop_repository, question, spoken, conversation_id=conversation_id)


async def shop_tool(socket, token, name, args, history, actions, traffic):
    try:
        if history.unclear:
            return {'accepted': False, 'message': REPEAT_QUESTION}
        contextual = (name in ('inspect_shop', 'prepare_listing', 'prepare_chat_request')
                      and has_product_reference(history.user) and planning_request(history.user))
        if contextual:
            if history.contextual_advice is not None:
                return history.contextual_advice
            name, args = 'inspect_shop', {'question': history.user[:1200]}
        elif name == 'prepare_listing' and planning_request(history.user) and not listing_request(history.user):
            name, args = 'inspect_shop', {'question': history.user[:1200]}
        if name == 'prepare_listing':
            return await actions.ask_chat(ListingDetails.model_validate(args).message())
        if name == 'prepare_chat_request':
            review = ChatReview.model_validate(args)
            if is_product_archive_request(review.message) or is_product_archive_request(history.user):
                if not (voice_finished(traffic) or traffic.get('awaiting_turn') and history.user):
                    return {'accepted': False, 'message': 'Chờ hệ thống đối chiếu lời nói. Chưa đọc câu trả lời.'}
                if is_product_archive_request(history.user) or await run_in_threadpool(actions.follows_archive_request, history.user):
                    return await actions.ask_chat(history.user)
                return {'accepted': False, 'message': 'Mình chỉ chuẩn bị xóa khi người bán yêu cầu rõ ràng.'}
            return await actions.ask_chat(review.message)
        if name == 'prepare_order':
            order = OrderReview.model_validate(args)
            if order.changes.keys() - ORDER_FIELDS.keys():
                return {'accepted': False, 'message': 'Thông tin đơn hàng chưa hợp lệ.'}
            return await actions.prepare_order(order.order_id, order.changes)
        if name == 'confirm_action' and args == {}:
            if history.decision:
                return {'accepted': True, 'answer': history.decision[2]}
            return await actions.decide(history.user, finished=voice_finished(traffic))
        if name == 'inspect_shop':
            question = ShopQuestion.model_validate(args).question
            result = await run_in_threadpool(read_shop, socket, token, question, history.user, history.conversation_id)
            if result is None:
                return {'accepted': False, 'message': 'Hãy làm rõ kỳ, sản phẩm hoặc mã đơn. Với yêu cầu khác dùng prepare_chat_request.'}
            order_id = result.get('order_id')
            summary = result.get('spoken_summary') if history.language == 'vi' else None
            display = {'id': str(uuid4()), 'turn_id': history.turn_id, 'language': history.language, 'question': question,
                       'answer': result['answer'], 'report': result.get('report'), 'order_id': order_id}
            if summary:
                display['spoken_summary'] = summary
            if result.get('sales_context'):
                display['sales_context'] = result['sales_context']
            history.result(display, result['facts'])
            await socket.send_json({'type': 'shop_result', **display})
            spoken_answer = ('Đã tìm thông tin đơn. Đọc trạng thái và tổng tiền nếu có.' if 'order_id' in result
                             else summary or result['answer'][:2000])
            advice = {'accepted': True, 'answer': spoken_answer,
                      'facts': result['facts'], 'order_id': order_id, 'report_available': display['report'] is not None}
            if summary:
                advice['detailed_plan'] = True
            if contextual:
                history.contextual_advice = advice
            return advice
    except ValidationError:
        pass
    except HTTPException as error:
        detail = error.detail.get('message') if isinstance(error.detail, dict) else error.detail
        return {'accepted': False, 'message': detail or 'Mình chưa xử lý được yêu cầu.'}
    except (ValueError, ShopItemNotFoundError):
        return {'accepted': False, 'message': 'Mình chưa đọc được bản nháp hoặc đơn hàng với thông tin này.'}
    except ShopDatabaseError:
        return {'accepted': False, 'message': 'Dữ liệu shop tạm thời chưa đọc được. Hãy báo lại cho người bán.'}
    return {'accepted': False, 'message': 'Công cụ hoặc dữ kiện không hợp lệ.'}


def voice_finished(traffic):
    next_turn = traffic['turn_signals'] > traffic.get('review_turn', 0)
    if traffic.get('manual_turns'):
        return (next_turn and traffic.get('awaiting_turn')
                and (traffic.get('speech_finished') or traffic.get('settled_input')))
    return traffic.get('speech_finished') or next_turn


def read_json(message, limit):
    if not isinstance(message, (str, bytes)) or len(message) > limit:
        raise LiveError('Gói dữ liệu Live không hợp lệ.')
    try:
        data = json.loads(message)
    except (ValueError, UnicodeError) as error:
        raise LiveError('Gói dữ liệu Live không hợp lệ.') from error
    if not isinstance(data, dict):
        raise LiveError('Gói dữ liệu Live không hợp lệ.')
    return data


def authenticate(socket, token, conversation_id):
    with socket.app.state.session_factory() as session:
        shop = socket.app.state.shop_repository
        _, seller = verify_seller(shop, session, token)
        ensure_conversation_open(session, shop.seller_shop_slug or 'local', str(conversation_id))
        return seller['user']['id']


def allowed_origin(socket):
    origin = socket.headers.get('origin')
    settings = socket.app.state.settings
    scheme = 'https' if socket.url.scheme == 'wss' else 'http'
    # Native WebSocket clients can supply the API origin as their own origin.
    return (origin is None or origin == f'{scheme}://{socket.url.netloc}'
            or origin in settings.cors_origins
            or settings.demo_mode and bool(re.fullmatch(LOCAL_WEB_ORIGIN, origin)))


async def forward_microphone(socket, upstream, traffic, actions, *, manual_turns, started):
    audio_seconds = 0.0
    active_speech = False
    last_image_at = float('-inf')
    images = 0
    async for message in socket.iter_text():
        data = read_json(message, MAX_IMAGE_BASE64 + 100)
        if data.get('type') == 'images_added':
            try:
                receipt = GalleryReceipt.model_validate(data)
                summary, jpeg = await actions.accept_gallery(receipt.draft_id, receipt.run_id)
                if jpeg:
                    await upstream.send(json.dumps({'realtimeInput': {
                        'video': {'mimeType': 'image/jpeg', 'data': base64.b64encode(jpeg).decode('ascii')},
                    }}))
                await upstream.send(json.dumps({'realtimeInput': {'text':
                    'Thông báo của ứng dụng: người bán vừa chọn ảnh. Hãy nói lại bằng giọng nói. ' + summary}}))
            except (ValidationError, ValueError, ProductDraftNotFoundError):
                await socket.send_json({'type': 'image_rejected', 'message': 'Mình chưa mở được bản nháp chứa ảnh vừa thêm.'})
            continue
        if data.get('type') == 'image':
            now = monotonic()
            image = data.get('data')
            try:
                jpeg = base64.b64decode(image, validate=True) if isinstance(image, str) and len(image) <= MAX_IMAGE_BASE64 else b''
            except (ValueError, binascii.Error):
                jpeg = b''
            if not jpeg.startswith(b'\xff\xd8\xff') or not jpeg.endswith(b'\xff\xd9'):
                await socket.send_json({'type': 'image_rejected', 'message': 'Ảnh chưa gửi được. Bạn thử chọn ảnh khác nhé.'})
            elif images == 6 or now - last_image_at < 1:
                await socket.send_json({'type': 'image_rejected', 'message': 'Live nhận tối đa 6 ảnh mỗi phiên, cách nhau ít nhất 1 giây.'})
            else:
                await upstream.send(json.dumps({'realtimeInput': {'video': {'mimeType': 'image/jpeg', 'data': image}}}))
                images += 1
                last_image_at = now
                await socket.send_json({'type': 'image_sent'})
            continue
        if len(message) > MAX_PACKET:
            raise LiveError('Gói âm thanh micro quá lớn hoặc không hợp lệ.')
        kind = data.get('type')
        if manual_turns and kind == 'speech_start':
            if not active_speech and not traffic.get('awaiting_turn'):
                active_speech = True
                traffic['speech_finished'] = False
                traffic['input_final'].clear()
                await upstream.send('{"realtimeInput":{"activityStart":{}}}')
            continue
        if kind in ('finish', 'mute', 'turn'):
            if kind == 'turn' and (not manual_turns or active_speech):
                traffic['turn_signals'] += 1
                traffic['input_ended_at'] = monotonic()
            if not manual_turns or active_speech:
                active_speech = False
                traffic['awaiting_turn'] = manual_turns
                signal = '{"realtimeInput":{"activityEnd":{}}}' if manual_turns else '{"realtimeInput":{"audioStreamEnd":true}}'
                await upstream.send(signal)
            if kind == 'finish':
                if manual_turns and traffic.get('awaiting_turn') and not traffic.get('speech_finished'):
                    # Give a pending utterance a bounded drain. An idle session closes immediately.
                    try:
                        await asyncio.wait_for(traffic['input_final'].wait(), timeout=1.65)
                    except TimeoutError:
                        pass
                return True
            continue
        rate = data.get('rate')
        if data.get('type') != 'audio' or type(rate) is not int or not 8000 <= rate <= 48000:
            raise LiveError('Định dạng micro không được hỗ trợ.')
        try:
            pcm = base64.b64decode(data.get('data', ''), validate=True)
        except (ValueError, TypeError, binascii.Error) as error:
            raise LiveError('Âm thanh micro không hợp lệ.') from error
        if not pcm or len(pcm) % 2 or len(pcm) > rate:
            raise LiveError('Gói âm thanh micro quá lớn hoặc không hợp lệ.')
        audio_seconds += len(pcm) / (rate * 2)
        if audio_seconds > monotonic() - started + 2:
            raise LiveError('Âm thanh gửi quá nhanh. Bạn mở lại phiên Live nhé.')
        if manual_turns and not active_speech:
            continue
        await upstream.send(json.dumps({'realtimeInput': {'audio': {
            'mimeType': f'audio/pcm;rate={rate}', 'data': data['data'],
        }}}))
        traffic['audio_frames'] += 1
        if traffic['audio_frames'] == 1:
            await socket.send_json({'type': 'audio_received'})


async def save_live_turn(socket, history, *, notify):
    pending = history.take()
    if pending is None:
        return
    saved = await run_in_threadpool(history.save, pending)
    if notify:
        await socket.send_json({'type': 'turn_saved', 'turn': jsonable_encoder(saved)})


async def check_transcription(socket, history, traffic):
    if (history.language == 'vi' and not history.unclear and voice_finished(traffic)
            and unclear_vietnamese(history.user)):
        history.unclear = True
        await socket.send_json({'type': 'interrupted'})
        await socket.send_json({'type': 'transcript', 'role': 'user', 'text': 'Lời nói chưa rõ',
                                'snapshot': True, 'unclear': True, 'turn_id': history.turn_id})


async def forward_response(socket, upstream, token, history, traffic, actions):
    tool_count = 0
    first_audio_at = None
    tool_seconds = 0.0
    messages = aiter(upstream)
    # ClientConnection.recv is cancellation-safe. Timing out its async iterator
    # would instead close the generator and lose the following turn.
    read_next = upstream.recv if isinstance(upstream, ClientConnection) else lambda: anext(messages)
    loop = asyncio.get_running_loop()
    complete_by = None
    generation_complete = False
    waiting_for_tool_reply = False
    while True:
        try:
            if complete_by is None:
                message = await read_next()
            else:
                async with asyncio.timeout_at(complete_by):
                    message = await read_next()
            data = read_json(message, 1_000_000)
        except StopAsyncIteration:
            raise LiveError('Gemini đã ngắt kết nối. Bạn có thể mở phiên Live mới.') from None
        except TimeoutError:
            if complete_by is None:
                raise
            data = {}
        check_live_provider_error(data)
        if 'goAway' in data:
            raise LiveError('Gemini đã kết thúc phiên. Bạn có thể mở phiên Live mới.')
        content = data.get('serverContent') or {}
        if content.get('interrupted'):
            await socket.send_json({'type': 'interrupted'})
            first_audio_at = None
            tool_seconds = 0.0
        for key, role in (('inputTranscription', 'user'), ('outputTranscription', 'assistant')):
            text = (content.get(key) or {}).get('text')
            if isinstance(text, str) and text:
                if role == 'user':
                    traffic['transcript_frames'] += 1
                else:
                    waiting_for_tool_reply = False
                    if not history.delegated and is_product_archive_request(history.user):
                        continue
                final = (content.get(key) or {}).get('finished') is True
                previous = history.user if role == 'user' else history.assistant
                if role == 'user' and final:
                    traffic['speech_finished'] = True
                history.transcript(role, text, final)
                if role == 'user':
                    await check_transcription(socket, history, traffic)
                if not history.unclear:
                    snapshot = history.user if role == 'user' else history.assistant
                    if snapshot != previous or final:
                        await socket.send_json({'type': 'transcript', 'role': role, 'text': snapshot,
                                                'final': final, 'snapshot': True, 'turn_id': history.turn_id})
                if role == 'user' and final:
                    traffic['input_final'].set()
        if (history.contextual_advice is None and not history.unclear
                and (history.assistant or content.get('modelTurn') or content.get('turnComplete'))
                and has_product_reference(history.user) and planning_request(history.user)):
            # Some Live generations skip the tool on follow-up advice. Ground
            # the result in the same product even on those turns.
            started = monotonic()
            history.contextual_advice = await shop_tool(socket, token, 'inspect_shop', {}, history, actions, traffic)
            tool_seconds += monotonic() - started
        hold_archive_reply = not history.delegated and is_product_archive_request(history.user)
        if not content.get('interrupted') and not history.unclear and not hold_archive_reply:
            for part in (content.get('modelTurn') or {}).get('parts', []):
                audio = part.get('inlineData') or {}
                if not part.get('thought') and audio.get('mimeType', '').split(';', 1)[0] == 'audio/pcm':
                    encoded = audio.get('data')
                    if isinstance(encoded, str) and len(encoded) <= 256_000:
                        waiting_for_tool_reply = False
                        if first_audio_at is None and len(encoded) > 4:
                            first_audio_at = monotonic()
                            input_ended_at = traffic.pop('input_ended_at', None)
                            logger.info('Live first audio: since_input_end_ms=%s tool_ms=%d',
                                        round((first_audio_at - input_ended_at) * 1000) if input_ended_at is not None else None,
                                        round(tool_seconds * 1000))
                        await socket.send_json({'type': 'audio', 'data': encoded,
                                                **({'review': True} if actions.pending else {})})
        if content.get('generationComplete') and not content.get('interrupted') and not waiting_for_tool_reply:
            generation_complete = True
            await socket.send_json({'type': 'audio_end'})
        replies = []
        for call in (data.get('toolCall') or {}).get('functionCalls', []):
            name, call_id = call.get('name'), call.get('id')
            if not isinstance(name, str) or not isinstance(call_id, str):
                continue
            tool_count += 1
            started = monotonic()
            await check_transcription(socket, history, traffic)
            result = (await shop_tool(socket, token, name, call.get('args', {}), history, actions, traffic)
                      if tool_count <= MAX_TOOLS_PER_TURN else
                      {'accepted': False, 'message': 'Lượt này đã tra cứu nhiều mục. Tóm tắt kết quả rồi chờ câu hỏi tiếp theo.'})
            tool_seconds += monotonic() - started
            replies.append({'id': call_id, 'name': name, 'response': result})
        if replies:
            await upstream.send(json.dumps({'toolResponse': {'functionResponses': replies}}, default=str))
            if traffic.get('manual_turns'):
                # Gemini can mark the tool phase complete before starting the spoken answer.
                waiting_for_tool_reply = True
                generation_complete = False
        completed = content.get('turnComplete') and content.get('interactionStatus') != 'IN_PROGRESS'
        now = loop.time()
        if traffic.get('manual_turns') and (completed or complete_by is not None):
            if content or replies:
                # Audio and both transcriptions can follow an early turnComplete.
                # Keep those chunks in the same turn until output settles.
                tail = 5.0 if waiting_for_tool_reply else .32 if generation_complete else 1.25
                if traffic.get('awaiting_turn') and not traffic.get('speech_finished'):
                    tail = max(tail, .75)
                complete_by = now + tail
            if complete_by is not None and now < complete_by:
                continue
        if completed or complete_by is not None:
            complete_by = None
            generation_complete = False
            waiting_for_tool_reply = False
            traffic['settled_input'] = True
            await check_transcription(socket, history, traffic)
            unclear = history.unclear
            if not unclear and not history.delegated and voice_finished(traffic) and is_product_archive_request(history.user):
                result = await shop_tool(socket, token, 'prepare_chat_request', {'message': history.user}, history, actions, traffic)
                if result.get('accepted'):
                    await upstream.send(json.dumps({'realtimeInput': {'text':
                        'Đọc lại thông tin chính xác sau, rồi chờ người bán xác nhận. ' + (result.get('review') or result['answer'])}}))
                    if traffic.get('manual_turns'):
                        waiting_for_tool_reply = True
                        complete_by = loop.time() + 5
                        continue
            if not history.decision and actions.decision_for(history.user, finished=voice_finished(traffic)):
                result = await actions.decide(history.user, finished=True)
                answer = result.get('answer') or result['message']
                await upstream.send(json.dumps({'realtimeInput': {'text':
                    'Thông báo của ứng dụng: hãy nói lại kết quả đã kiểm chứng bằng giọng nói. ' + answer}}))
            archive_phrase = ('confirm product removal' if history.language == 'en' else 'xac nhan xoa san pham')
            if (actions.pending and not actions.pending.armed and history.assistant
                    and (actions.pending.kind != 'archive' or archive_phrase in plain(history.assistant))):
                actions.pending.armed = True
                traffic['review_turn'] = traffic['turn_signals']
            traffic['speech_finished'] = False
            traffic['settled_input'] = False
            traffic['awaiting_turn'] = False
            traffic['input_final'].set()
            identifier = history.turn_id
            clear_captions = not (history.user or history.results or history.delegated)
            await socket.send_json({'type': 'turn_end', 'turn_id': identifier,
                                    **({'clear_captions': True} if clear_captions else {})})
            first_audio_at = None
            tool_count = 0
            tool_seconds = 0.0
            saved = traffic['save_task'] = asyncio.create_task(save_live_turn(socket, history, notify=True))
            await asyncio.shield(saved)
            traffic.pop('save_task', None)
            if unclear:
                await upstream.send(json.dumps({'realtimeInput': {'text':
                    'Thông báo ứng dụng: lượt nói vừa rồi không rõ. Chỉ nói đúng một câu sau rồi chờ. ' + REPEAT_QUESTION}}))


async def relay(socket, upstream, token, history, *, manual_turns, started):
    await socket.send_json({'type': 'ready', 'seconds': SESSION_SECONDS, 'turn_protocol': int(manual_turns)})
    actions = LiveActions(socket, history)
    if draft := await run_in_threadpool(actions.load_draft):
        await actions.set_draft(draft)
    traffic = {'audio_frames': 0, 'transcript_frames': 0, 'turn_signals': 0, 'manual_turns': manual_turns,
               'input_final': asyncio.Event()}
    microphone = asyncio.create_task(forward_microphone(socket, upstream, traffic, actions,
                                                      manual_turns=manual_turns, started=started))
    tasks = {microphone, asyncio.create_task(forward_response(socket, upstream, token, history, traffic, actions))}
    finishing = False
    done = set()
    try:
        done, _ = await asyncio.wait(tasks, timeout=SESSION_SECONDS, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
        finishing = microphone in done and microphone.result() is True
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if (saving := traffic.get('save_task')) is not None:
            await saving
        await save_live_turn(socket, history, notify=finishing or not done)
        logger.info('Live input ended: audio_frames=%d transcript_frames=%d turn_signals=%d',
                    traffic['audio_frames'], traffic['transcript_frames'], traffic['turn_signals'])
    if finishing:
        return {'type': 'finished'}
    if not done:
        return {'type': 'ended', 'message': 'Đã hết 3 phút Live. Bạn có thể mở phiên mới.'}
    return None


async def open_live_transport(socket, attempt, transport, setup, history_messages):
    async def handshake():
        upstream = await attempt.enter_async_context(transport)
        await upstream.send(setup)
        ready = read_json(await upstream.recv(), 1_000_000)
        check_live_provider_error(ready)
        if 'setupComplete' not in ready:
            raise LiveError('Gemini chưa mở được phiên Live. Kiểm tra quyền sử dụng model trong AI Studio.')
        if history_messages:
            await upstream.send(json.dumps({'clientContent': {'turnComplete': True, 'turns': [
                {'role': 'model' if row['role'] == 'assistant' else 'user',
                 'parts': [{'text': row['content']}]} for row in history_messages
            ]}}, ensure_ascii=False))
        return upstream

    provider = asyncio.create_task(handshake())
    client = asyncio.create_task(socket.receive())
    try:
        done, _ = await asyncio.wait((provider, client), return_when=asyncio.FIRST_COMPLETED)
        if client in done:
            event = client.result()
            if event['type'] == 'websocket.disconnect':
                raise WebSocketDisconnect(event.get('code', 1000))
            raise LiveError('Đợi Live sẵn sàng trước khi gửi âm thanh.')
        return provider.result()
    finally:
        for task in (provider, client):
            if not task.done():
                task.cancel()
        await asyncio.gather(provider, client, return_exceptions=True)


async def connect_live(socket, keys, voice, history, *, manual_turns):
    started = monotonic()
    tried = set()
    messages, focus = await run_in_threadpool(history.initial_context)
    setup = json.dumps(live_setup(history.model, voice, history.language, manual_turns=manual_turns,
                                  initial_history=bool(messages), focus=focus), ensure_ascii=False)
    while credential := keys.available(excluded=tried, reserve=True):
        remaining = LIVE_CONNECT_BUDGET - (monotonic() - started)
        if remaining <= 0:
            raise TimeoutError
        tried.add(credential.slot)
        connected = False
        try:
            async with AsyncExitStack() as attempt:
                async with asyncio.timeout(min(remaining, 12)):
                    transport = connect(
                        GEMINI_LIVE_URL, additional_headers={'x-goog-api-key': credential.secret},
                        open_timeout=min(remaining, 8), close_timeout=2, max_size=1_000_000, max_queue=8,
                    )
                    upstream = await open_live_transport(socket, attempt, transport, setup, messages)
                connected = True
                logger.info('Live upstream ready: slot=%d model=%s elapsed_ms=%d',
                            credential.slot, history.model, round((monotonic() - started) * 1000))
                return await relay(socket, upstream, history.token, history, manual_turns=manual_turns, started=started)
        except (LiveKeyError, ConnectionClosed, InvalidStatus) as error:
            problem = live_key_failure(error)
            if problem is None:
                raise
            if problem.reason == 'rate_limited':
                keys.rate_limited(credential, problem.retry_after)
            else:
                keys.disable(credential)
            logger.warning('Gemini Live key unavailable: slot=%d reason=%s', credential.slot, problem.reason)
            # A live turn may already have changed shop data. Preserve its history
            # instead of replaying that turn on a new upstream session.
            if connected:
                raise problem from None
    raise LiveKeyError('rejected' if all(key.disabled for key in keys.credentials) else 'rate_limited')


@router.websocket('/live')
async def live(socket: WebSocket):
    if not allowed_origin(socket):
        await socket.close(code=1008)
        return
    await socket.accept()
    sessions = socket.app.state.live_sessions
    try:
        credentials = read_json(await asyncio.wait_for(socket.receive_text(), 5), 512)
        if credentials.get('type') != 'auth':
            raise LiveError('Vui lòng đăng nhập để mở Live.')
        try:
            preferences = LivePreferences.model_validate(credentials.get('preferences', {}))
        except ValidationError as error:
            raise LiveError('Cài đặt giọng hoặc ngôn ngữ Live không hợp lệ.') from error
        try:
            conversation_id = UUID(credentials['conversation_id']) if credentials.get('conversation_id') else uuid4()
        except (TypeError, ValueError, AttributeError) as error:
            raise LiveError('Cuộc trò chuyện Live không hợp lệ.') from error
        seller = await run_in_threadpool(authenticate, socket, credentials.get('token'), conversation_id)
        settings = socket.app.state.settings
        keys = getattr(socket.app.state, 'live_gemini_keys', None)
        if keys is None:
            try:
                keys = GeminiKeyPool(gemini_credentials(settings), rpm=None)
            except ValueError:
                raise LiveError('Một key Gemini đang được khai báo với hai Project ID khác nhau.') from None
            socket.app.state.live_gemini_keys = keys
        if not keys.configured:
            raise LiveError('Live cần GEMINI_API_KEY trong .env của máy chủ.')
        if seller in sessions or len(sessions) >= MAX_SESSIONS:
            raise LiveError('Đã có phiên Live đang mở. Đóng phiên cũ rồi thử lại.')
        sessions.add(seller)
        try:
            history = LiveHistory(socket.app.state, credentials['token'], conversation_id, settings.gemini_live_model, preferences.language)
            voice = GEMINI_VOICES[preferences.language].get(preferences.voice,
                GEMINI_VOICES['vi']['female'] if preferences.language == 'vi' else settings.gemini_live_voice)
            terminal = await connect_live(socket, keys, voice, history,
                manual_turns=type(credentials.get('turn_protocol')) is int and credentials['turn_protocol'] == 1)
        finally:
            sessions.discard(seller)
        if terminal:
            await socket.send_json(terminal)
    except WebSocketDisconnect:
        return
    except (LiveError, HTTPException, TimeoutError, WebSocketException, OSError, RuntimeError) as error:
        if isinstance(error, HTTPException):
            message = (error.detail.get('message') if isinstance(error.detail, dict) else error.detail)
        elif isinstance(error, LiveError):
            message = str(error)
        elif isinstance(error, (ConnectionClosed, InvalidStatus)):
            message = 'Gemini Live chưa sẵn sàng. Kiểm tra model, quyền API và hạn mức trong AI Studio.'
        else:
            message = 'Chưa kết nối được Live. Kiểm tra mạng rồi thử lại.'
        try:
            await socket.send_json({'type': 'error', 'message': message})
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
    finally:
        try:
            await socket.close()
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
