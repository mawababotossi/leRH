from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.core.credits import SUBSCRIPTION_BONUS, CreditManager
from leRH.db.base import get_db
from leRH.db.repository import SubscriptionRepository, UserRepository
from leRH.schemas import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("/{user_id}", response_model=SubscriptionResponse, status_code=201)
async def subscribe(
    user_id: str,
    payload: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    sub_repo = SubscriptionRepository(db)
    existing = await sub_repo.get_by_user(user_id)
    if existing:
        raise HTTPException(status_code=409, detail="Vous avez déjà un abonnement")

    sub = await sub_repo.create(
        user_id=user_id,
        min_match_score=payload.min_match_score,
        notify_telegram=payload.notify_telegram,
        notify_whatsapp=payload.notify_whatsapp,
    )
    await CreditManager().add(user_id, SUBSCRIPTION_BONUS, reason="subscription_bonus", session=db)
    return SubscriptionResponse.model_validate(sub)


@router.get("/{user_id}", response_model=SubscriptionResponse)
async def get_subscription(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    sub_repo = SubscriptionRepository(db)
    sub = await sub_repo.get_by_user(user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Abonnement non trouvé")
    return SubscriptionResponse.model_validate(sub)


@router.patch("/{user_id}", response_model=SubscriptionResponse)
async def update_subscription(
    user_id: str,
    payload: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    sub_repo = SubscriptionRepository(db)
    sub = await sub_repo.get_by_user(user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Abonnement non trouvé")

    updates = payload.model_dump(exclude_none=True)
    if updates:
        sub = await sub_repo.update(sub, **updates)
    return SubscriptionResponse.model_validate(sub)


@router.delete("/{user_id}", status_code=204)
async def delete_subscription(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    sub_repo = SubscriptionRepository(db)
    sub = await sub_repo.get_by_user(user_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Abonnement non trouvé")
    await sub_repo.delete(sub)
