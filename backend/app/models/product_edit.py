from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductEditProposal(Base):
    __tablename__ = 'product_edit_proposal'

    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(36), unique=True)
    shop_slug: Mapped[str] = mapped_column(String(120), index=True)
    sku: Mapped[str] = mapped_column(String(100))
    product_id: Mapped[int] = mapped_column(Integer)
    variant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductEditAudit(Base):
    __tablename__ = 'product_edit_audit'

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(Integer, unique=True)
    shop_slug: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(100))
    before_json: Mapped[str] = mapped_column(Text)
    after_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
