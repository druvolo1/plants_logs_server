# app/models/social.py
"""
Social media feature models: grower profiles, published reports, reviews, and admin settings.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Text, Date, JSON, Float, CheckConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class GrowerProfile(Base):
    __tablename__ = "grower_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Business Information
    business_name = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    instagram = Column(String(100), nullable=True)

    # System Fields
    is_public = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="grower_profile")
    product_locations = relationship(
        "ProductLocation",
        primaryjoin="GrowerProfile.user_id==ProductLocation.user_id",
        foreign_keys="ProductLocation.user_id",
        back_populates="grower",
        cascade="all, delete-orphan"
    )
    published_reports = relationship(
        "PublishedReport",
        primaryjoin="GrowerProfile.user_id==PublishedReport.user_id",
        foreign_keys="PublishedReport.user_id",
        back_populates="grower",
        cascade="all, delete-orphan"
    )
    upcoming_strains = relationship(
        "UpcomingStrain",
        primaryjoin="GrowerProfile.user_id==UpcomingStrain.user_id",
        foreign_keys="UpcomingStrain.user_id",
        back_populates="grower",
        cascade="all, delete-orphan"
    )


class ProductLocation(Base):
    __tablename__ = "product_locations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    store_name = Column(String(255), nullable=False)
    store_link = Column(String(500), nullable=True)
    store_phone = Column(String(20), nullable=True)
    store_email = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    grower = relationship(
        "GrowerProfile",
        primaryjoin="ProductLocation.user_id==GrowerProfile.user_id",
        foreign_keys=[user_id],
        back_populates="product_locations"
    )


class PublishedReport(Base):
    __tablename__ = "published_reports"

    id = Column(Integer, primary_key=True, index=True)

    # Links
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plant_id = Column(String(36), nullable=False)

    # Frozen Report Data
    plant_name = Column(String(255), nullable=False)
    strain = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    final_phase = Column(String(50), nullable=True)

    # Full report JSON (raw_data + aggregated_stats)
    report_data = Column(JSON, nullable=False)

    # Publishing Metadata
    published_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    unpublished_at = Column(DateTime, nullable=True)  # Soft delete
    views_count = Column(Integer, default=0, nullable=False)

    # Optional grower notes
    grower_notes = Column(Text, nullable=True)

    # Relationships
    grower = relationship(
        "GrowerProfile",
        primaryjoin="PublishedReport.user_id==GrowerProfile.user_id",
        foreign_keys=[user_id],
        back_populates="published_reports"
    )
    reviews = relationship("StrainReview", back_populates="report", cascade="all, delete-orphan")


class UpcomingStrain(Base):
    __tablename__ = "upcoming_strains"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    strain_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    expected_start_date = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    grower = relationship(
        "GrowerProfile",
        primaryjoin="UpcomingStrain.user_id==GrowerProfile.user_id",
        foreign_keys=[user_id],
        back_populates="upcoming_strains"
    )


class StrainReview(Base):
    __tablename__ = "strain_reviews"

    id = Column(Integer, primary_key=True, index=True)

    published_report_id = Column(Integer, ForeignKey("published_reports.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Table args for check constraint
    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
    )

    # Relationships
    report = relationship("PublishedReport", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    response = relationship("ReviewResponse", back_populates="review", uselist=False, cascade="all, delete-orphan")


class ReviewResponse(Base):
    __tablename__ = "review_responses"

    id = Column(Integer, primary_key=True, index=True)

    review_id = Column(Integer, ForeignKey("strain_reviews.id", ondelete="CASCADE"), nullable=False, unique=True)
    grower_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    response_text = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    review = relationship("StrainReview", back_populates="response")
    grower = relationship("User", foreign_keys=[grower_id])


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), nullable=False, unique=True)
    setting_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
