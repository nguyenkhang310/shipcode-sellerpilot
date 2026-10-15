import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.api.v1.endpoints.seller_tools import get_shop
from app.db.session import get_session
from app.integrations.ute_mall import UTEMallRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.advisor import forget_memory, memory_rows
from app.models.agent_run import AgentRun
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
    ).where(AgentRun.conversation_id.is_not(None),
            AgentRun.shop_slug == (shop.seller_shop_slug or "local"))
        .group_by(AgentRun.conversation_id).order_by(func.max(AgentRun.id).desc()).limit(50)).all()
    items = []
    for group in groups:
        first, last = session.get(AgentRun, group.first_id), session.get(AgentRun, group.last_id)
        items.append({"id": group.conversation_id, "title": first.message[:80],
                      "updated_at": last.created_at.isoformat() + "Z", "turns": group.turns})
    return {"data": {"items": items}}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: UUID, session: Session = Depends(get_session),
                 shop: UTEMallRepository = Depends(get_shop)):
    runs = recent_runs(session, shop, str(conversation_id), limit=100)
    if not runs:
        raise HTTPException(404, detail="Không tìm thấy cuộc trò chuyện.")
    return {"data": {"id": str(conversation_id), "turns": [
        {"message": run.message, "created_at": run.created_at.isoformat() + "Z",
         "response": run_data(session, run)} for run in runs
    ]}}
