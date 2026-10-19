from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    shop_slug: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_edit_proposal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(50), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_arguments_json: Mapped[str] = mapped_column(Text, default="{}")
    facts_json: Mapped[str] = mapped_column(Text, default="{}")
    elapsed_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
