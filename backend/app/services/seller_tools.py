from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.ute_mall import ShopItemNotFoundError, StaleShopPriceError, UTEMallRepository
from app.models.action import ActionAudit, ActionProposal


class ProposalNotFoundError(LookupError):
    pass


class ProposalConflictError(RuntimeError):
    pass


class PriceUnchangedError(ValueError):
    pass


def create_price_proposal(
    session: Session,
    shop: UTEMallRepository,
    *,
    sku: str,
    new_price_vnd: int,
) -> ActionProposal:
    item = shop.get_item_by_sku(sku)
    if item["price_vnd"] == new_price_vnd:
        raise PriceUnchangedError("New price matches the current price")
    proposal = ActionProposal(
        kind="change_price",
        status="pending",
        target_kind=item["target_kind"],
        product_id=item["product_id"],
        variant_id=item["variant_id"],
        sku=item["sku"],
        product_name=item["product_name"],
        old_price_vnd=item["price_vnd"],
        new_price_vnd=new_price_vnd,
    )
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


def scoped_proposal(session: Session, shop: UTEMallRepository, proposal_id: int) -> ActionProposal:
    proposal = session.get(ActionProposal, proposal_id)
    if proposal is None:
        raise ProposalNotFoundError(proposal_id)
    try:
        item = shop.get_item_by_sku(proposal.sku)
    except ShopItemNotFoundError as error:
        raise ProposalNotFoundError(proposal_id) from error
    if (item['product_id'], item['variant_id'], item['target_kind']) != (proposal.product_id, proposal.variant_id, proposal.target_kind):
        raise ProposalNotFoundError(proposal_id)
    return proposal


def confirm_price_proposal(
    session: Session,
    shop: UTEMallRepository,
    proposal_id: int,
) -> tuple[ActionProposal, bool]:
    proposal = scoped_proposal(session, shop, proposal_id)
    if proposal.status == "approved":
        return proposal, True
    if proposal.status not in {"pending", "executing"}:
        raise ProposalConflictError(f"Proposal is already {proposal.status}")

    if proposal.status == "executing":
        current_item = shop.get_item_by_sku(proposal.sku)
        current_price = current_item["price_vnd"]
        if current_price == proposal.new_price_vnd:
            return _finalize_approved(session, proposal, idempotent=True)
        if current_price != proposal.old_price_vnd:
            _mark_conflict(session, proposal, current_price)
            raise ProposalConflictError("Product price changed; create a new proposal")
    else:
        proposal.status = "executing"
        session.commit()

    try:
        shop.apply_price_change(
            target_kind=proposal.target_kind,
            product_id=proposal.product_id,
            variant_id=proposal.variant_id,
            expected_price_vnd=proposal.old_price_vnd,
            new_price_vnd=proposal.new_price_vnd,
        )
    except StaleShopPriceError as error:
        if error.current_price_vnd == proposal.new_price_vnd:
            return _finalize_approved(session, proposal, idempotent=True)
        _mark_conflict(session, proposal, error.current_price_vnd)
        raise ProposalConflictError("Product price changed; create a new proposal") from error

    return _finalize_approved(session, proposal, idempotent=False)


def _finalize_approved(
    session: Session,
    proposal: ActionProposal,
    *,
    idempotent: bool,
) -> tuple[ActionProposal, bool]:
    proposal.status = "approved"
    proposal.decided_at = datetime.utcnow()
    session.add(ActionAudit(
        proposal_id=proposal.id,
        action="change_price",
        sku=proposal.sku,
        before_value=proposal.old_price_vnd,
        after_value=proposal.new_price_vnd,
    ))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        proposal = session.get(ActionProposal, proposal.id)
        audit = session.scalar(
            select(ActionAudit).where(ActionAudit.proposal_id == proposal.id)
        ) if proposal else None
        if proposal and audit:
            proposal.status = "approved"
            proposal.decided_at = proposal.decided_at or datetime.utcnow()
            session.commit()
            session.refresh(proposal)
            return proposal, True
        raise
    session.refresh(proposal)
    return proposal, idempotent


def _mark_conflict(session: Session, proposal: ActionProposal, current_price_vnd: int) -> None:
    proposal.status = "conflict"
    proposal.failure_reason = f"current_price_vnd={current_price_vnd}"
    proposal.decided_at = datetime.utcnow()
    session.commit()


def reject_price_proposal(session: Session, shop: UTEMallRepository, proposal_id: int) -> tuple[ActionProposal, bool]:
    proposal = scoped_proposal(session, shop, proposal_id)
    if proposal.status == "rejected":
        return proposal, True
    if proposal.status != "pending":
        raise ProposalConflictError(f"Proposal is already {proposal.status}")
    proposal.status = "rejected"
    proposal.decided_at = datetime.utcnow()
    session.commit()
    session.refresh(proposal)
    return proposal, False


def proposal_to_dict(proposal: ActionProposal, *, idempotent: bool = False) -> dict:
    return {
        "id": proposal.id,
        "kind": proposal.kind,
        "status": proposal.status,
        "target_kind": proposal.target_kind,
        "sku": proposal.sku,
        "product_name": proposal.product_name,
        "old_price_vnd": proposal.old_price_vnd,
        "new_price_vnd": proposal.new_price_vnd,
        "created_at": proposal.created_at,
        "decided_at": proposal.decided_at,
        "idempotent": idempotent,
    }
