import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.browser_connector import BrowserAssistRequest


def authorize(request: Request):
    token = request.app.state.settings.browser_connector_token.get_secret_value()
    if len(token) < 32:
        raise HTTPException(503, detail='Chưa bật kết nối extension. Chạy npm run extension:setup rồi khởi động lại backend.')
    supplied = request.headers.get('authorization', '')
    if not secrets.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
        raise HTTPException(401, detail='Khóa ghép nối extension không đúng.')
    origin = request.headers.get('origin')
    if origin and not origin.startswith('chrome-extension://'):
        raise HTTPException(403, detail='Nguồn kết nối không hợp lệ.')


router = APIRouter(prefix='/browser-connector', tags=['Shopee browser connector'], dependencies=[Depends(authorize)])


@router.get('/health')
def health():
    return {'data': {'status': 'ok', 'integration_mode': 'shopee_browser', 'writes': 'user_reviewed_form_fill'}}


@router.post('/requests', status_code=202)
async def start(payload: BrowserAssistRequest, request: Request):
    request.app.state.browser_requests.start(payload, request.app.state.ai_provider)
    return {'data': {'request_id': str(payload.request_id), 'status': 'accepted'}}


@router.get('/requests/{connection_id}/{request_id}')
def status(connection_id: UUID, request_id: UUID, request: Request):
    return {'data': request.app.state.browser_requests.status(connection_id, request_id)}


@router.post('/requests/{connection_id}/{request_id}/cancel')
async def cancel(connection_id: UUID, request_id: UUID, request: Request):
    manager = request.app.state.browser_requests
    manager.status(connection_id, request_id)
    job = manager.jobs[manager.key(connection_id, request_id)]
    if not job.task.done():
        job.task.cancel()
    return {'data': {'status': 'cancel_requested'}}
