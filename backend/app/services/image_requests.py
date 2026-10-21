"""Replay gallery uploads when the phone loses their HTTP response."""
import hashlib
import json
from datetime import datetime

from fastapi import HTTPException

from app.models.chat_request import ChatRequestRecord
from app.schemas.chat import ChatResponse
from app.services.chat_requests import ChatTransaction, request_key
from app.services.product_drafts import create_product_draft_images
from app.services.conversation_state import ensure_conversation_open


async def upload_once(manager, shop, payload, contents, upload_dir):
    key = request_key(shop, payload.request_id)
    with manager.sessions() as session:
        known = session.get(ChatRequestRecord, key) is not None
    if known:
        return _upload_once(manager, shop, payload, contents, upload_dir)
    manager.ensure_conversation_idle(key[0], payload.conversation_id)
    # A text-first listing can hold an agent DB write transaction while waiting
    # for AI. Queue unrelated uploads asynchronously rather than blocking the
    # event loop inside SQLite (which also prevents stopping that inference).
    async with manager.execution:
        return _upload_once(manager, shop, payload, contents, upload_dir)


def _upload_once(manager, shop, payload, contents, upload_dir):
    key = request_key(shop, payload.request_id)
    manager.ensure_conversation_available(key[0], payload.conversation_id)
    fingerprint = hashlib.sha256(json.dumps(['images', str(payload.conversation_id),
        [hashlib.sha256(content).hexdigest() for content in contents]]).encode()).hexdigest()
    with manager.sessions() as source:
        bind = source.get_bind()
    with ChatTransaction(bind=bind, expire_on_commit=False, autoflush=False) as session:
        ensure_conversation_open(session, key[0], payload.conversation_id)
        row = session.get(ChatRequestRecord, key)
        if row:
            manager.ensure_conversation_available(key[0], row.conversation_id)
            ensure_conversation_open(session, key[0], row.conversation_id)
            if row.fingerprint is not None and row.fingerprint != fingerprint:
                raise HTTPException(409, detail={'code': 'request_id_conflict', 'message': 'Mã tải ảnh đã được dùng cho nội dung khác.'})
            return manager.result(key)
        manager.ensure_conversation_idle(key[0], payload.conversation_id)
        row = ChatRequestRecord(shop_slug=key[0], request_id=key[1],
            fingerprint=fingerprint, status='running')
        session.add(row)
        result = ChatResponse(data=create_product_draft_images(session, shop, contents=contents,
            upload_dir=upload_dir, conversation_id=str(payload.conversation_id) if payload.conversation_id else None))
        row.status = 'completed'
        row.conversation_id = result.data.conversation_id
        row.response_json = result.model_dump_json()
        row.updated_at = datetime.utcnow()
        # File writes and draft creation have completed synchronously. There is
        # no inference or await in this transaction.
        from sqlalchemy.orm import Session
        Session.commit(session)
        return result
