"""Use the seller chat's tools and decisions inside an authenticated Live session."""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool

from app.ai.listing_text import _wants_ai_description, labelled_copy, listing_copy_choice
from app.ai.money import plain
from app.ai.quick_reads import quick_read
from app.ai.small_talk import social_reply
from app.integrations.order_management import OrderConflictError, order_detail, update_order
from app.integrations.ute_mall import ShopItemNotFoundError
from app.models.agent_run import AgentRun
from app.schemas.chat import ChatRequest
from app.schemas.order_management import OrderUpdate
from app.services.advisor import forget_memory, is_forget_request
from app.services.auth import verify_seller
from app.services.conversation_state import ensure_conversation_open
from app.services.conversations import recent_runs
from app.services.live_language import copy_choice, listing_opening, spoken_listing_name
from app.services.live_shop import strategy_summary
from app.services.product_archive_chat import archive_target_reply
from app.services.product_drafts import (
    SELLER_WRITES_COPY, ProductDraftConflictError, ProductDraftNotFoundError, cancel_product_draft,
    draft_stored_images, draft_to_dict, get_active_draft, get_product_draft, has_copy_offer, publish_product_draft,
    spoken_listing_amounts,
)
from app.services.product_edits import decide_product_edit, edit_to_dict
from app.services.seller_tools import (
    ProposalConflictError, ProposalNotFoundError, confirm_price_proposal, proposal_to_dict, reject_price_proposal,
)


@dataclass
class Review:
    kind: str
    value: dict
    message: str
    payload: OrderUpdate | None = None
    armed: bool = False


