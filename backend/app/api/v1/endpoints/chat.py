import json
import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, delete, update
from pydantic import BaseModel, ConfigDict, StrictBool

from app.api.v1.endpoints.seller_tools import get_shop
from app.db.session import get_session
from app.integrations.ute_mall import UTEMallRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.advisor import forget_memory, memory_rows
from app.models.agent_run import AgentRun
from app.models.action import ActionProposal
from app.models.chat_request import ChatRequestRecord
from app.models.conversation_state import ConversationState
from app.models.product_draft import ProductDraft
from app.models.product_edit import ProductEditProposal
from app.services.conversation_state import ensure_conversation_open
from app.services.product_drafts import delete_draft_images
from app.services.conversations import recent_runs, run_data
from app.services.chat_requests import request_key

router = APIRouter(tags=["seller chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request,
               shop: UTEMallRepository = Depends(get_shop)) -> ChatResponse:
    manager = request.app.state.chat_requests
    key = manager.submit(payload, shop)
    # Losing the HTTP connection does not lose the durable result. Only an
    # explicit cancel request stops inference; a retry joins the same task.
    await manager.wait(key)
    return manager.result(key)


@router.get('/chat/requests/{request_id}')
def chat_request_status(request_id: UUID, request: Request,
                        shop: UTEMallRepository = Depends(get_shop)):
    return {'data': request.app.state.chat_requests.status(request_key(shop, request_id))}


@router.post('/chat/requests/{request_id}/cancel')
async def cancel_chat_request(request_id: UUID, request: Request,
                              shop: UTEMallRepository = Depends(get_shop)):
    return {'data': await request.app.state.chat_requests.cancel(request_key(shop, request_id))}


@router.get('/assistant/memory')
def assistant_memory(session: Session = Depends(get_session), shop: UTEMallRepository = Depends(get_shop)):
    return {'data': {'items': [{'scope': row.scope, 'key': row.key,
        'value': json.loads(row.value_json), 'evidence': row.evidence,
        'updated_at': row.updated_at.isoformat() + 'Z'} for row in memory_rows(session, shop)]}}


@router.post('/assistant/memory/reset')
async def reset_assistant_memory(request: Request, session: Session = Depends(get_session),
                                 shop: UTEMallRepository = Depends(get_shop)):
    manager = request.app.state.chat_requests
    tenant = shop.seller_shop_slug or 'local'
    # A response already being generated must not re-save preferences after
    # the seller asked us to forget them.
    for key in list(manager.tasks):
        if key[0] == tenant:
            await manager.cancel(key)
    async with manager.execution:
        count = forget_memory(session, shop)
        session.commit()
    return {'data': {'deleted': count}}


@router.get("/conversations")
def conversations(session: Session = Depends(get_session), shop: UTEMallRepository = Depends(get_shop)):
    groups = session.execute(select(
        AgentRun.conversation_id, func.min(AgentRun.id).label("first_id"),
        func.max(AgentRun.id).label("last_id"), func.count(AgentRun.id).label("turns"),
        ConversationState.pinned_at,
    ).outerjoin(ConversationState, and_(ConversationState.shop_slug == AgentRun.shop_slug,
        ConversationState.conversation_id == AgentRun.conversation_id))
        .where(AgentRun.conversation_id.is_not(None), ConversationState.deleted_at.is_(None),
            AgentRun.shop_slug == (shop.seller_shop_slug or "local"))
        .group_by(AgentRun.conversation_id, ConversationState.pinned_at)
        .order_by(ConversationState.pinned_at.is_not(None).desc(), ConversationState.pinned_at.desc(), func.max(AgentRun.id).desc()).limit(50)).all()
    items = []
    for group in groups:
        first, last = session.get(AgentRun, group.first_id), session.get(AgentRun, group.last_id)
        items.append({"id": group.conversation_id, "title": first.message[:80],
                      "updated_at": last.created_at.isoformat() + "Z", "turns": group.turns,
                      "is_pinned": group.pinned_at is not None})
    return {"data": {"items": items}}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, session: Session = Depends(get_session),
                 shop: UTEMallRepository = Depends(get_shop)):
    ensure_conversation_open(session, shop.seller_shop_slug or 'local', str(conversation_id))
    runs = recent_runs(session, shop, str(conversation_id), limit=100)
    if not runs:
        raise HTTPException(404, detail="Không tìm thấy cuộc trò chuyện.")
    return {"data": {"id": str(conversation_id), "turns": [
        {"message": run.message, "created_at": run.created_at.isoformat() + "Z",
         "response": run_data(session, run)} for run in runs
    ]}}


