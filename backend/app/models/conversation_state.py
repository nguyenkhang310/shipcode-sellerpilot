from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationState(Base):
    __tablename__ = 'conversation_state'

    shop_slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