class LiveActions:
    def __init__(self, socket, history):
        self.socket = socket
        self.history = history
        self.state = socket.app.state
        self.shop = self.state.shop_repository
        self.tenant = self.shop.seller_shop_slug or 'local'
        self.manager = self.state.chat_requests
        self.pending: Review | None = None

    def say(self, vi, en):
        return en if self.history.language == 'en' else vi

    def authenticate(self, session):
        verify_seller(self.shop, session, self.history.token)
        ensure_conversation_open(session, self.tenant, self.history.conversation_id)

    def follows_archive_request(self, speech):
        with self.state.session_factory() as session:
            self.authenticate(session)
            return archive_target_reply(speech, recent_runs(session, self.shop, self.history.conversation_id, limit=1))

    def load_draft(self, draft_id=None):
        with self.state.session_factory() as session:
            self.authenticate(session)
            if draft_id:
                draft = get_product_draft(session, self.shop, draft_id)
                if draft.conversation_id != self.history.conversation_id or draft.status not in ('collecting', 'ready'):
                    raise ValueError('Ảnh này không thuộc bản nháp đang soạn trong phiên Live.')
            else:
                draft = get_active_draft(session, self.shop, self.history.conversation_id)
                self.history.draft_copy_offer = bool(draft and has_copy_offer(session, draft))
            return draft_to_dict(draft) if draft else None

    async def set_draft(self, draft, *, offer_copy=False):
        if not draft or self.pending and self.pending.kind in ('publish', 'cancel_draft'):
            self.pending = None
        await self.socket.send_json({'type': 'draft', 'draft': jsonable_encoder(draft)})
        if draft and draft['status'] == 'ready' and not offer_copy:
            self.pending = Review('publish', draft,
                self.say(f"Mình chuẩn bị đăng {draft['name']}, giá {draft['price_vnd']} đồng, "
                         f"tồn kho {draft['stock']}, có {draft['image_count']} ảnh. Bạn nói «xác nhận đăng» để mình đăng ngay.",
                         f"Ready to list {draft['name']} at {draft['price_vnd']} VND, with {draft['stock']} in stock and "
                         f"{draft['image_count']} photos. Say “confirm publish” to list it."))
        return self.pending.message if self.pending and self.pending.kind == 'publish' else None

    async def clear_review(self):
        if self.pending and self.pending.kind == 'archive':
            await self.socket.send_json({'type': 'archive_review', 'name': ''})
        self.pending = None

    async def listing_copy(self, proposed_message=None):
        """Separate the seller's title from Gemini's interpretation of the item."""
        if not self.history.user:
            return None
        if self.history.listing_reply:
            return self.history.listing_reply
        speech = self.history.user
        if listing_opening(speech):
            self.history.expecting_title = True
            self.history.copy_choice_touched = True
            self.history.listing_reply = {'accepted': True, 'answer': self.say(
                'Được. Bạn muốn đăng món gì? Bạn có thể nói tên sản phẩm hoặc gửi ảnh nhé.',
                'Sure. What would you like to list? You can tell me the product name or send a photo.')}
            return self.history.listing_reply
        if self.history.draft_copy_offer and listing_copy_choice(speech) is not None:
            self.history.listing_reply = await self.ask_chat(speech)
            return self.history.listing_reply
        if _wants_ai_description(speech) or labelled_copy(speech):
            dictated = spoken_listing_name(speech)
            if dictated and dictated[1] and speech.endswith(dictated[0] + '.'):
                speech = speech.removesuffix('.')
            if proposed_message:
                details = [line for line in proposed_message.splitlines()
                           if line.startswith(('Mô tả: ', 'Ngành hàng: ')) and line.partition(': ')[2].casefold() in speech.casefold()]
                if details:
                    speech += '\n' + '\n'.join(details)
            draft = await run_in_threadpool(self.load_draft)
            if _wants_ai_description(speech) and self.history.copy_subject:
                request = '\n'.join(['Đăng sản phẩm lên shop.', speech,
                                     f'Tên sản phẩm: {self.history.copy_subject}', *self.history.copy_amounts])
                self.history.copy_subject = None
                self.history.copy_amounts = []
                self.history.copy_choice_touched = True
            elif draft:
                request = speech
            elif labelled_copy(speech):
                request = 'Đăng sản phẩm lên shop.\n' + speech
            else:
                self.history.expecting_title = True
                self.history.copy_choice_touched = True
                self.history.listing_reply = {'accepted': True, 'answer': self.say(
                    'Bạn cho mình biết món cần đăng hoặc thêm một ảnh nhé, mình sẽ tự gợi ý nội dung.',
                    'Tell me what you’re selling or add a photo, and I’ll suggest the listing copy.')}
                return self.history.listing_reply
            self.history.expecting_title = False
            self.history.copy_choice_touched = True
            self.history.listing_reply = await self.ask_chat(request)
            return self.history.listing_reply
        if self.history.language != 'vi':
            return None
        if (self.history.copy_subject or self.history.expecting_title) and cancel_draft_words(speech):
            self.history.copy_subject = None
            self.history.copy_amounts = []
            self.history.expecting_title = False
            self.history.copy_choice_touched = True
            if await run_in_threadpool(self.load_draft):
                return await self.ask_chat(speech)
            self.history.listing_reply = {'accepted': True, 'answer': 'Ừ, mình dừng việc soạn sản phẩm ở đây nhé.'}
            return self.history.listing_reply
        choice = copy_choice(speech) if self.history.copy_subject else None
        if not choice and (social_reply(speech) or quick_read(speech, today=datetime.now(self.shop.timezone).date())):
            return None
        spoken = spoken_listing_name(speech, expecting_title=self.history.expecting_title)
        if choice:
            name = self.history.copy_subject
            amounts = self.history.copy_amounts
            self.history.copy_subject = None
            self.history.copy_amounts = []
            self.history.copy_choice_touched = True
            direction = ('AI tự viết lại tiêu đề và mô tả cho bắt mắt, dùng đúng thông tin đã có.'
                         if choice == 'polish' else SELLER_WRITES_COPY)
            request = '\n'.join(['Đăng sản phẩm lên shop.', direction, f'Tên sản phẩm: {name}', *amounts])
            reply = await self.ask_chat(request)
        elif spoken:
            name, exact = spoken
            self.history.expecting_title = False
            self.history.copy_subject = None if exact else name
            amounts = spoken_listing_amounts(speech.replace(name, '', 1))
            if exact:
                labels = {line.partition(':')[0] for line in amounts}
                amounts += [line for line in self.history.copy_amounts if line.partition(':')[0] not in labels]
            self.history.copy_amounts = [] if exact else amounts
            self.history.copy_choice_touched = True
            if exact:
                extra = amounts.copy()
                if proposed_message:
                    for line in proposed_message.splitlines()[1:]:
                        label, _, value = line.partition(': ')
                        if label in {'Mô tả', 'Ngành hàng'} and value.casefold() in speech.casefold():
                            extra.append(line)
                reply = await self.ask_chat('\n'.join(['Đăng sản phẩm lên shop.', f'Tên sản phẩm: {name}', *extra]))
                if not reply.get('review'):
                    question = reply['answer'].split('\n\n')[-1]
                    reply['answer'] = f'Mình giữ nguyên tiêu đề “{name}”. ' + question
            else:
                reply = {'accepted': True, 'answer':
                         f'Mình hiểu bạn đang bán {name}. Bạn muốn mình viết tiêu đề và mô tả bắt mắt hơn, hay giữ tên này?'}
        elif proposed_message is None:
            return None
        elif self.history.copy_subject:
            reply = {'accepted': True, 'answer': 'Bạn muốn giữ tên đang nói hay để mình viết tiêu đề và mô tả bắt mắt hơn?'}
        elif (draft := await run_in_threadpool(self.load_draft)) and draft.get('name'):
            reply = await self.ask_chat(speech)
        else:
            self.history.expecting_title = True
            self.history.copy_choice_touched = True
            reply = {'accepted': True, 'answer':
                     'Bạn muốn đặt tiêu đề gì? Bạn có thể đọc đúng tiêu đề, hoặc nói món hàng bạn muốn bán.'}
        self.history.listing_reply = reply
        return reply

    async def ask_chat(self, message):
        if self.history.delegated:
            return {'accepted': False, 'message': self.say('Mình đã xử lý yêu cầu này. Dùng kết quả của công cụ trước.',
                                                           'Use the previous result for this turn.')}
        if is_forget_request(message):
            await self.clear_review()
            self.pending = Review('memory', {'id': 0},
                'Bạn muốn xóa những điều mình ghi nhớ về shop. Nói «xác nhận xóa ghi nhớ» để thực hiện.')
            return {'accepted': True, 'review': self.pending.message}
        with self.state.session_factory() as session:
            self.authenticate(session)
        await self.clear_review()
        request = ChatRequest(message=message[:4000], conversation_id=UUID(self.history.conversation_id), request_id=uuid4())
        key = self.manager.submit(request, self.shop, review_only=True)
        await self.manager.wait(key)
        data = self.manager.result(key).data.model_dump()
        self.history.delegated = data['run_id']
        draft = data.get('product_draft')
        if brief := data['facts'].get('business_advisory'):
            summary = strategy_summary(brief, language=self.history.language)
            display = {'id': str(uuid4()), 'turn_id': self.history.turn_id, 'language': self.history.language,
                       'question': message, 'answer': data['answer'], 'report': data.get('report'),
                       'order_id': None, 'spoken_summary': summary}
            self.history.result(display, data['facts'])
            await self.socket.send_json({'type': 'shop_result', **display})
            return {'accepted': True, 'answer': summary, 'detailed_plan': True}
        if draft and not draft['name'] and 'name' in draft['missing_fields'] and self.history.language == 'vi':
            self.history.expecting_title = self.history.copy_choice_touched = True
            data['answer'] = 'Bạn muốn đọc nguyên văn tiêu đề, hay nói món hàng để mình gợi ý tên và mô tả?'
        self.history.draft_copy_offer = bool(draft and data['facts'].get('copy_offer'))
        review_message = await self.set_draft(draft, offer_copy=self.history.draft_copy_offer) if draft else None
        if draft and (cancel_draft_words(message) or cancel_draft_words(self.history.user)):
            self.pending = Review('cancel_draft', draft, f"Bạn muốn hủy bản nháp {draft['name'] or 'sản phẩm này'}. Nói «xác nhận hủy bản nháp» để tiếp tục.")
            review_message = self.pending.message
        if (price := data.get('proposal')) and price['status'] == 'pending':
            self.pending = Review('price', price,
                f"Đổi giá {price['product_name']}, mã {price['sku']}, từ {price['old_price_vnd']} thành {price['new_price_vnd']} đồng. "
                "Bạn nói «xác nhận cập nhật sản phẩm» để lưu.")
            review_message = self.pending.message
        if (edit := data.get('product_edit_proposal')) and edit['status'] == 'pending':
            if edit['action'] == 'archive':
                self.pending = Review('archive', edit, self.say(
                    f"Bạn muốn xóa {edit['product_name']} khỏi gian hàng. Các đơn cũ vẫn được giữ. Bạn nói «xác nhận xóa sản phẩm» nhé.",
                    f"You asked to remove {edit['product_name']} from your shop. Past orders will be kept. Say “confirm product removal”."))
            else:
                fields = {'name': 'tên', 'description': 'mô tả', 'price_vnd': 'giá', 'stock': 'tồn kho'}
                changes = '; '.join(f"{fields[item['field']]} từ {item['before']} thành {item['after']}" for item in edit['changes'])
                self.pending = Review('edit', edit, f"Sửa {edit['product_name']}, mã {edit['sku']}. {changes}. "
                                      "Bạn nói «xác nhận cập nhật sản phẩm» để lưu.")
            review_message = self.pending.message
        if review_message:
            if self.pending and self.pending.kind == 'archive':
                await self.socket.send_json({'type': 'archive_review', 'name': self.pending.value['product_name']})
            return {'accepted': True, 'review': review_message}
        instruction = (' Hướng dẫn bạn bấm nút Thêm ảnh trong Live. Ảnh được lưu ngay sau khi chọn.'
                       if draft and 'image' in draft['missing_fields'] else '')
        if draft and draft['image_count'] and not draft['name']:
            instruction += ' Bạn có thể dùng ảnh nếu đã nhìn thấy và hỏi tên sản phẩm để xác nhận.'
        return {'accepted': True, 'answer': data['answer'][:3500], 'instruction': instruction}

    async def accept_gallery(self, draft_id, run_id):
        draft, photos = await run_in_threadpool(self.gallery, draft_id, run_id)
        await self.clear_review()
        review = await self.set_draft(draft)
        missing = {'name': 'tên sản phẩm', 'price_vnd': 'giá bán', 'stock': 'tồn kho', 'category_id': 'ngành hàng',
                   'description': 'mô tả'}
        labels = ', '.join(missing[field] for field in draft['missing_fields'] if field in missing)
        return review or self.say(f"Mình đã lưu {draft['image_count']} ảnh trong bản nháp. "
                                  f"Phần còn thiếu: {labels}. Chỉ hỏi dữ kiện cần thiết tiếp theo.",
                                  f"I saved {draft['image_count']} photos in the draft. "
                                  f"Ask for the next missing field in English. Missing fields: {labels}."), photos

    def gallery(self, draft_id, run_id):
        with self.state.session_factory() as session:
            self.authenticate(session)
            run = session.get(AgentRun, run_id)
            if not run or run.shop_slug != self.tenant or run.conversation_id != self.history.conversation_id \
                    or run.tool_name != 'create_product_draft' or run.product_draft_id != draft_id:
                raise ValueError('Không tìm thấy lượt thêm ảnh trong phiên.')
            draft = get_product_draft(session, self.shop, draft_id)
            if draft.status not in ('collecting', 'ready'):
                raise ValueError('Bản nháp đã đóng.')
            images = draft_stored_images(draft)
            facts = json.loads(run.facts_json)
            photos = []
            for index in facts.get('image_indices', list(range(len(images)))):
                if type(index) is not int or not 0 <= index < len(images):
                    continue
                image = images[index]
                if image['mime'] == 'image/jpeg' and image['bytes'] <= 510_000:
                    path = self.state.settings.shop_product_upload_dir / Path(image['filename']).name
                    if path.is_file():
                        photos.append(path.read_bytes())
            return draft_to_dict(draft), photos

    async def prepare_order(self, order_id, changes):
        detail = await run_in_threadpool(self.order, order_id)
        if changes.keys() - ({'status'} | set(detail['editable_fields'])):
            raise ValueError('Những trường này hiện chưa chỉnh sửa được trên đơn hàng.')
        if 'status' in changes and changes['status'] not in detail['allowed_statuses']:
            raise ValueError('Đơn này chưa thể chuyển sang trạng thái yêu cầu.')
        payload = OrderUpdate(**changes, request_id=uuid4(), expected_version=detail['version'])
        fields = {'shipping_name': 'người nhận', 'shipping_phone': 'số điện thoại', 'shipping_address': 'địa chỉ',
                  'shipping_carrier': 'đơn vị vận chuyển', 'tracking_number': 'mã vận đơn', 'note': 'ghi chú', 'status': 'trạng thái'}
        statuses = {'paid': 'chờ lấy hàng', 'shipped': 'đang giao', 'delivered': 'đã giao', 'cancelled': 'đã hủy'}
        summary = '; '.join(f"{fields[key]} thành {statuses.get(value, value) or 'để trống'}" for key, value in changes.items())
        await self.clear_review()
        self.pending = Review('order', {'id': order_id},
                              f"Cập nhật đơn {order_id}, {summary}. Bạn nói «xác nhận cập nhật đơn» để lưu.", payload)
        return {'accepted': True, 'review': self.pending.message}

    def order(self, order_id):
        with self.state.session_factory() as session:
            self.authenticate(session)
        return order_detail(self.shop, order_id)

    def decision_for(self, speech, *, finished):
        pending = self.pending
        if not pending or not pending.armed or not finished or self.history.unclear:
            return None
        words = spoken_words(speech)
        reject = words in {'huy yeu cau', 'khong dong y', 'dung cap nhat', 'chua dang', 'dung dang',
                           'khong xoa', 'dung xoa', 'chua xoa'}
        phrases = {
            'publish': {'xac nhan dang', 'xac nhan dang san pham', 'dang di', 'dang luon', 'dong y dang', 'dang san pham di'},
            'cancel_draft': {'xac nhan huy ban nhap'},
            'price': {'xac nhan cap nhat san pham', 'xac nhan doi gia', 'dong y doi gia'},
            'edit': {'xac nhan cap nhat san pham', 'dong y cap nhat san pham'},
            'archive': {'xac nhan xoa san pham', 'xac nhan go khoi gian hang'},
            'order': {'xac nhan cap nhat don', 'xac nhan cap nhat don hang'},
            'memory': {'xac nhan xoa ghi nho'},
        }
        if self.history.language == 'en':
            reject = words in {'cancel request', 'do not publish', 'do not update', 'do not remove', 'stop this change'}
            phrases = {
                'publish': {'confirm publish', 'publish it', 'confirm listing', 'confirm publishing'},
                'cancel_draft': {'confirm draft cancellation', 'confirm cancel draft'},
                'price': {'confirm product update', 'confirm price update'},
                'edit': {'confirm product update'},
                'archive': {'confirm product removal', 'confirm product deletion'},
                'order': {'confirm order update'},
                'memory': {'confirm memory reset'},
            }
        if reject or words in phrases[pending.kind]:
            return pending, reject
        return None

    async def decide(self, speech, *, finished):
        decision = self.decision_for(speech, finished=finished)
        if not decision:
            return {'accepted': False, 'message': self.pending.message if self.pending else
                    'Mình cần đọc lại yêu cầu trước và nghe bạn xác nhận ở lượt tiếp theo.'}
        pending, reject = decision
        self.pending = None
        try:
            async with self.manager.execution:
                self.manager.ensure_conversation_idle(self.tenant, self.history.conversation_id)
                result, message, changed = await run_in_threadpool(self.apply, pending, reject)
        except (ProductDraftConflictError, ProductDraftNotFoundError, ProposalConflictError,
                ProposalNotFoundError, OrderConflictError, ShopItemNotFoundError):
            if pending.kind == 'archive':
                await self.socket.send_json({'type': 'archive_review', 'name': ''})
            return {'accepted': False, 'message': 'Thông tin vừa thay đổi hoặc thao tác không còn hợp lệ. Mình cần đọc lại trước khi bạn xác nhận.'}
        self.history.decision = (pending.kind, pending.value['id'], message)
        await self.socket.send_json({'type': 'action_done', 'changed': changed, 'message': message,
                                     'draft': jsonable_encoder(result) if pending.kind in ('publish', 'cancel_draft') else None})
        return {'accepted': True, 'answer': message}

    def apply(self, pending, reject):
        kind, data = pending.kind, pending.value
        identifier = data['id']
        with self.state.session_factory() as session:
            self.authenticate(session)
            if kind in ('publish', 'cancel_draft'):
                draft = get_product_draft(session, self.shop, identifier)
                if draft.conversation_id != self.history.conversation_id or draft_to_dict(draft) != data:
                    raise ProductDraftConflictError('Bản nháp đã thay đổi.')
                if reject:
                    return data, self.say('Mình giữ nguyên bản nháp để bạn làm tiếp khi cần.', 'I kept the draft for later.'), False
                if kind == 'cancel_draft':
                    result = cancel_product_draft(session, self.shop, identifier, self.state.settings.shop_product_upload_dir)
                    return draft_to_dict(result), self.say('Mình đã hủy bản nháp.', 'I cancelled the draft.'), False
                result = publish_product_draft(session, self.shop, identifier)
                return draft_to_dict(result), self.say(f'Mình đã đăng {result.name} lên shop. Mã sản phẩm là {result.sku}.',
                                                      f'I listed {result.name} in your shop. Its SKU is {result.sku}.'), True
            if kind == 'order':
                if reject:
                    return None, self.say('Mình đã bỏ yêu cầu cập nhật đơn.', 'I discarded the order update.'), False
                update_order(self.shop, identifier, pending.payload)
                return None, self.say(f'Mình đã cập nhật đơn {identifier}.', f'I updated order {identifier}.'), True
            if kind == 'memory':
                if reject:
                    return None, self.say('Mình giữ nguyên ghi nhớ hiện tại.', 'I kept your shop memory.'), False
                forget_memory(session, self.shop)
                session.commit()
                return None, self.say('Mình đã xóa ghi nhớ về shop.', 'I cleared your shop memory.'), False
            if kind == 'price':
                decide = reject_price_proposal if reject else confirm_price_proposal
                result, replayed = decide(session, self.shop, identifier)
                result = proposal_to_dict(result, idempotent=replayed)
            else:
                result, replayed = decide_product_edit(session, self.shop, identifier, approve=not reject)
                result = edit_to_dict(result, idempotent=replayed)
            if kind == 'archive' and not reject:
                return result, self.say(f"Mình đã xóa {result['product_name']} khỏi gian hàng.",
                                        f"I removed {result['product_name']} from your shop."), not replayed
            return result, (self.say('Mình đã bỏ đề xuất cập nhật.', 'I discarded the proposed update.') if reject else
                            self.say('Mình đã cập nhật sản phẩm trong shop.', 'I updated the product in your shop.')), not reject


def spoken_words(value):
    if any(char in value for char in '?"“”:'):
        return ''
    words = plain(value).lower().strip(' .!,…').split()
    if words and words[0] in ('toi', 'minh', 'em', 'i'):
        words = words[1:]
    if words and words[-1] in ('nhe', 'a', 'please'):
        words = words[:-1]
    return ' '.join(words)


def cancel_draft_words(value):
    return spoken_words(value) in {'huy ban nhap', 'bo ban nhap', 'huy ban nhap nay'}
