from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class UserCreate(BaseModel):
    name: str
    country: str = "Togo"
    activity: str | None = None
    phone: str | None = None
    city: str | None = None
    telegram_id: int | None = None
    whatsapp_id: str | None = None


class UserResponse(BaseModel):
    id: str
    name: str
    country: str
    activity: str | None = None
    phone: str | None = None
    city: str | None = None
    telegram_id: int | None = None
    whatsapp_id: str | None = None
    verified: bool
    credits: int = 10
    created_at: datetime

    model_config = {"from_attributes": True}


class CVResponse(BaseModel):
    id: str
    user_id: str
    original_name: str
    analysis: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    recruiter_id: str
    title: str
    description: str
    company: str | None = None
    city: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    requirements: dict | None = None
    source_url: str | None = None
    external_id: str | None = None
    source_name: str | None = None
    is_external: bool = False


class JobUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    company: str | None = None
    city: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    requirements: dict | None = None
    status: str | None = None


class JobResponse(BaseModel):
    id: str
    title: str
    description: str
    company: str | None = None
    city: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    requirements: dict | None = None
    recruiter_id: str
    status: str
    source_url: str | None = None
    external_id: str | None = None
    source_name: str | None = None
    is_external: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApplicationCreate(BaseModel):
    candidate_id: str
    job_id: str


class ApplicationResponse(BaseModel):
    id: str
    candidate_id: str
    job_id: str
    status: str
    match_score: float | None = None
    ai_analysis: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CVUpload(BaseModel):
    user_id: str
    original_name: str
    extracted_text: str | None = None
    analysis: dict | None = None


class SubscriptionCreate(BaseModel):
    min_match_score: float = 60.0
    notify_telegram: bool = True
    notify_whatsapp: bool = False


class SubscriptionUpdate(BaseModel):
    active: bool | None = None
    min_match_score: float | None = None
    notify_telegram: bool | None = None
    notify_whatsapp: bool | None = None


class SubscriptionResponse(BaseModel):
    id: str
    user_id: str
    active: bool
    payment_status: str
    min_match_score: float
    notify_telegram: bool
    notify_whatsapp: bool
    last_notified_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentGenerateRequest(BaseModel):
    user_id: str
    job_id: str
    format: str = "docx"


class DocumentGenerateResponse(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
