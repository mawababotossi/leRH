from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from leRH.db.base import get_db
from leRH.db.repository import UserRepository
from leRH.schemas import UserCreate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)) -> UserResponse:
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserResponse:
    repo = UserRepository(db)
    user = await repo.create(**payload.model_dump())
    return UserResponse.model_validate(user)


@router.get("/telegram/{telegram_id}", response_model=UserResponse)
async def get_user_by_telegram(
    telegram_id: int, db: AsyncSession = Depends(get_db)
) -> UserResponse:
    repo = UserRepository(db)
    user = await repo.get_by_telegram(telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)
