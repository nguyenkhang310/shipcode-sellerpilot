from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssistantMemory(Base):
    __tablename__ = 'assistant_memory'
    __table_args__ = (UniqueConstraint('shop_slug', 'scope', 'key', name='uq_assistant_memory_scope'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_slug: Mapped[str] = mapped_column(String(120), index=True)
    scope: Mapped[str] = mapped_column(String(160))
    key: Mapped[str] = mapped_column(String(60))
    value_json: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
