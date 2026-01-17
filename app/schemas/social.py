# app/schemas/social.py
"""
Social media feature Pydantic schemas.
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, validator, field_validator


# ===== GROWER PROFILES =====

class GrowerProfileBase(BaseModel):
    business_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    instagram: Optional[str] = None


class GrowerProfileCreate(GrowerProfileBase):
    pass


class GrowerProfileUpdate(GrowerProfileBase):
    is_public: Optional[bool] = None


class GrowerProfileRead(GrowerProfileBase):
    id: int
    user_id: int
    is_public: bool
    created_at: datetime

    # Computed fields (will be added by endpoint)
    grower_name: Optional[str] = None
    total_published_reports: Optional[int] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None

    class Config:
        from_attributes = True


# ===== PRODUCT LOCATIONS =====

class ProductLocationBase(BaseModel):
    store_name: str
    store_link: Optional[str] = None
    store_phone: Optional[str] = None
    store_email: Optional[str] = None


class ProductLocationCreate(ProductLocationBase):
    pass


class ProductLocationUpdate(ProductLocationBase):
    store_name: Optional[str] = None  # Allow partial updates


class ProductLocationRead(ProductLocationBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===== PUBLISHED REPORTS =====

class PublishedReportCreate(BaseModel):
    plant_id: str
    grower_notes: Optional[str] = None


class PublishedReportRead(BaseModel):
    id: int
    user_id: int
    plant_id: str
    plant_name: str
    strain: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    final_phase: Optional[str]
    report_data: dict
    published_at: datetime
    views_count: int
    grower_notes: Optional[str]

    # Include grower info (will be added by endpoint)
    grower_name: Optional[str] = None
    grower_business_name: Optional[str] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None

    class Config:
        from_attributes = True


class PublishedReportSummary(BaseModel):
    """Lighter version for list views"""
    id: int
    plant_name: str
    strain: Optional[str]
    end_date: Optional[date]
    published_at: datetime
    views_count: int
    grower_name: str
    grower_business_name: Optional[str] = None
    average_rating: Optional[float] = None
    total_reviews: Optional[int] = None


# ===== UPCOMING STRAINS =====

class UpcomingStrainBase(BaseModel):
    strain_name: str
    description: Optional[str] = None
    expected_start_date: Optional[date] = None


class UpcomingStrainCreate(UpcomingStrainBase):
    pass


class UpcomingStrainRead(UpcomingStrainBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===== STRAIN REVIEWS =====

class StrainReviewBase(BaseModel):
    rating: int
    comment: str

    @field_validator('rating')
    @classmethod
    def rating_range(cls, v):
        if v < 1 or v > 5:
            raise ValueError('Rating must be between 1 and 5')
        return v

    @field_validator('comment')
    @classmethod
    def comment_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Comment cannot be empty')
        return v


class StrainReviewCreate(StrainReviewBase):
    pass


class StrainReviewUpdate(StrainReviewBase):
    pass


class StrainReviewRead(StrainReviewBase):
    id: int
    published_report_id: int
    reviewer_id: int
    created_at: datetime
    updated_at: datetime

    # Include reviewer info (will be added by endpoint)
    reviewer_name: Optional[str] = None

    # Include response if exists (will be added by endpoint)
    has_response: Optional[bool] = None
    response: Optional['ReviewResponseRead'] = None

    class Config:
        from_attributes = True


# ===== REVIEW RESPONSES =====

class ReviewResponseBase(BaseModel):
    response_text: str

    @field_validator('response_text')
    @classmethod
    def response_not_empty(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('Response cannot be empty')
        return v


class ReviewResponseCreate(ReviewResponseBase):
    pass


class ReviewResponseUpdate(ReviewResponseBase):
    pass


class ReviewResponseRead(ReviewResponseBase):
    id: int
    review_id: int
    grower_id: int
    created_at: datetime
    updated_at: datetime

    # Include grower info (will be added by endpoint)
    grower_name: Optional[str] = None

    class Config:
        from_attributes = True


# ===== ADMIN SETTINGS =====

class AdminSettingUpdate(BaseModel):
    setting_value: str


class AdminSettingRead(BaseModel):
    id: int
    setting_key: str
    setting_value: Optional[str]
    description: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


# Update forward references for nested models
StrainReviewRead.model_rebuild()
