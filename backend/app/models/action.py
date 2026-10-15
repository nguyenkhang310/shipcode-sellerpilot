from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActionProposal(Base):
    __tablename__ = "action_proposal"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), default="change_price")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    product_id: Mapped[int] = mapped_column(Integer)
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    product_name: Mapped[str] = mapped_column(String(200))
    old_price_vnd: Mapped[int] = mapped_column(Integer)
    new_price_vnd: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ActionAudit(Base):
    __tablename__ = "action_audit"
    __table_args__ = (UniqueConstraint("proposal_id", name="uq_action_audit_proposal_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(50))
    sku: Mapped[str] = mapped_column(String(100), index=True)
    before_value: Mapped[int] = mapped_column(Integer)
    after_value: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(100), default="demo_operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
