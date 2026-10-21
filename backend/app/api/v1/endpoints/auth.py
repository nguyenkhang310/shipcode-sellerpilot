from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.services.auth import login, require_seller, revoke

router = APIRouter(prefix='/auth', tags=['seller authentication'])


class LoginRequest(BaseModel):
    login_id: str = Field(min_length=1, max_length=180)
    password: SecretStr = Field(min_length=1, max_length=256)


@router.post('/login')
def sign_in(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    response.headers['Cache-Control'] = 'no-store'
    return {'data': login(request, session, payload.login_id.strip(), payload.password.get_secret_value())}


@router.get('/me')
def me(response: Response, user=Depends(require_seller)):
    response.headers['Cache-Control'] = 'no-store'
    return {'data': user}


@router.post('/logout')
def sign_out(request: Request, response: Response, user=Depends(require_seller), session: Session = Depends(get_session)):
    revoke(session, request.state.seller_session)
    response.headers['Cache-Control'] = 'no-store'
    return {'data': {'signed_out': True}}