class ConversationPin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_pinned: StrictBool


@router.patch('/conversations/{conversation_id}')
async def pin_conversation(conversation_id: UUID, payload: ConversationPin,
                     session: Session = Depends(get_session), shop: UTEMallRepository = Depends(get_shop)):
    tenant, identifier = shop.seller_shop_slug or 'local', str(conversation_id)
    ensure_conversation_open(session, tenant, identifier)
    if not recent_runs(session, shop, identifier, limit=1):
        raise HTTPException(404, detail='Không tìm thấy cuộc trò chuyện.')
    state = session.get(ConversationState, (tenant, identifier))
    if state is None:
        state = ConversationState(shop_slug=tenant, conversation_id=identifier)
        session.add(state)
    if payload.is_pinned and not state.pinned_at:
        state.pinned_at = datetime.utcnow()
    elif not payload.is_pinned:
        state.pinned_at = None
    session.commit()
    return {'data': {'id': identifier, 'is_pinned': state.pinned_at is not None}}


@router.delete('/conversations/{conversation_id}')
async def delete_conversation(conversation_id: UUID, request: Request,
                              session: Session = Depends(get_session), shop: UTEMallRepository = Depends(get_shop)):
    tenant, identifier = shop.seller_shop_slug or 'local', str(conversation_id)
    state = session.get(ConversationState, (tenant, identifier))
    known = recent_runs(session, shop, identifier, limit=1) or session.scalar(select(ChatRequestRecord.request_id)
        .where(ChatRequestRecord.shop_slug == tenant, ChatRequestRecord.conversation_id == identifier).limit(1))
    if not state and not known:
        raise HTTPException(404, detail='Không tìm thấy cuộc trò chuyện.')
    manager = request.app.state.chat_requests
    deleting_key = (tenant, identifier)
    if deleting_key in manager.deleting:
        raise HTTPException(409, detail='Cuộc trò chuyện đang được xóa. Bạn thử lại sau nhé.')
    manager.deleting.add(deleting_key)
    session.rollback()  # release reads before cancelling a transaction with staged writes
    try:
        key = manager.conversations.get(deleting_key)
        if key:
            await manager.cancel(key)
        async with manager.execution:
            state = session.get(ConversationState, deleting_key)
            if state is None:
                state = ConversationState(shop_slug=tenant, conversation_id=identifier)
                session.add(state)
            state.deleted_at = state.deleted_at or datetime.utcnow()
            state.pinned_at = None
            proposal_ids = select(AgentRun.proposal_id).where(AgentRun.shop_slug == tenant,
                AgentRun.conversation_id == identifier, AgentRun.proposal_id.is_not(None))
            session.execute(update(ActionProposal).where(ActionProposal.id.in_(proposal_ids),
                ActionProposal.status == 'pending').values(status='rejected', decided_at=datetime.utcnow()))
            edit_ids = select(AgentRun.product_edit_proposal_id).where(AgentRun.shop_slug == tenant,
                AgentRun.conversation_id == identifier, AgentRun.product_edit_proposal_id.is_not(None))
            session.execute(update(ProductEditProposal).where(ProductEditProposal.shop_slug == tenant,
                ProductEditProposal.id.in_(edit_ids), ProductEditProposal.status == 'pending')
                .values(status='rejected', decided_at=datetime.utcnow()))
            drafts = session.scalars(select(ProductDraft).where(ProductDraft.shop_slug == tenant,
                ProductDraft.conversation_id == identifier, ProductDraft.status != 'published')).all()
            for draft in drafts:
                draft.status = 'cancelled'
                draft.decided_at = draft.updated_at = datetime.utcnow()
            session.execute(delete(AgentRun).where(AgentRun.shop_slug == tenant, AgentRun.conversation_id == identifier))
            session.execute(update(ChatRequestRecord).where(ChatRequestRecord.shop_slug == tenant,
                ChatRequestRecord.conversation_id == identifier).values(status='failed', response_json=None,
                error_status=410, error_json=json.dumps({'code': 'conversation_deleted',
                    'message': 'Cuộc trò chuyện đã được xóa.'}), updated_at=datetime.utcnow()))
            session.commit()
            for draft in drafts:
                try:
                    delete_draft_images(draft, request.app.state.settings.shop_product_upload_dir)
                except OSError:
                    logging.getLogger(__name__).warning('Could not remove images from deleted draft %s', draft.id)
    finally:
        manager.deleting.discard(deleting_key)
    return {'data': {'id': identifier, 'deleted': True}}
