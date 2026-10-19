"""Single-process local job runner with durable, shop-scoped request identity.

The response, chat history, draft edits and memory are committed together.
HTTP disconnects do not cancel jobs. Explicit cancellation rolls them back.
Run one Uvicorn worker; a shared worker queue is needed for multi-process hosting.
"""
import asyncio
import hashlib
import json
import logging
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chat_request import ChatRequestRecord
from app.schemas.chat import ChatResponse
from app.services.chat_dispatch import dispatch_chat
from app.services.conversation_state import ensure_conversation_open
from app.ai.text import assistant_text

logger = logging.getLogger(__name__)
ACTIVE = ('queued', 'running')


def request_key(shop, request_id):
    return (shop.seller_shop_slug or 'local', str(request_id))


class ChatTransaction(Session):
    def commit(self):
        # Legacy services may commit internally. The runner owns the actual
        # transaction so cancellation cannot leave half a completed chat turn.
        self.flush()


class ChatRequestManager:
    def __init__(self, session_factory, provider, settings):
        self.sessions = session_factory
        self.provider = provider
        self.settings = settings
        self.tasks = {}
        self.conversations = {}
        self.deleting = set()
        self.execution = asyncio.Lock()

    def recover(self):
        # Never automatically repeat an action interrupted by a process crash.
        with self.sessions() as session:
            for row in session.scalars(select(ChatRequestRecord).where(ChatRequestRecord.status.in_(ACTIVE))):
                row.status = 'failed'
                row.error_status = 409
                row.error_json = json.dumps({'code': 'chat_interrupted', 'message':
                    'Backend đã khởi động lại giữa lúc xử lý. Kiểm tra lịch sử và bản nháp trước khi gửi yêu cầu mới.'})
                row.updated_at = datetime.utcnow()
            session.commit()

    def submit(self, payload, shop):
        key = request_key(shop, payload.request_id or uuid4())
        self.ensure_conversation_available(key[0], payload.conversation_id)
        fingerprint = hashlib.sha256(json.dumps(
            [payload.message, str(payload.conversation_id) if payload.conversation_id else None],
            ensure_ascii=False).encode()).hexdigest()
        with self.sessions() as session:
            ensure_conversation_open(session, key[0], payload.conversation_id)
            row = session.get(ChatRequestRecord, key)
            if row:
                self.ensure_conversation_available(key[0], row.conversation_id)
                ensure_conversation_open(session, key[0], row.conversation_id)
                if row.fingerprint is not None and row.fingerprint != fingerprint:
                    raise HTTPException(409, detail={'code': 'request_id_conflict',
                        'message': 'Mã tin nhắn đã được dùng cho nội dung khác.'})
                return key
            conversation_id = str(payload.conversation_id or uuid4())
            conversation = (key[0], conversation_id)
            if conversation in self.conversations:
                raise HTTPException(409, detail={'code': 'conversation_busy',
                    'message': 'Hội thoại đang xử lý một tin nhắn. Hãy chờ hoặc dừng trước khi gửi tiếp.'})
            if len(self.tasks) >= 16:
                raise HTTPException(429, detail={'code': 'chat_queue_full',
                    'message': 'Có nhiều yêu cầu đang chờ. Bạn thử lại sau nhé.'})
            session.add(ChatRequestRecord(shop_slug=key[0], request_id=key[1],
                conversation_id=conversation_id, fingerprint=fingerprint, status='queued'))
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row = session.get(ChatRequestRecord, key)
                if not row or row.fingerprint != fingerprint:
                    raise HTTPException(409, detail='Mã yêu cầu đã tồn tại.')
                return key
        resolved = payload.model_copy(update={'conversation_id': conversation_id})
        self.conversations[conversation] = key
        self.tasks[key] = asyncio.create_task(self._run(key, resolved, shop))
        return key

    def ensure_conversation_available(self, tenant, conversation_id):
        if conversation_id and (tenant, str(conversation_id)) in self.deleting:
            raise HTTPException(410, detail={'code': 'conversation_deleted',
                'message': 'Cuộc trò chuyện đang được xóa. Bạn mở cuộc trò chuyện mới nhé.'})

    async def _run(self, key, payload, shop):
        try:
            async with asyncio.timeout(300):
                async with self.execution:
                    self._terminal(key, 'running')
                    with self.sessions() as connection_session:
                        bind = connection_session.get_bind()
                    with ChatTransaction(bind=bind, expire_on_commit=False, autoflush=False) as session:
                        session.info['defer_advisor_writes'] = True
                        result = await dispatch_chat(payload, session, shop, self.provider(), self.settings)
                        from app.services.advisor import flush_memory_writes
                        flush_memory_writes(session)
                        row = session.get(ChatRequestRecord, key)
                        row.status = 'completed'
                        row.response_json = result.model_dump_json()
                        row.updated_at = datetime.utcnow()
                        # No await between service effects and final commit: an
                        # explicit cancel either wins before this or sees completed.
                        Session.commit(session)
        except asyncio.CancelledError:
            self._terminal(key, 'cancelled')
        except TimeoutError:
            self._terminal(key, 'failed', 504, {'code': 'chat_timeout',
                'message': 'Yêu cầu mất quá nhiều thời gian và đã dừng. Bạn có thể gửi lại.'})
        except HTTPException as error:
            self._terminal(key, 'failed', error.status_code, error.detail)
        except Exception:
            logger.exception('Chat request failed: %s', key[1])
            self._terminal(key, 'failed', 500, {'code': 'chat_failed',
                'message': 'Chưa xử lý được tin nhắn. Kiểm tra lịch sử và bản nháp trước khi gửi yêu cầu mới.'})
        finally:
            self.tasks.pop(key, None)
            self.conversations.pop((key[0], str(payload.conversation_id)), None)

    def _terminal(self, key, status, error_status=None, detail=None):
        with self.sessions() as session:
            row = session.get(ChatRequestRecord, key)
            if row is None or row.status not in ACTIVE:
                return
            row.status = status
            row.error_status = error_status
            row.error_json = json.dumps(detail, ensure_ascii=False) if detail is not None else None
            row.updated_at = datetime.utcnow()
            session.commit()

    async def wait(self, key):
        task = self.tasks.get(key)
        if task is not None:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                # A queued task can be cancelled before _run starts. The
                # cancel endpoint records its terminal state independently.

    def status(self, key):
        with self.sessions() as session:
            row = session.get(ChatRequestRecord, key)
            if row is None:
                raise HTTPException(404, detail={'code': 'chat_request_not_found',
                    'message': 'Không tìm thấy yêu cầu.'})
            response = json.loads(row.response_json) if row.response_json else None
            if isinstance(response, dict) and isinstance(response.get('data'), dict):
                if isinstance(response['data'].get('answer'), str):
                    response['data']['answer'] = assistant_text(response['data']['answer'])
            return {'request_id': row.request_id, 'conversation_id': row.conversation_id,
                'status': row.status,
                'response': response,
                'error': {'status': row.error_status, 'detail': json.loads(row.error_json)} if row.error_json else None}

    def result(self, key):
        state = self.status(key)
        if state['status'] == 'completed':
            return ChatResponse.model_validate(state['response'])
        if state['status'] == 'cancelled':
            raise HTTPException(409, detail={'code': 'chat_cancelled', 'message': 'Tin nhắn đã được dừng.'})
        if state['error']:
            raise HTTPException(state['error']['status'], detail=state['error']['detail'])
        raise HTTPException(409, detail={'code': 'chat_in_progress', 'message': 'Tin nhắn đang được xử lý.'})

    async def cancel(self, key):
        task = self.tasks.get(key)
        if task:
            if not task.cancelling():
                task.cancel()
            # If cancelled before its coroutine starts, _run's finally never runs.
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            self.tasks.pop(key, None)
            for conversation, owner in list(self.conversations.items()):
                if owner == key:
                    self.conversations.pop(conversation, None)
        with self.sessions() as session:
            row = session.get(ChatRequestRecord, key)
            if row is None:
                # A cancel may arrive before the original POST on a slow network.
                session.add(ChatRequestRecord(shop_slug=key[0], request_id=key[1], status='cancelled'))
                session.commit()
        self._terminal(key, 'cancelled')
        return self.status(key)

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.recover()
