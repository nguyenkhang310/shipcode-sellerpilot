from fastapi import HTTPException

from app.models.conversation_state import ConversationState


def ensure_conversation_open(session, shop_slug: str, conversation_id: str | None):
    if conversation_id:
        state = session.get(ConversationState, (shop_slug, str(conversation_id)))
        if state and state.deleted_at:
            raise HTTPException(410, detail={'code': 'conversation_deleted',
                'message': 'Cuộc trò chuyện đã được xóa. Bạn mở cuộc trò chuyện mới nhé.'})
